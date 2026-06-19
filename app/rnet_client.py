"""rnet 客户端：用 Chrome131 指纹模拟，供求解与业务请求共用。

求解阶段：jsdom 内阿里云 SDK 发起的请求经桩转发到 Python，由本客户端用 rnet 发出。
业务阶段：zcode /messages 请求也由本客户端发出。
两者 TLS/UA/出口 IP 完全一致。
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import rnet

from . import logs, settings


class RnetClient:
    """单例 rnet 客户端，模拟 Chrome131 指纹。"""

    def __init__(self) -> None:
        self._client: Optional[rnet.Client] = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> rnet.Client:
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    kwargs: dict = {"impersonate": rnet.Impersonate.Chrome131}
                    if settings.PROXY_URL:
                        kwargs["proxy"] = settings.PROXY_URL
                    if not settings.TLS_VERIFY:
                        kwargs["verify"] = False
                    self._client = rnet.Client(**kwargs)
                    logs.ok("rnet", f"Chrome131 客户端已创建 proxy={bool(settings.PROXY_URL)} tls_verify={settings.TLS_VERIFY}")
        return self._client

    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        body: Optional[bytes] = None,
    ) -> tuple[int, dict, bytes]:
        """发起请求，返回 (status, headers, body_bytes)。用于 jsdom 桩回调。"""
        client = await self._ensure()
        # rnet 需要 Method 枚举，不接受 str
        rnet_method = getattr(rnet.Method, method.upper(), rnet.Method.GET)
        kw: dict = {}
        if headers:
            kw["headers"] = headers
        if body is not None:
            kw["body"] = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body
        resp = await client.request(rnet_method, url, **kw)
        status = resp.status_code
        status_int = status.as_int() if hasattr(status, "as_int") else int(status)
        # rnet Response.headers 是 HeaderMap 对象，key/value 可能是 bytes
        try:
            raw_hdrs = list(resp.headers.items()) if hasattr(resp.headers, "items") else []
            hdrs = {}
            for k, v in raw_hdrs:
                ks = k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else str(k)
                vs = v.decode("utf-8") if isinstance(v, (bytes, bytearray)) else str(v)
                hdrs[ks] = vs
        except Exception:
            hdrs = {}
        data = await resp.bytes()
        return status_int, hdrs, data

    async def stream_post(
        self,
        url: str,
        headers: dict,
        body: dict,
    ):
        """流式 POST，返回 rnet Response（调用方可 iter stream）。用于 zcode /messages。"""
        client = await self._ensure()
        resp = await client.post(url, headers=headers, json=body)
        return resp

    async def close(self) -> None:
        # rnet Client 没有显式 close 接口
        self._client = None


rnet_client = RnetClient()
