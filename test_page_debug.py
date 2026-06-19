import asyncio, httpx
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(headless=True, os=['macos'], humanize=False, geoip=False, i_know_what_im_doing=True) as b:
        ctx = await b.new_context()
        page = await ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:300]))
        page.on("console", lambda m: print(f"[console.{m.type}] {m.text[:200]}") if m.type in ("error","warning","log") else None)

        await page.goto("http://127.0.0.1:3000/static/captcha-solver.html", wait_until="load", timeout=30000)
        await asyncio.sleep(5)

        ready = await page.evaluate("() => window.__solverReady")
        sdk_ready = await page.evaluate("() => window.__sdkReady")
        has_init = await page.evaluate("() => typeof window.initAliyunCaptcha")
        has_solve = await page.evaluate("() => typeof window.__solveCaptcha")
        print(f"__solverReady: {ready}")
        print(f"__sdkReady: {sdk_ready}")
        print(f"initAliyunCaptcha: {has_init}")
        print(f"__solveCaptcha: {has_solve}")
        print(f"pageerrors: {len(errs)}")
        for e in errs[:5]:
            print(f"  {e}")

        # 检查所有 script 标签
        scripts = await page.evaluate("() => Array.from(document.querySelectorAll('script')).map(s => s.src || s.textContent.slice(0,50)).join(' | ')")
        print(f"scripts: {scripts[:300]}")

        await page.close()

asyncio.run(main())
