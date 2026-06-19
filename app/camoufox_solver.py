"""Camoufox 求解器：用真实浏览器环境运行阿里云无痕验证 SDK。

jsdom 求解器无法通过 cloudauth-device 设备指纹检测（F001），
Camoufox 提供真实浏览器指纹，可绕过检测拿到含 securityToken 的完整 verifyParam。

流程：
1. Camoufox 打开 http://127.0.0.1:PORT/static/captcha-solver.html
2. 页面通过 /internal/aliyun-sdk 反代加载阿里云 SDK（同源，无跨域）
3. 页面自动 fetch zcode configs 获取 captcha 配置
4. 调用 initAliyunCaptcha + startTracelessVerification 求解
5. success 回调返回含 securityToken 的 verifyParam

浏览器池：常驻多个浏览器实例，启动时预加载页面+SDK，求解时直接复用。
"""

from __future__ import annotations

import asyncio
import json as _json

from . import logs, settings


class _BrowserSlot:
    """单个浏览器实例：持有 context 和预加载好的 page。"""

    def __init__(self, context, index: int) -> None:
        self.context = context
        self.index = index
        self.page = None

    async def prepare(self, port: int) -> None:
        """打开页面、设置 route、加载 SDK，直到 __sdkReady。"""
        self.page = await self.context.new_page()
        await self._setup_route(self.page)
        self._setup_listeners(self.page)

        page_url = f"http://127.0.0.1:{port}/static/captcha-solver.html"
        await self.page.goto(page_url, wait_until="load", timeout=30000)
        logs.ok("camoufox", f"#{self.index} 页面已加载，等待 SDK...")

        ready = False
        for _ in range(100):
            ready = await self.page.evaluate("mw:window.__sdkReady")
            if ready:
                break
            await asyncio.sleep(0.3)
        if not ready:
            raise RuntimeError(f"#{self.index} SDK 加载超时")
        logs.ok("camoufox", f"#{self.index} SDK 已就绪")

    async def reload(self, port: int) -> None:
        """页面出错时重新加载。"""
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
        await self.prepare(port)

    async def solve(self, config: dict) -> str:
        """在已加载好的页面上调用 __solveCaptcha，轮询结果。"""
        assert self.page is not None
        timeout_ms = int(settings.CAMOUFOX_SOLVE_TIMEOUT * 1000)
        config_json = _json.dumps(config)
        await self.page.evaluate(
            f"mw:window.__solveCaptcha({timeout_ms}, {config_json})"
        )

        result = None
        for _ in range(int(settings.CAMOUFOX_SOLVE_TIMEOUT * 2)):
            result = await self.page.evaluate("mw:window.__solveResult")
            if result:
                break
            await asyncio.sleep(0.5)

        if not result or not result.get("ok"):
            raise RuntimeError(result.get("error") if result else "求解返回空结果")

        param = result.get("param", "")
        if not param:
            raise RuntimeError("求解返回空 verify_param")

        logs.ok("camoufox", f"#{self.index} 求解成功，verifyParam 长度={len(param)}")
        return param

    def _setup_listeners(self, page) -> None:
        def _safe_pageerror(err):
            try:
                logs.warn("camoufox", f"#{self.index} [pageerror] {str(err)[:300]}")
            except Exception:
                pass
        try:
            page.on("pageerror", _safe_pageerror)
        except Exception:
            pass
        page.on("console", lambda msg: logs.warn("camoufox", f"#{self.index} [console.{msg.type}] {msg.text[:300]}") if msg.type in ("log", "error", "warning") else None)

        def _on_requestfailed(req):
            if "captcha" in req.url.lower() or "aliyun" in req.url.lower() or "cloudauth" in req.url.lower():
                logs.warn("camoufox", f"#{self.index} [reqfail] {req.method} {req.url[:100]} failure={req.failure}")
        def _on_response(resp):
            url = resp.url.lower()
            if "captcha" in url or "aliyun" in url or "cloudauth" in url:
                logs.ok("camoufox", f"#{self.index} [resp] {resp.status} {resp.url[:100]}")
        page.on("requestfailed", _on_requestfailed)
        page.on("response", _on_response)

    async def _setup_route(self, page) -> None:
        reverse_url = (settings.REVERSE_URL or "").strip().rstrip("/")
        if not reverse_url:
            return

        import httpx as _httpx

        async def _rewrite_route(route):
            req = route.request
            url = req.url
            if not (
                url.startswith("http")
                and ("captcha" in url or "cloudauth" in url)
                and not url.startswith(reverse_url)
                and "127.0.0.1" not in url
                and "localhost" not in url
            ):
                await route.continue_()
                return

            if req.method == "OPTIONS":
                await route.fulfill(status=200, headers={
                    "access-control-allow-origin": "*",
                    "access-control-allow-methods": "*",
                    "access-control-allow-headers": "*",
                })
                return

            new_url = reverse_url + "/" + url
            logs.ok("camoufox", f"#{self.index} [rewrite] {req.method} {url[:80]} -> {new_url[:80]}")
            try:
                skip_req = {"host", "origin", "referer", "cookie",
                            "content-length", "transfer-encoding", "connection"}
                hdrs = {k: v for k, v in req.headers.items()
                        if k.lower() not in skip_req}
                body = req.post_data
                if isinstance(body, str):
                    body = body.encode("utf-8")
                proxy = settings.PROXY_URL or None
                async with _httpx.AsyncClient(timeout=30, proxy=proxy, verify=settings.TLS_VERIFY) as cx:
                    resp = await cx.request(req.method, new_url, headers=hdrs, content=body)
                skip_resp = {"content-encoding", "content-length",
                             "transfer-encoding", "connection"}
                out_hdrs = {k: v for k, v in resp.headers.items()
                            if k.lower() not in skip_resp}
                out_hdrs["access-control-allow-origin"] = "*"
                await route.fulfill(
                    status=resp.status_code, headers=out_hdrs, body=resp.content)
            except Exception as e:
                logs.warn("camoufox", f"#{self.index} [rewrite] proxy failed, fallback direct: {e}")
                await route.continue_()

        await page.route("**/*", _rewrite_route)

    async def close(self) -> None:
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
        try:
            await self.context.__aexit__(None, None, None)
        except Exception:
            pass


class CamoufoxSolver:
    """Camoufox 浏览器求解器，用真实浏览器指纹通过阿里云无痕验证。"""

    def __init__(self) -> None:
        self._slots: list[_BrowserSlot] = []
        self._idle: asyncio.Queue[_BrowserSlot] | None = None
        self._lock = asyncio.Lock()
        self._started = False

    async def _ensure(self) -> None:
        if self._started:
            return
        async with self._lock:
            if self._started:
                return
            try:
                from camoufox.async_api import AsyncCamoufox
            except ImportError as e:
                raise RuntimeError(
                    "camoufox 未安装，请执行: pip install camoufox && python -m camoufox fetch"
                ) from e

            pool_size = max(1, settings.CAMOUFOX_POOL_SIZE)
            port = settings.PORT
            kwargs = {
                "headless": settings.CAMOUFOX_HEADLESS,
                "os": ["macos", "windows"],
                "humanize": False,
                "geoip": False,
                "i_know_what_im_doing": True,
                "main_world_eval": True,
            }
            if settings.PROXY_URL:
                kwargs["proxy"] = {"server": settings.PROXY_URL}

            logs.ok("camoufox", f"正在并行启动浏览器池 size={pool_size} headless={settings.CAMOUFOX_HEADLESS}...")

            async def _spawn_one(i: int) -> _BrowserSlot:
                t0 = asyncio.get_event_loop().time()
                ctx = await AsyncCamoufox(**kwargs).__aenter__()
                slot = _BrowserSlot(ctx, i + 1)
                await slot.prepare(port)
                t1 = asyncio.get_event_loop().time()
                logs.ok("camoufox", f"浏览器 #{i+1}/{pool_size} 已就绪（耗时 {t1-t0:.1f}s）")
                return slot

            t_total = asyncio.get_event_loop().time()
            self._slots = await asyncio.gather(*(_spawn_one(i) for i in range(pool_size)))
            t_done = asyncio.get_event_loop().time()

            self._idle = asyncio.Queue()
            for slot in self._slots:
                self._idle.put_nowait(slot)
            self._started = True
            logs.ok("camoufox", f"浏览器池就绪（{pool_size} 个实例，页面已预加载，总耗时 {t_done-t_total:.1f}s）")

    async def solve(self, config: dict, port: int | None = None) -> str:
        """求解 verifyParam。复用已预加载好页面+SDK 的浏览器实例。"""
        await self._ensure()
        assert self._idle is not None

        slot = await self._idle.get()
        try:
            return await slot.solve(config)
        except Exception:
            # 求解失败时尝试重载页面，下次复用
            try:
                await slot.reload(settings.PORT)
            except Exception:
                pass
            raise
        finally:
            await self._idle.put(slot)

    async def close(self) -> None:
        for slot in self._slots:
            try:
                await slot.close()
            except Exception:
                pass
        self._slots = []
        self._idle = None
        self._started = False
