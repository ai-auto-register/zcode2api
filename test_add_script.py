import asyncio
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(headless=True, os=['macos'], humanize=False, geoip=False, i_know_what_im_doing=True) as b:
        ctx = await b.new_context()
        page = await ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        # goto 空白页
        await page.goto("about:blank")
        # add_script_tag 加载 SDK
        print("add_script_tag...")
        try:
            await page.add_script_tag(url="http://127.0.0.1:3000/internal/aliyun-sdk")
            print("add_script_tag done")
        except Exception as e:
            print(f"add_script_tag failed: {e}")
        await asyncio.sleep(2)
        has = await page.evaluate("() => typeof window.initAliyunCaptcha")
        print("initAliyunCaptcha:", has)
        print("pageerrors:", len(errs))
        for e in errs[:5]:
            print("  ", e)
        await page.close()

asyncio.run(main())
