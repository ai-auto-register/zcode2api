"""验证码 WebSocket 端点 + 页面路由。"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from .. import settings
from ..captcha import captcha_manager

router = APIRouter()


@router.websocket("/captcha/ws")
async def captcha_ws(ws: WebSocket):
    await ws.accept()
    captcha_manager.register_ws(ws)
    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")
            if msg_type == "result":
                param = data.get("verifyParam")
                if param:
                    captcha_manager.submit_result(param)
            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        captcha_manager.unregister_ws(ws)


@router.get("/admin/captcha", include_in_schema=False)
async def captcha_page():
    path = settings.STATIC_DIR / "admin" / "captcha.html"
    if not path.exists():
        return HTMLResponse("<h1>页面不存在</h1>", status_code=404)
    body = path.read_text(encoding="utf-8").replace("{{APP_VERSION}}", settings.APP_VERSION)
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})
