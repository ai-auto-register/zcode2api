"""获取 zcode configs 完整 captcha 配置，找 NVC 需要的 appkey/scene。"""
import asyncio, json, httpx

async def main():
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get("https://zcode.z.ai/api/v1/client/configs?app_version=3.0.0&platform=win32")
        d = r.json()
        print(json.dumps(d, ensure_ascii=False, indent=2))

asyncio.run(main())
