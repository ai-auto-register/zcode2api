"""Node 求解服务的进程管理与客户端。

启动 captcha_node/server.js，自动选取空闲端口（或使用配置端口），提供：

- solve(scene, region, prefix, reverse_url) -> str  ：求解 verifyParam

Node jsdom 求解时，阿里云 SDK 发起的请求经桩转发到 Python /internal/rnet-proxy，
由 rnet (Chrome131) 实际发出，保证求解与业务请求 TLS/UA/出口 IP 一致。
回调通过共享随机 token 鉴权。

进程生命周期与 FastAPI 应用绑定（lifespan 中 start/stop）。
"""

from __future__ import annotations

import asyncio
import json
import secrets
import socket
import time
from typing import Optional

import httpx

from . import logs, settings


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SolverServer:
    """守护 Node HTTP 服务的生命周期，并提供 HTTP 调用接口。"""

    def __init__(self) -> None:
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._port: int = 0
        self._base: str = ""
        self._client: Optional[httpx.AsyncClient] = None
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._stdout_buf: list[str] = []
        self._start_lock = asyncio.Lock()
        self._callback_token: str = ""

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        return self._base

    @property
    def enabled(self) -> bool:
        return settings.SOLVER_SERVER_ENABLED

    @property
    def callback_token(self) -> str:
        """共享密钥：Node 调用 Python /internal/rnet-proxy 时必须携带。"""
        return self._callback_token

    async def start(self, rnet_callback: str = "") -> None:
        if not self.enabled:
            return
        async with self._start_lock:
            if self._proc and self._proc.returncode is None:
                return
            if not settings.SOLVER_SERVER_JS.exists():
                raise RuntimeError(
                    f"未找到 Node 服务脚本 {settings.SOLVER_SERVER_JS}，请在 captcha_node 下执行 npm install"
                )
            port = settings.SOLVER_PORT or _pick_free_port()
            self._callback_token = secrets.token_hex(16)
            env = {
                "SOLVER_PORT": str(port),
                "SOLVER_HOST": settings.SOLVER_HOST,
                "ZCODE_UA": settings.USER_AGENT,
            }
            if rnet_callback:
                env["RNET_CALLBACK_URL"] = rnet_callback
                env["RNET_CALLBACK_TOKEN"] = self._callback_token
            if settings.PROXY_URL:
                env["GLOBAL_AGENT_HTTP_PROXY"] = settings.PROXY_URL
            if __import__("os").environ.get("PATH"):
                env["PATH"] = __import__("os").environ["PATH"]

            self._proc = await asyncio.create_subprocess_exec(
                settings.NODE_PATH, str(settings.SOLVER_SERVER_JS),
                cwd=str(settings.CAPTCHA_SOLVER_DIR),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env={**__import__("os").environ, **env},
            )
            self._port = port
            self._base = f"http://{settings.SOLVER_HOST}:{port}"
            self._stdout_buf = []
            self._task = asyncio.create_task(self._pump())
            await self._wait_ready()
            logs.ok("solver", f"Node 服务已启动 {self._base}")

    async def _pump(self) -> None:
        assert self._proc is not None
        async def _drain(stream, prefix: str) -> None:
            assert stream is not None
            while True:
                line = await stream.readline()
                if not line:
                    break
                msg = line.decode("utf-8", "ignore").rstrip()
                self._stdout_buf.append(f"[{prefix}] {msg}")
                if len(self._stdout_buf) > 200:
                    self._stdout_buf = self._stdout_buf[-200:]
        try:
            await asyncio.gather(_drain(self._proc.stdout, "out"), _drain(self._proc.stderr, "err"))
        except Exception:
            pass

    async def _wait_ready(self, timeout: float = 15.0) -> None:
        deadline = time.time() + timeout
        last_err: Optional[str] = None
        async with httpx.AsyncClient(timeout=2.0, verify=settings.TLS_VERIFY) as probe:
            while time.time() < deadline:
                if self._proc and self._proc.returncode is not None:
                    tail = "\n".join(self._stdout_buf[-20:])
                    raise RuntimeError(f"Node 服务进程提前退出（code={self._proc.returncode}）\n{tail}")
                try:
                    r = await probe.get(f"{self._base}/healthz")
                    if r.status_code == 200:
                        return
                except Exception as e:  # noqa: BLE001
                    last_err = str(e)
                await asyncio.sleep(0.3)
        raise RuntimeError(f"Node 服务启动超时: {last_err or 'unknown'}")

    async def stop(self) -> None:
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass
        self._proc = None
        self._base = ""
        self._port = 0

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base,
                timeout=httpx.Timeout(connect=10.0, read=None, write=120.0, pool=30.0),
                verify=settings.TLS_VERIFY,
            )
        return self._client

    # ── 公共接口 ─────────────────────────────────────────────────────────────
    async def solve(
        self,
        scene: str,
        region: str,
        prefix: str,
        reverse_url: str = "",
        timeout_ms: int = 25_000,
    ) -> str:
        """调用 Node /solve，返回 verifyParam。失败抛 RuntimeError。"""
        if not self.enabled or not self._base:
            raise RuntimeError("Node 求解服务未启用/未启动")
        client = self._ensure_client()
        payload = {
            "scene": scene,
            "region": region,
            "prefix": prefix,
            "reverse_url": reverse_url,
            "timeout_ms": int(timeout_ms),
        }
        try:
            r = await client.post("/solve", json=payload, timeout=settings.SOLVER_HTTP_TIMEOUT)
        except httpx.HTTPError as e:
            raise RuntimeError(f"调用 Node /solve 失败: {e}") from e
        if r.status_code != 200:
            raise RuntimeError(f"Node /solve 返回 HTTP {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
        except ValueError as e:
            raise RuntimeError(f"Node /solve 响应非 JSON: {e}") from e
        if not data.get("ok"):
            raise RuntimeError(f"Node 求解失败: {data.get('error') or 'unknown'}")
        param = data.get("verify_param")
        if not isinstance(param, str) or not param:
            raise RuntimeError("Node /solve 返回空 verify_param")
        return param


solver_server = SolverServer()
