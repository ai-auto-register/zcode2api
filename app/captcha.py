"""验证码求解（无浏览器）。

通过 Node + jsdom 在模拟浏览器环境中运行阿里云无痕 SDK，
求得 verifyParam（X-Aliyun-Captcha-Verify-Param）。不再启动真实浏览器。

- 缓存：求得的 verifyParam 在 TTL 内复用
- 并发：同一时刻只跑一个求解进程，其余请求等待后命中缓存
- 重试：单次求解偶发失败时自动重试
"""

from __future__ import annotations

import asyncio
import time

import httpx

from . import logs, settings


class CaptchaManager:
    def __init__(self) -> None:
        self._cached: str | None = None
        self._cached_at: float = 0.0
        self._lock = asyncio.Lock()
        self._config_cache: dict | None = None
        self._config_cache_at: float = 0.0

    # ── 配置 ─────────────────────────────────────────────────────────────────
    async def fetch_config(self) -> dict:
        now = time.time() * 1000
        if self._config_cache and now - self._config_cache_at < settings.CAPTCHA_CONFIG_CACHE_TTL:
            age = (now - self._config_cache_at) / 1000
            logs.info("captcha", f"配置缓存命中 (age={age:.0f}s)")
            return self._config_cache
        try:
            logs.info("captcha", "GET https://zcode.z.ai/api/v1/client/configs (获取验证码配置)")
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.get(
                    "https://zcode.z.ai/api/v1/client/configs"
                    "?app_version=3.0.0&platform=win32"
                )
            res.raise_for_status()
            captcha = ((res.json().get("data") or {}).get("configs") or {}).get("captcha")
            if captcha:
                self._config_cache = captcha
                self._config_cache_at = now
                logs.ok("captcha", f"配置获取成功: sceneId={captcha.get('sceneId')} region={captcha.get('region')}")
                return captcha
        except (httpx.HTTPError, ValueError) as err:
            logs.warn("captcha", f"获取配置失败，使用默认: {err}")
        return {"enabled": True, "prefix": "no8xfe", "region": "sgp", "sceneId": "11xygtvd"}

    # ── 求解 ─────────────────────────────────────────────────────────────────
    async def get_verify_param(self, port: int | None = None) -> str:
        now = time.time() * 1000
        if self._cached and now - self._cached_at < settings.CAPTCHA_CACHE_TTL:
            age = (now - self._cached_at) / 1000
            logs.info("captcha", f"verifyParam 缓存命中 (age={age:.0f}s)")
            return self._cached

        async with self._lock:
            if self._cached and time.time() * 1000 - self._cached_at < settings.CAPTCHA_CACHE_TTL:
                age = (time.time() * 1000 - self._cached_at) / 1000
                logs.info("captcha", f"verifyParam 缓存命中 (等锁后, age={age:.0f}s)")
                return self._cached

            logs.step("captcha", "验证码求解中 (缓存未命中)...")
            config = await self.fetch_config()
            param = await self._solve(config)
            self._cached = param
            self._cached_at = time.time() * 1000
            logs.ok("captcha", f"verifyParam 求解完成: {param[:20]}... (TTL={settings.CAPTCHA_CACHE_TTL}ms)")
            return param

    async def _solve(self, config: dict) -> str:
        scene = config.get("sceneId") or "11xygtvd"
        region = config.get("region") or "sgp"
        prefix = config.get("prefix") or "no8xfe"

        last_err: str | None = None
        for attempt in range(1, settings.CAPTCHA_SOLVE_RETRIES + 1):
            try:
                t0 = time.time()
                param = await self._run_solver(scene, region, prefix)
                elapsed = time.time() - t0
            except Exception as err:  # noqa: BLE001
                last_err = str(err)
                param = None
                elapsed = time.time() - t0
            if param:
                log_msg = f"求解成功 ({elapsed:.1f}s)"
                if attempt > 1:
                    log_msg += f"，第 {attempt} 次尝试"
                    logs.ok("captcha", log_msg)
                else:
                    logs.info("captcha", log_msg)
                return param
            logs.warn("captcha", f"第 {attempt}/{settings.CAPTCHA_SOLVE_RETRIES} 次求解未果 ({elapsed:.1f}s){f': {last_err}' if last_err else ''}，重试…")

        raise RuntimeError(f"验证码求解失败: {last_err or '多次重试无结果'}")

    async def _run_solver(self, scene: str, region: str, prefix: str) -> str | None:
        if not settings.CAPTCHA_SOLVER_JS.exists():
            raise RuntimeError(
                f"未找到求解器 {settings.CAPTCHA_SOLVER_JS}，请先在 captcha_node 下执行 npm install"
            )
        env = None
        if settings.PROXY_URL:
            env = {"GLOBAL_AGENT_HTTP_PROXY": settings.PROXY_URL, **dict(env or {})}
            # 继承父进程 PATH 确保能找到 node
            import os
            if os.environ.get("PATH"):
                env["PATH"] = os.environ["PATH"]
        logs.info("captcha", f"启动求解器: {settings.NODE_PATH} {settings.CAPTCHA_SOLVER_JS.name} scene={scene} region={region}")
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
                logs.warn("captcha", f"求解器 stderr: {solver_err.strip()}")
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            logs.warn("captcha", "求解器超时")
            return None
        except FileNotFoundError as err:
            raise RuntimeError(f"无法启动 Node（{settings.NODE_PATH}）: {err}") from err

        for line in solver_output.splitlines():
            if line.startswith("VERIFY_PARAM="):
                return line[len("VERIFY_PARAM="):].strip()

        logs.warn("captcha", f"求解器输出中未找到 VERIFY_PARAM，完整 stdout:\n{solver_output.strip()}")
        return None

    def invalidate(self) -> None:
        logs.info("captcha", "verifyParam 缓存已失效")
        self._cached = None
        self._cached_at = 0.0

    async def close(self) -> None:
        pass


captcha_manager = CaptchaManager()
