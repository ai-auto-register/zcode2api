"""Z.AI OAuth 登录流程。

主要供 CLI `login zai` 使用：发起 OAuth → 轮询 → 兑换 API Key。
"""

from __future__ import annotations

import secrets

import httpx

from . import logs


class ZaiAuthFlow:
    def __init__(self, api_base: str = "https://zcode.z.ai/api/v1") -> None:
        self.api_base = api_base
        self.poll_token = secrets.token_hex(32)

    async def init(self) -> tuple[str, str]:
        logs.step("oauth", "发起 OAuth 登录流程...")
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                f"{self.api_base}/oauth/cli/init",
                headers={
                    "Authorization": f"Bearer {self.poll_token}",
                    "Content-Type": "application/json",
                },
                json={"provider": "zai"},
            )
        res.raise_for_status()
        data = res.json().get("data") or {}
        flow_id, authorize_url = data.get("flow_id"), data.get("authorize_url")
        if not flow_id or not authorize_url:
            raise RuntimeError("返回的 OAuth 流程数据不完整")
        logs.ok("oauth", f"OAuth 已发起: flow_id={flow_id}")
        logs.step("oauth", f"请在浏览器中打开以下地址完成授权:\n{authorize_url}")
        return flow_id, authorize_url

    async def poll(self, flow_id: str) -> dict:
        logs.info("oauth", f"轮询 OAuth 状态: flow_id={flow_id}")
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.get(
                f"{self.api_base}/oauth/cli/poll/{flow_id}",
                headers={"Authorization": f"Bearer {self.poll_token}"},
            )
        res.raise_for_status()
        data = res.json().get("data") or {}
        status = data.get("status", "unknown")
        logs.info("oauth", f"OAuth 轮询结果: status={status}")
        return data

    async def exchange_api_key(self, access_token: str) -> str:
        """OAuth access_token → 业务 token → 机构/项目 → API Key。"""
        logs.step("oauth", "开始兑换 API Key...")
        async with httpx.AsyncClient(timeout=30) as client:
            logs.info("oauth", "POST https://api.z.ai/api/auth/z/login (兑换业务凭证)")
            login = await client.post(
                "https://api.z.ai/api/auth/z/login",
                headers={"Content-Type": "application/json"},
                json={"token": access_token},
            )
            login.raise_for_status()
            biz = (login.json().get("data") or {})
            biz_token = biz.get("access_token") or biz.get("accessToken")
            if not biz_token:
                raise RuntimeError("返回数据中不含业务凭证")
            logs.ok("oauth", "业务凭证获取成功")

            logs.info("oauth", "GET /api/biz/customer/getCustomerInfo (获取机构信息)")
            info = await client.get(
                "https://api.z.ai/api/biz/customer/getCustomerInfo",
                headers={"Authorization": f"Bearer {biz_token}"},
            )
            info.raise_for_status()
            orgs = (info.json().get("data") or {}).get("organizations") or []
            org = next((o for o in orgs if "默认机构" in (o.get("organizationName") or "")), None) or (orgs[0] if orgs else None)
            if not org:
                raise RuntimeError("找不到可用的机构")
            projects = org.get("projects") or []
            proj = next((p for p in projects if "默认项目" in (p.get("projectName") or "")), None) or (projects[0] if projects else None)
            if not proj:
                raise RuntimeError("找不到可用的项目")

            org_id, proj_id = org["organizationId"], proj["projectId"]
            org_name = org.get("organizationName", org_id)
            proj_name = proj.get("projectName", proj_id)
            logs.info("oauth", f"机构={org_name} 项目={proj_name}")
            key_url = f"https://api.z.ai/api/biz/v1/organization/{org_id}/projects/{proj_id}/api_keys"

            logs.info("oauth", "GET 已有 API Key 列表")
            keys_res = await client.get(key_url, headers={"Authorization": f"Bearer {biz_token}"})
            keys_res.raise_for_status()
            keys = keys_res.json().get("data") or []
            key_obj = next((k for k in keys if k.get("name") == "zcode-api-key"), None)
            if not key_obj:
                logs.info("oauth", "未找到现有 Key，创建新的 zcode-api-key")
                create = await client.post(
                    key_url,
                    headers={"Authorization": f"Bearer {biz_token}", "Content-Type": "application/json"},
                    json={"name": "zcode-api-key"},
                )
                create.raise_for_status()
                key_obj = create.json().get("data")
                logs.ok("oauth", "新 API Key 创建成功")
            else:
                logs.info("oauth", "使用已有的 zcode-api-key")

            api_key = (key_obj or {}).get("apiKey")
            if not api_key:
                raise RuntimeError("获取 API Key 失败")

            logs.info("oauth", f"解密 Secret Key: {key_url}/copy/{api_key[:8]}...")
            copy = await client.get(
                f"{key_url}/copy/{api_key}",
                headers={"Authorization": f"Bearer {biz_token}"},
            )
            copy.raise_for_status()
            secret_key = (copy.json().get("data") or {}).get("secretKey")
            if not secret_key:
                raise RuntimeError("未能解密 Secret Key")
        logs.ok("oauth", f"API Key 兑换完成: {api_key[:8]}...{secret_key[-4:]}")
        return f"{api_key}.{secret_key}"
