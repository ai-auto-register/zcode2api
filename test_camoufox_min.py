"""最小测试：确认 camoufox 能启动并打开页面。"""
import asyncio
from app import settings

async def main():
    settings.CAMOUFOX_HEADLESS = True
    from app.camoufox_solver import CamoufoxSolver
    s = CamoufoxSolver()
    print("启动 camoufox...")
    await s._ensure()
    print("成功！浏览器已启动")
    page = await s._context.new_page()
    print("打开 about:blank...")
    await page.goto("about:blank")
    print("页面标题:", await page.title())
    await page.close()
    await s.close()
    print("已关闭")

asyncio.run(main())
