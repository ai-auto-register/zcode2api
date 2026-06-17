import httpx
import asyncio

async def run():
    client = httpx.AsyncClient(verify=False)
    headers = {'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNjU2MTQyMTYtZGI2Ny00OWU3LTg4NDItY2Q2ODRmNDBlZThkIiwic3ViIjoiNjU2MTQyMTYtZGI2Ny00OWU3LTg4NDItY2Q2ODRmNDBlZThkIiwiaWF0IjoxNzgxNjExNTQ3fQ.ATm04Wa2_jk_w5D3B0K0Fz1YYQPuZEUijho-ju5dNyQ'}
    
    res = await client.get('https://zcode.z.ai/api/v1/zcode-plan/billing/balance', headers=headers)
    print("BALANCE:", res.status_code, res.text)
    
    res = await client.get('https://zcode.z.ai/api/v1/zcode-plan/usage', headers=headers)
    print("USAGE:", res.status_code, res.text)

asyncio.run(run())
