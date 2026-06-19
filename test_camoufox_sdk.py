"""最小测试：camoufox 能否加载阿里云 SDK。"""
import asyncio
from app import settings

async def main():
    settings.CAMOUFOX_HEADLESS = True
    from app.camoufox_solver import CamoufoxSolver
    s = CamoufoxSolver()
    print("启动 camoufox...")
    await s._ensure()
    page = await s._context.new_page()
    errors = []
    page.on("console", lambda msg: print(f"[console.{msg.type}] {msg.text[:300]}"))
    page.on("pageerror", lambda err: print(f"[pageerror] {err}") or errors.append(str(err)))
    page.on("requestfailed", lambda req: print(f"[reqfail] {req.url[:80]} {req.failure}"))

    print("\n1. goto about:blank")
    await page.goto("about:blank")

    print("2. add_script_tag 阿里云 SDK...")
    try:
        await page.add_script_tag(url="https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js")
        print("3. add_script_tag 完成")
    except Exception as e:
        print(f"3. add_script_tag 失败: {e}")

    print("4. 检查 initAliyunCaptcha...")
    has = await page.evaluate("() => typeof window.initAliyunCaptcha === 'function'")
    print(f"   initAliyunCaptcha 可用: {has}")

    # 试直接 goto SDK url
    print("\n5. 直接 goto SDK URL...")
    try:
        resp = await page.goto("https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js", wait_until="domcontentloaded", timeout=20000)
        print(f"   status: {resp.status if resp else '?'}")
        print(f"   body 长度: {len(await page.evaluate('document.body.innerText'))}")
    except Exception as e:
        print(f"   goto 失败: {e}")

    await page.close()
    await s.close()

asyncio.run(main())
