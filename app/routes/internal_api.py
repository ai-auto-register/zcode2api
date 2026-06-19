"""内部回调路由：接收 Node jsdom 桩转发的请求，用 rnet (Chrome131) 实际发出。

Node solver 在求解阶段，jsdom 内阿里云 SDK 发起的 HTTP 请求被桩拦截，
通过 HTTP 转发给本路由，由 Python rnet 客户端用 Chrome131 指纹发出。
这样求解阶段与业务请求阶段 TLS/UA/出口 IP 完全一致。

鉴权：Node 调用时必须携带 X-Rnet-Token 头，值与 solver_server 启动时生成的
共享密钥一致；否则 401。仅本机 Node 进程能拿到该 token。

额外：/internal/captcha-solver 返回 captcha-proxy.html（供 camoufox 加载），
/internal/aliyun-sdk 反代阿里云 SDK JS 文件（避免 camoufox 跨域加载问题）。
"""

from __future__ import annotations

import base64
import hmac
import json
from pathlib import Path

import httpx
from fastapi import APIRouter, Header, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .. import logs, settings
from ..rnet_client import rnet_client
from ..solver_server import solver_server

router = APIRouter()

_ALIYUN_SDK_URL = "https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js"
_PROXY_HTML = settings.ROOT_DIR / "captcha-proxy.html"
_sdk_cache: tuple[bytes, float] | None = None
_SDK_CACHE_TTL = 3600.0


@router.get("/internal/captcha-solver", response_class=HTMLResponse)
async def captcha_solver_page():
    """返回 captcha-solver.html，供 camoufox 浏览器加载。"""
    html_path = settings.STATIC_DIR / "captcha-solver.html"
    if not html_path.exists():
        return HTMLResponse("captcha-solver.html not found", status_code=404)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@router.get("/internal/aliyun-sdk")
async def aliyun_sdk():
    """反代阿里云验证码 SDK JS 文件，避免浏览器跨域加载问题。"""
    global _sdk_cache
    import time as _t
    now = _t.time()
    if _sdk_cache and now - _sdk_cache[1] < _SDK_CACHE_TTL:
        return Response(content=_sdk_cache[0], media_type="application/javascript")
    try:
        async with httpx.AsyncClient(timeout=20, verify=settings.TLS_VERIFY) as cx:
            r = await cx.get(_ALIYUN_SDK_URL)
            r.raise_for_status()
            data = r.content
        _sdk_cache = (data, now)
        return Response(content=data, media_type="application/javascript")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@router.post("/internal/rnet-proxy")
async def rnet_proxy(
    request: Request,
    x_rnet_token: str | None = Header(default=None, alias="X-Rnet-Token"),
):
    # 鉴权：校验共享密钥
    expected = solver_server.callback_token
    if not expected:
        return JSONResponse({"error": "callback not initialized"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    if not x_rnet_token or not hmac.compare_digest(x_rnet_token, expected):
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"error": "invalid json"}, status_code=400)

    method = (payload.get("method") or "GET").upper()
    url = payload.get("url")
    if not url or not isinstance(url, str):
        return JSONResponse({"error": "missing url"}, status_code=400)

    # REVERSE_URL 反向代理前缀：把阿里云验证 API 的请求走反向代理
    # settings 已 rstrip("/")，需补回 "/"，与原 jsdom 行为一致
    reverse_url = (payload.get("reverse_url") or settings.REVERSE_URL).strip().rstrip("/")
    if reverse_url and url.startswith("http") and not url.startswith(reverse_url):
        url = reverse_url + "/" + url

    headers = payload.get("headers") or {}
    body_b64 = payload.get("body")
    body: bytes | None = None
    if body_b64:
        try:
            body = base64.b64decode(body_b64)
        except Exception:
            body = None

    try:
        resp_status, resp_headers, data = await rnet_client.request(method, url, headers, body)
    except Exception as err:
        logs.warn("rnet-proxy", f"转发失败 {method} {url[:80]}: {err}")
        return JSONResponse({"error": str(err)}, status_code=502)

    return JSONResponse({
        "status": resp_status,
        "headers": resp_headers,
        "body": base64.b64encode(data).decode("ascii") if data else "",
    })
