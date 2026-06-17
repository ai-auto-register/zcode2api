"""验证码求解（WebSocket 模式）。

页面客户端通过 WebSocket 连接，完成阿里云无痕验证后将 verifyParam 提交回来。
网关需要验证码时，若缓存失效则等待 WS 客户端提交结果。

- 缓存：求得的 verifyParam 在 TTL 内复用
- 并发：同一时刻只等待一个求解结果，其余请求等待后命中缓存
"""

from __future__ import annotations

import asyncio
import time

from fastapi import WebSocket

from . import logs, settings


class CaptchaManager:
    def __init__(self) -> None:
        self._cached: str | None = None
        self._cached_at: float = 0.0
        self._lock = asyncio.Lock()
        self._config_cache: dict | None = None
        self._config_cache_at: float = 0.0
        self._pending: asyncio.Future[str] | None = None
        self._ws_clients: list[WebSocket] = []
        self._last_config: dict | None = None

    @property
    def last_config(self) -> dict | None:
        return self._last_config

    @property
    def ws_clients(self) -> list[WebSocket]:
        return self._ws_clients

    # ── 配置 ─────────────────────────────────────────────────────────────────
    async def fetch_config(self) -> dict:
        import httpx

        now = time.time() * 1000
        if self._config_cache and now - self._config_cache_at < settings.CAPTCHA_CONFIG_CACHE_TTL:
            return self._config_cache
        try:
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
                self._last_config = captcha
                return captcha
        except (httpx.HTTPError, ValueError) as err:
            logs.warn("captcha", f"获取配置失败，使用默认: {err}")
        default = {"enabled": True, "prefix": "no8xfe", "region": "sgp", "sceneId": "11xygtvd"}
        self._last_config = default
        return default

    # ── 求解 ─────────────────────────────────────────────────────────────────
    async def get_verify_param(self, port: int | None = None) -> str:
        now = time.time() * 1000
        if self._cached and now - self._cached_at < settings.CAPTCHA_CACHE_TTL:
            return self._cached

        async with self._lock:
            if self._cached and time.time() * 1000 - self._cached_at < settings.CAPTCHA_CACHE_TTL:
                return self._cached

            config = await self.fetch_config()
            await self._request_solve(config)

            if self._pending and not self._pending.done():
                try:
                    param = await asyncio.wait_for(
                        asyncio.shield(self._pending),
                        timeout=settings.CAPTCHA_SOLVE_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    self._pending = None
                    raise RuntimeError("验证码求解超时，页面客户端未响应")
                self._pending = None
                if param:
                    self._cached = param
                    self._cached_at = time.time() * 1000
                    return param
                raise RuntimeError("验证码求解返回空结果")

            if self._cached:
                return self._cached
            raise RuntimeError("验证码求解失败")

    async def _request_solve(self, config: dict) -> None:
        if self._pending and not self._pending.done():
            return
        self._pending = asyncio.get_running_loop().create_future()
        scene = config.get("sceneId") or "11xygtvd"
        region = config.get("region") or "sgp"
        prefix = config.get("prefix") or "no8xfe"
        task = {"type": "solve", "scene": scene, "region": region, "prefix": prefix}
        dead = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(task)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.remove(ws)

    def submit_result(self, param: str) -> None:
        if self._pending and not self._pending.done():
            self._pending.set_result(param)
        self._cached = param
        self._cached_at = time.time() * 1000

    def register_ws(self, ws: WebSocket) -> None:
        self._ws_clients.append(ws)

    def unregister_ws(self, ws: WebSocket) -> None:
        if ws in self._ws_clients:
            self._ws_clients.remove(ws)

    def invalidate(self) -> None:
        self._cached = None
        self._cached_at = 0.0

    async def close(self) -> None:
        pass


captcha_manager = CaptchaManager()
