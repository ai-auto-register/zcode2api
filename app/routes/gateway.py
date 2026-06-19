"""核心网关：兼容 Anthropic Messages 协议的 /v1/messages，以及兼容 OpenAI 协议的 /v1/chat/completions。

实现多账号轮询 + 额度用完自动换号 + 阿里无痕验证自动续期。
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from typing import Callable, Awaitable, Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .. import logs, settings
from ..agent import build_request
from ..auth_admin import verify_gateway_key
from ..captcha import captcha_manager
from ..models import Account, Status
from ..quota import fetch_quota
from ..store import store
from ..openai_bridge import convert_openai_to_anthropic, convert_anthropic_to_openai, openai_streaming_response
from ..system_prompt import inject_official_system, apply_forgetting_directive

router = APIRouter()


class _CmShim:
    """伪装 httpx stream 的上下文管理器：持有一个异步清理回调。"""
    def __init__(self, aclose):
        self._aclose = aclose

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._aclose:
            try:
                await self._aclose()
            except Exception:
                pass


class _ClientShim:
    """伪装 httpx.AsyncClient，formatter 在 finally 里调用 aclose()。"""
    async def aclose(self):
        pass


class _RnetResponseShim:
    """把 rnet Response 包装成 httpx.Response 兼容接口（status_code/aread/aiter_bytes/aclose）。"""
    def __init__(self, rnet_resp):
        self._resp = rnet_resp
        sc = rnet_resp.status_code
        self.status_code = sc.as_int() if hasattr(sc, "as_int") else int(sc)
        # rnet HeaderMap 的 .get() 需要 bytes 默认值，转成普通 dict 避免 TypeError
        try:
            raw_hdrs = list(rnet_resp.headers.items()) if hasattr(rnet_resp.headers, "items") else []
            self.headers = {}
            for k, v in raw_hdrs:
                ks = k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else str(k)
                vs = v.decode("utf-8") if isinstance(v, (bytes, bytearray)) else str(v)
                self.headers[ks] = vs
        except Exception:
            self.headers = {}

    async def aread(self) -> bytes:
        return await self._resp.bytes()

    async def aiter_bytes(self):
        stream = self._resp.stream()
        async for chunk in stream:
            yield chunk

    async def aclose(self):
        try:
            await self._resp.close()
        except Exception:
            pass


async def _open_upstream(url: str, headers: dict, payload: bytes, body: dict, provider: str):
    """打开到上游的流式请求，返回 (resp, cm, client)。

    zai provider 用 rnet (Chrome131) 发请求，与求解环境 TLS/UA/出口 IP 完全一致；
    bigmodel provider 用 httpx 直连。
    """
    if provider == "zai" and settings.SOLVER_SERVER_ENABLED:
        from ..rnet_client import rnet_client
        rnet_resp = await rnet_client.stream_post(url, headers, body)
        shim = _RnetResponseShim(rnet_resp)
        async def _close():
            await shim.aclose()
        return shim, _CmShim(_close), _ClientShim()

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=30.0, read=None, write=120.0, pool=30.0),
        verify=settings.TLS_VERIFY,
    )
    cm = client.stream("POST", url, headers=headers, content=payload)
    resp = await cm.__aenter__()
    return resp, cm, client


MAX_CAPTCHA_RETRIES = 3
MAX_ACCOUNT_ATTEMPTS = 5

# Z.AI 上游模型名大小写敏感
MODEL_NAME_MAP = {
    "glm-5.2": "GLM-5.2",
    "glm-5-turbo": "GLM-5-Turbo",
    "glm-turbo": "GLM-5-Turbo",
    "glm-5.1": "GLM-5.1",
    "glm-4.7": "GLM-4.7",
}

AVAILABLE_MODELS = list(MODEL_NAME_MAP.values())

_EXHAUST_KEYWORDS = ("quota", "insufficient", "balance", "exhaust", "额度", "余额不足")


def _detect_provider(body: dict, headers) -> str:
    model = body.get("model") or ""
    if model.startswith("bigmodel/") or headers.get("x-provider") == "bigmodel":
        return "bigmodel"
    return "zai"


def _normalize_body(body: dict) -> dict:
    model = body.get("model")
    if isinstance(model, str) and "/" in model:
        model = "/".join(model.split("/")[1:])
    if isinstance(model, str):
        model = MODEL_NAME_MAP.get(model.lower(), model)
        body["model"] = model

    messages = body.get("messages")
    if isinstance(messages, list):
        bridged = []
        for msg in messages:
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                bridged.append({**msg, "content": [{"type": "text", "text": msg["content"]}]})
            else:
                bridged.append(msg)
        body["messages"] = bridged
    return body


def _inject_gateway_system(body: dict, provider: str) -> dict:
    """注入官方 ZCode 系统提示词门禁 block + 遗忘指令（仅 zai/StartPlan）。

    zcode-plan 网关对 body.system 做逐字校验，必须以官方前两个 block 开头，
    否则 3012。bigmodel 端点无此校验，原样透传。

    最终 system 形态：[官方block0, 官方block1, 客户端system..., 覆盖指令]。
    覆盖指令放最末，权重最高，压过官方人设锚定。
    """
    if provider != "zai":
        return body
    # 保留客户端自带的 system 作为追加指令，官方门禁 block 始终占位 0/1
    inject_official_system(body, preserve_user_system=True)
    # 让模型"遗忘"官方人设：在 system 末尾追加强覆盖指令
    apply_forgetting_directive(body)
    return body


def _is_captcha_error(text: str) -> bool:
    low = text.lower()
    return "captcha" in low or "verify token" in low or "verify failed" in low


def _is_exhausted(status_code: int, text: str) -> bool:
    if status_code in (402,):
        return True
    low = text.lower()
    return any(k in low for k in _EXHAUST_KEYWORDS)


def _mark(account: Account, status_value: str, error: str | None = None) -> None:
    account.status = status_value
    account.last_error = error
    if status_value == Status.COOLING:
        account.cooling_until = time.time() + settings.COOLING_SECONDS
    store.update_account(account)


def _last_user_text(body: dict) -> str:
    for msg in reversed(body.get("messages") or []):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    return part.get("text", "")
    return ""


@router.get("/v1/models", dependencies=[Depends(verify_gateway_key)])
async def list_models():
    """列出可用模型（兼容 OpenAI 和 Anthropic 格式）。"""
    return {
        "object": "list",
        "data": [
            {"id": i, "object": "model", "type": "model", "display_name": i, "created_at": "2025-01-01T00:00:00Z", "created": 1735689600, "owned_by": "zai"}
            for i in AVAILABLE_MODELS
        ],
    }

async def pipe_anthropic_response(resp: httpx.Response, cm: Any, client: httpx.AsyncClient, req_id: str):
    content_type = resp.headers.get("content-type", "application/json")
    status_code = resp.status_code
    
    async def _body_iter():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
            logs.req_ok(req_id)
        except Exception as err:
            logs.req_err(req_id, f"流传输中断: {err}")
        finally:
            await cm.__aexit__(None, None, None)
            await client.aclose()

    out_headers = {"Cache-Control": "no-cache"}
    return StreamingResponse(_body_iter(), status_code=status_code, media_type=content_type, headers=out_headers)


_NEXT_ACCOUNT = object()


async def _try_account(req_id: str, account: Account, body: dict, incoming_headers: dict, port: int, formatter: Callable):
    needs_captcha = account.provider == "zai" and account.mode == "jwt"
    payload = json.dumps(body).encode("utf-8")

    for attempt in range(MAX_CAPTCHA_RETRIES):
        verify_param = None
        if needs_captcha:
            try:
                verify_param = await captcha_manager.get_verify_param(port)
            except Exception as err:
                logs.req_err(req_id, f"人机校验失败: {err}")
                return JSONResponse({"error": {"message": f"无法完成人机校验: {err}", "type": "captcha_error"}}, status_code=500)

        try:
            url, headers = build_request(account, body, verify_param, incoming_headers)
        except RuntimeError as err:
            _mark(account, Status.INVALID, str(err))
            logs.warn(req_id, f"账号 {account.name} 凭证无效，切换下一个")
            return _NEXT_ACCOUNT

        client: object | None = None
        try:
            resp, cm, client = await _open_upstream(url, headers, payload, body, account.provider)
        except httpx.HTTPError as err:
            _mark(account, Status.COOLING, f"连接失败: {err}")
            logs.warn(req_id, f"账号 {account.name} 连接失败，切换下一个")
            return _NEXT_ACCOUNT
        except Exception as err:  # Node 反代连接错误等
            _mark(account, Status.COOLING, f"连接失败: {err}")
            logs.warn(req_id, f"账号 {account.name} 连接失败（反代），切换下一个")
            return _NEXT_ACCOUNT

        status_code = resp.status_code

        if status_code >= 400:
            text = (await resp.aread()).decode("utf-8", "ignore")
            await cm.__aexit__(None, None, None)
            await client.aclose()

            if status_code == 403 and _is_captcha_error(text) and needs_captcha:
                captcha_manager.invalidate()
                logs.warn(req_id, f"账号 {account.name} 验证码失效，刷新重试")
                continue

            if _is_exhausted(status_code, text):
                _mark(account, Status.EXHAUSTED, "额度已用完")
                logs.warn(req_id, f"账号 {account.name} 额度用完，切换下一个")
                asyncio.create_task(_safe_refresh(account))
                return _NEXT_ACCOUNT

            if status_code in (401, 403):
                _mark(account, Status.INVALID, f"鉴权失败 HTTP {status_code}")
                logs.warn(req_id, f"账号 {account.name} 鉴权失败 {status_code}，切换下一个")
                return _NEXT_ACCOUNT

            if status_code == 429:
                _mark(account, Status.COOLING, "上游限流 429")
                logs.warn(req_id, f"账号 {account.name} 被限流 429，切换下一个")
                return _NEXT_ACCOUNT

            account.fail_count += 1
            store.update_account(account)
            logs.req_err(req_id, f"上游错误 HTTP {status_code}（账号 {account.name}）")
            try:
                err_json = json.loads(text)
            except ValueError:
                err_json = {"error": {"message": text[:500], "type": "upstream_error"}}
            return JSONResponse(err_json, status_code=status_code)

        # 成功记录
        account.use_count += 1
        account.last_used_at = time.time()
        if account.status in (Status.COOLING, Status.EXHAUSTED):
            account.status = Status.ACTIVE
        store.update_account(account)
        asyncio.create_task(_safe_refresh(account))

        # 调用 formatter，formatter 负责消费 resp 和清理 client
        return await formatter(resp, cm, client, req_id, body)

    logs.warn(req_id, f"账号 {account.name} 验证码连续失败，切换下一个")
    return _NEXT_ACCOUNT


async def run_with_rotation(req: Request, provider: str, body: dict, formatter: Callable):
    req_id = secrets.token_hex(3)
    logs.req(req_id, str(body.get("model") or "-"), bool(body.get("stream")), _last_user_text(body))

    incoming_headers = dict(req.headers)
    port = req.url.port or settings.PORT
    tried: set[str] = set()

    for _ in range(MAX_ACCOUNT_ATTEMPTS):
        account = store.select(provider, skip_ids=tried)
        if account is None:
            break
        tried.add(account.id)

        result = await _try_account(req_id, account, body, incoming_headers, port, formatter)
        if result is _NEXT_ACCOUNT:
            continue
        return result

    logs.req_err(req_id, "无可用账号 / 额度均已耗尽")
    return JSONResponse(
        {"error": {"message": "所有账号均不可用或额度已用完，请在后台检查账号状态", "type": "no_available_account"}},
        status_code=503,
    )


@router.post("/v1/messages", dependencies=[Depends(verify_gateway_key)])
async def messages(request: Request):
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"error": {"message": "请求体不是合法 JSON", "type": "invalid_request"}}, status_code=400)

    provider = _detect_provider(body, request.headers)
    body = _normalize_body(body)
    body = _inject_gateway_system(body, provider)

    async def _anthropic_formatter(resp, cm, client, req_id, final_body):
        return await pipe_anthropic_response(resp, cm, client, req_id)

    return await run_with_rotation(request, provider, body, _anthropic_formatter)


@router.post("/v1/chat/completions", dependencies=[Depends(verify_gateway_key)])
async def chat_completions(request: Request):
    try:
        openai_body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"error": {"message": "请求体不是合法 JSON", "type": "invalid_request"}}, status_code=400)

    provider = _detect_provider(openai_body, request.headers)
    anthropic_body = convert_openai_to_anthropic(openai_body)
    anthropic_body = _normalize_body(anthropic_body)
    anthropic_body = _inject_gateway_system(anthropic_body, provider)
    requested_model = openai_body.get("model", "")

    async def _openai_formatter(resp, cm, client, req_id, final_body):
        is_stream = final_body.get("stream", False)
        
        if is_stream:
            # 流式处理
            async def _cleanup_wrapper():
                try:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
                    logs.req_ok(req_id)
                except Exception as err:
                    logs.req_err(req_id, f"流传输中断: {err}")
                finally:
                    await cm.__aexit__(None, None, None)
                    await client.aclose()
            
            return await openai_streaming_response(_cleanup_wrapper(), requested_model)
        else:
            # 非流式处理
            try:
                text = (await resp.aread()).decode("utf-8")
                anthropic_json = json.loads(text)
                openai_json = convert_anthropic_to_openai(anthropic_json, requested_model)
                logs.req_ok(req_id)
                return JSONResponse(openai_json)
            except Exception as err:
                logs.req_err(req_id, f"上游响应解析失败: {err}")
                return JSONResponse({"error": {"message": "上游响应解析失败", "type": "upstream_error"}}, status_code=502)
            finally:
                await cm.__aexit__(None, None, None)
                await client.aclose()

    return await run_with_rotation(request, provider, anthropic_body, _openai_formatter)


async def _safe_refresh(account: Account) -> None:
    try:
        if account.provider == "zai":
            await fetch_quota(account)
    except Exception:
        pass
