"""验证码求解（无浏览器）。

通过 Node + jsdom 在模拟浏览器环境中运行阿里云无痕 SDK，
求得 verifyParam（X-Aliyun-Captcha-Verify-Param）。不再启动真实浏览器。

- 缓存：求得的 verifyParam 在 TTL 内复用
- 并发：同一时刻只跑一个求解进程，其余请求等待后命中缓存
- 重试：单次求解偶发失败时自动重试
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import httpx

from . import logs, settings

_SOLVER_LOG = settings.DATA_DIR / "solver.log"


def _log_solver(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(_SOLVER_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


class CaptchaManager:
    def __init__(self) -> None:
        self._cached: str | None = None
        self._cached_at: float = 0.0
        self._lock = asyncio.Lock()
        self._config_cache: dict | None = None
        self._config_cache_at: float = 0.0
        # camoufox 求解器惰性初始化
        self._camoufox: object | None = None

    @property
    def solver_mode(self) -> str:
        return settings.CAPTCHA_SOLVER

    # ── 配置 ─────────────────────────────────────────────────────────────────
    async def fetch_config(self) -> dict:
        now = time.time() * 1000
        if self._config_cache and now - self._config_cache_at < settings.CAPTCHA_CONFIG_CACHE_TTL:
            return self._config_cache
        try:
            async with httpx.AsyncClient(timeout=15, verify=settings.TLS_VERIFY) as client:
                res = await client.get(
                    "https://zcode.z.ai/api/v1/client/configs"
                    "?app_version=3.0.0&platform=win32"
                )
            res.raise_for_status()
            captcha = ((res.json().get("data") or {}).get("configs") or {}).get("captcha")
            if captcha:
                self._config_cache = captcha
                self._config_cache_at = now
                return captcha
        except (httpx.HTTPError, ValueError) as err:
            logs.warn("captcha", f"获取配置失败，使用默认: {err}")
        return {"enabled": True, "prefix": "no8xfe", "region": "sgp", "sceneId": "11xygtvd"}

    # ── 求解 ─────────────────────────────────────────────────────────────────
    async def startup(self) -> None:
        """应用启动后预初始化求解器（camoufox 模式预启动浏览器池）。

        等待 HTTP 服务就绪后再启动，因为浏览器需要加载本服务提供的页面。
        """
        if self.solver_mode != "camoufox":
            return
        # 等待本服务 HTTP 端口就绪
        import httpx
        url = f"http://127.0.0.1:{settings.PORT}/static/captcha-solver.html"
        for _ in range(60):
            try:
                async with httpx.AsyncClient(timeout=2, verify=settings.TLS_VERIFY) as cx:
                    r = await cx.get(url)
                    if r.status_code < 500:
                        break
            except Exception:
                await asyncio.sleep(0.5)
        else:
            logs.warn("captcha", "等待 HTTP 服务就绪超时，跳过浏览器池预启动")
            return

        try:
            if self._camoufox is None:
                from .camoufox_solver import CamoufoxSolver
                self._camoufox = CamoufoxSolver()
            await self._camoufox._ensure()
        except Exception as err:  # noqa: BLE001
            logs.warn("captcha", f"camoufox 浏览器池预启动失败: {err}")

    async def get_verify_param(self, port: int | None = None, *, force_fresh: bool = False) -> str:
        if not force_fresh:
            now = time.time() * 1000
            if self._cached and now - self._cached_at < settings.CAPTCHA_CACHE_TTL:
                return self._cached

        async with self._lock:
            if not force_fresh:
                if self._cached and time.time() * 1000 - self._cached_at < settings.CAPTCHA_CACHE_TTL:
                    return self._cached

            config = await self.fetch_config()
            param = await self._solve(config, port)
            self._cached = param
            self._cached_at = time.time() * 1000
            return param

    async def _solve(self, config: dict, port: int | None = None) -> str:
        mode = self.solver_mode
        if mode == "camoufox":
            return await self._solve_camoufox(config, port)

        # 默认 jsdom 求解
        return await self._solve_jsdom(config)

    async def _solve_camoufox(self, config: dict, port: int | None) -> str:
        if self._camoufox is None:
            from .camoufox_solver import CamoufoxSolver
            self._camoufox = CamoufoxSolver()

        last_err: str | None = None
        for attempt in range(1, settings.CAPTCHA_SOLVE_RETRIES + 1):
            try:
                param = await self._camoufox.solve(config, port)
            except Exception as err:  # noqa: BLE001
                last_err = str(err)
                param = None
            if param:
                if attempt > 1:
                    logs.ok("captcha", f"camoufox 求解成功（第 {attempt} 次尝试）")
                return param
            logs.warn("captcha", f"camoufox 第 {attempt}/{settings.CAPTCHA_SOLVE_RETRIES} 次求解未果，重试…")

        raise RuntimeError(f"camoufox 求解失败: {last_err or '多次重试无结果'}")

    async def _solve_jsdom(self, config: dict) -> str:
        scene = config.get("sceneId") or "11xygtvd"
        region = config.get("region") or "sgp"
        prefix = config.get("prefix") or "no8xfe"

        last_err: str | None = None
        for attempt in range(1, settings.CAPTCHA_SOLVE_RETRIES + 1):
            try:
                param = await self._run_solver(scene, region, prefix)
            except Exception as err:  # noqa: BLE001
                last_err = str(err)
                param = None
            if param:
                if attempt > 1:
                    logs.ok("captcha", f"求解成功（第 {attempt} 次尝试）")
                return param
            logs.warn("captcha", f"第 {attempt}/{settings.CAPTCHA_SOLVE_RETRIES} 次求解未果，重试…")

        raise RuntimeError(f"验证码求解失败: {last_err or '多次重试无结果'}")

    async def _run_solver(self, scene: str, region: str, prefix: str) -> str | None:
        # 优先走常驻 Node HTTP 服务（/solve）
        if settings.SOLVER_SERVER_ENABLED:
            try:
                from .solver_server import solver_server
                if solver_server.enabled and solver_server.base_url:
                    return await solver_server.solve(
                        scene, region, prefix, settings.REVERSE_URL,
                        timeout_ms=int(settings.CAPTCHA_SOLVE_TIMEOUT * 1000),
                    )
            except Exception as err:  # noqa: BLE001
                _log_solver(f"HTTP /solve 失败，回退子进程模式: {err}")

        # 回退：直接 spawn solver.js（保留原行为）
        if not settings.CAPTCHA_SOLVER_JS.exists():
            raise RuntimeError(
                f"未找到求解器 {settings.CAPTCHA_SOLVER_JS}，请先在 captcha_node 下执行 npm install"
            )
        env = None
        if settings.PROXY_URL:
            env = {"GLOBAL_AGENT_HTTP_PROXY": settings.PROXY_URL, **dict(env or {})}
            if os.environ.get("PATH"):
                env["PATH"] = os.environ["PATH"]
        proc = await asyncio.create_subprocess_exec(
            settings.NODE_PATH, str(settings.CAPTCHA_SOLVER_JS),
            scene, region, prefix, settings.REVERSE_URL,
            cwd=str(settings.CAPTCHA_SOLVER_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        solver_output = ""
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=settings.CAPTCHA_SOLVE_TIMEOUT)
            solver_output = stdout.decode("utf-8", "ignore")
            solver_err = stderr.decode("utf-8", "ignore")
            if solver_err:
                _log_solver(f"stderr:\n{solver_err.strip()}")
        except asyncio.TimeoutError:
            _log_solver("超时")
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return None
        except FileNotFoundError as err:
            raise RuntimeError(f"无法启动 Node（{settings.NODE_PATH}）: {err}") from err

        for line in solver_output.splitlines():
            if line.startswith("VERIFY_PARAM="):
                return line[len("VERIFY_PARAM="):].strip()

        _log_solver(f"未找到 VERIFY_PARAM，stdout:\n{solver_output.strip()}")
        return None

    def invalidate(self) -> None:
        self._cached = None
        self._cached_at = 0.0

    async def close(self) -> None:
        if self._camoufox is not None:
            try:
                await self._camoufox.close()
            except Exception:  # noqa: BLE001
                pass


captcha_manager = CaptchaManager()
