import asyncio
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(headless=True, os=['macos'], humanize=False, geoip=False, i_know_what_im_doing=True) as b:
        ctx = await b.new_context()
        page = await ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await page.goto("http://127.0.0.1:3000/internal/aliyun-sdk", wait_until="load", timeout=20000)
        await asyncio.sleep(1)
        print("pageerrors:", len(errs))
        for e in errs[:5]:
            print("  ", e)
        keys = await page.evaluate("""() => Object.keys(window).filter(k => k.toLowerCase().includes('captcha') || k.toLowerCase().includes('aliyun')).join(',')""")
        print("captcha/aliyun keys:", keys)
        await page.close()

asyncio.run(main())
