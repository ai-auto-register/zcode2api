import asyncio
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(headless=True, os=['macos'], humanize=False, geoip=False, i_know_what_im_doing=True, main_world_eval=True) as b:
        ctx = await b.new_context()
        page = await ctx.new_page()
        page.on("console", lambda m: print(f"[{m.type}] {m.text[:150]}"))

        await page.goto("http://127.0.0.1:3000/static/captcha-solver.html", wait_until="load", timeout=30000)
        await asyncio.sleep(3)

        # isolated world
        print("=== isolated ===")
        print("1+1:", await page.evaluate("() => 1+1"))
        print("title:", await page.evaluate("() => document.title"))
        print("initAliyunCaptcha:", await page.evaluate("() => typeof window.initAliyunCaptcha"))
        print("__solverReady:", await page.evaluate("() => window.__solverReady"))

        # main world
        print("\n=== main world ===")
        print("mw 1+1:", await page.evaluate("mw:1+1"))
        print("mw initAliyunCaptcha:", await page.evaluate("mw:typeof window.initAliyunCaptcha"))
        print("mw __solverReady:", await page.evaluate("mw:window.__solverReady"))
        print("mw __sdkReady:", await page.evaluate("mw:window.__sdkReady"))
        print("mw __solveCaptcha:", await page.evaluate("mw:typeof window.__solveCaptcha"))

        await page.close()

asyncio.run(main())
