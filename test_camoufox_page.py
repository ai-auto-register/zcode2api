"""测试 Camoufox 能否正常加载页面并执行 JS。"""
import asyncio
from app import settings

async def main():
    settings.CAMOUFOX_HEADLESS = True
    from app.camoufox_solver import CamoufoxSolver
    s = CamoufoxSolver()
    print("启动 camoufox...")
    await s._ensure()
    page = await s._context.new_page()

    # 测试1: 简单页面
    print("\n1. 加载简单页面...")
    await page.set_content("<html><body><script>window.__test=42</script></body></html>", wait_until="load")
    val = await page.evaluate("() => window.__test")
    print(f"   window.__test = {val}")

    # 测试2: 加载求解页面（不包含 SDK）
    print("\n2. 加载求解页面（无SDK）...")
    await page.goto("http://127.0.0.1:3000/static/captcha-solver.html", wait_until="load", timeout=15000)
    ready = await page.evaluate("() => window.__solverReady")
    print(f"   __solverReady = {ready}")

    # 测试3: 检查 SDK 是否加载
    import asyncio as aio
    await aio.sleep(3)
    has_sdk = await page.evaluate("() => typeof window.initAliyunCaptcha === 'function'")
    print(f"   initAliyunCaptcha available: {has_sdk}")
    sdk_ready = await page.evaluate("() => window.__sdkReady")
    print(f"   __sdkReady: {sdk_ready}")

    # 测试4: 检查 console 消息
    msgs = []
    page.on("console", lambda m: msgs.append(f"[{m.type}] {m.text[:100]}"))
    await aio.sleep(1)
    print(f"   console messages: {len(msgs)}")
    for m in msgs[:5]:
        print(f"   {m}")

    await page.close()
    await s.close()
    print("\n完成")

asyncio.run(main())
