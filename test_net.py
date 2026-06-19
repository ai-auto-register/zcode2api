import asyncio
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(headless=True, os=['macos'], humanize=False, geoip=False, i_know_what_im_doing=True, main_world_eval=True) as b:
        ctx = await b.new_context()
        page = await ctx.new_page()
        page.on("console", lambda m: print(f"[{m.type}] {m.text[:200]}"))
        page.on("requestfailed", lambda req: print(f"[REQFAIL] {req.url[:100]} {req.failure}"))
        page.on("response", lambda resp: print(f"[RESP] {resp.status} {resp.url[:100]}") if 'captcha' in resp.url.lower() or 'aliyun' in resp.url.lower() else None)

        await page.goto("http://127.0.0.1:3000/static/captcha-solver.html", wait_until="load", timeout=30000)
        await asyncio.sleep(3)
        print("SDK ready, calling solveCaptcha...")

        result = await page.evaluate("""mw:(async () => {
            try {
                var config = {enabled:true, prefix:'no8xfe', region:'sgp', sceneId:'11xygtvd'};
                var p = await window.__solveCaptcha(60000, config);
                return {ok:true, param:p};
            } catch(e) {
                return {ok:false, error:String(e)};
            }
        })()""")
        print(f"\nResult: {result}")
        await page.close()

asyncio.run(main())
