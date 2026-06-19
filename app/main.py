"""FastAPI 应用工厂 + 生命周期。"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import settings
from . import logs
from .captcha import captcha_manager
from .quota import monitor
from .rnet_client import rnet_client
from .solver_server import solver_server
from .routes import admin_api, gateway, internal_api, pages

# 修正 Windows 中文控制台可能出现的乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def _display_host() -> str:
    # 0.0.0.0 / 空地址在浏览器中不可直接访问，展示为 127.0.0.1
    host = (settings.HOST or "").strip()
    return "127.0.0.1" if host in ("", "0.0.0.0", "::") else host


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor.start()
    if solver_server.enabled:
        # Python 内部回调地址：Node jsdom 桩把请求转发到这里，由 rnet 发出
        callback = f"http://127.0.0.1:{settings.PORT}/internal/rnet-proxy"
        try:
            await solver_server.start(rnet_callback=callback)
        except Exception as err:  # noqa: BLE001
            logs.warn("solver", f"Node 服务启动失败，将退回直连模式: {err}")
    # camoufox 模式：服务就绪后后台预启动浏览器池（服务此时已开始监听）
    _pool_task = asyncio.create_task(captcha_manager.startup())
    base = f"http://{_display_host()}:{settings.PORT}"
    logs.banner([
        f"{logs._B}{logs._MAG}zcode2api{logs._R} {logs._DIM}v{settings.APP_VERSION} · Python{logs._R}",
        f"{logs._DIM}后台管理{logs._R}  {logs._C}{base}/admin/login{logs._R}",
        f"{logs._DIM}对话端点{logs._R}  {logs._C}{base}/v1/messages{logs._R}",
    ])
    try:
        yield
    finally:
        _pool_task.cancel()
        await monitor.stop()
        await captcha_manager.close()
        if solver_server.enabled:
            await solver_server.stop()
        await rnet_client.close()


def create_app() -> FastAPI:
    app = FastAPI(title="zcode2api", version=settings.APP_VERSION, lifespan=lifespan)

    app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

    app.include_router(pages.router)
    app.include_router(admin_api.router)
    app.include_router(gateway.router)
    app.include_router(internal_api.router)
    return app


app = create_app()
