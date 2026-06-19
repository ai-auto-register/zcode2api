import asyncio
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(headless=True, os=['macos'], humanize=False, geoip=False, i_know_what_im_doing=True) as b:
        ctx = await b.new_context()
        page = await ctx.new_page()
        page.on("console", lambda m: print(f"[{m.type}] {m.text[:150]}"))
        page.on("pageerror", lambda e: print(f"[pageerror] {e}"))

        await page.goto("http://127.0.0.1:3000/static/captcha-solver.html", wait_until="load", timeout=30000)
        await asyncio.sleep(3)

        print("evaluate 1+1:", await page.evaluate("() => 1+1"))
        print("evaluate location:", await page.evaluate("() => window.location.href"))
        print("evaluate document.title:", await page.evaluate("() => document.title"))
        print("evaluate typeof initAliyunCaptcha:", await page.evaluate("() => typeof window.initAliyunCaptcha"))
        print("evaluate window.__sdkReady:", await page.evaluate("() => window.__sdkReady"))
        print("evaluate window.__solverReady:", await page.evaluate("() => window.__solverReady"))
        # 列出 window 上所有自定义属性
        keys = await page.evaluate("""() => {
            var result = [];
            for (var k in window) { if (k.indexOf('captcha') !== -1 || k.indexOf('sdk') !== -1 || k.indexOf('solver') !== -1 || k.indexOf('Aliyun') !== -1 || k.indexOf('init') !== -1) result.push(k + '=' + typeof window[k]); }
            return result.join(', ');
        }""")
        print("window keys:", keys)

        await page.close()

asyncio.run(main())
