import asyncio
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(headless=False, os=['macos'], humanize=False, geoip=False, i_know_what_im_doing=True, main_world_eval=True) as b:
        ctx = await b.new_context()
        page = await ctx.new_page()
        page.on("console", lambda m: print(f"[{m.type}] {m.text[:200]}") if m.type in ("log","error","warning") else None)

        await page.goto("http://127.0.0.1:3000/static/captcha-solver.html", wait_until="load", timeout=30000)
        # 等 SDK
        for _ in range(100):
            ready = await page.evaluate("mw:window.__sdkReady")
            if ready: break
            await asyncio.sleep(0.3)
        print("SDK ready")

        # 调用求解
        config = '{"enabled":true,"prefix":"no8xfe","region":"sgp","sceneId":"11xygtvd"}'
        await page.evaluate(f"mw:window.__solveCaptcha(60000, {config})")

        # 轮询结果
        for i in range(120):
            result = await page.evaluate("mw:window.__solveResult")
            if result:
                print(f"\n__solveResult: {result}")
                # 如果 result 是对象，看它的结构
                if isinstance(result, dict):
                    print(f"  ok: {result.get('ok')}")
                    param = result.get('param', '')
                    print(f"  param length: {len(param) if param else 0}")
                    print(f"  param[:80]: {param[:80] if param else ''}")
                    print(f"  error: {result.get('error')}")
                break
            await asyncio.sleep(0.5)
        else:
            print("超时，无结果")

        await page.close()

asyncio.run(main())
