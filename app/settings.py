"""运行期配置：环境变量 + 默认值。

所有可调参数集中在此。账号与凭证不在此处，而是持久化到 data/ 目录（见 store.py）。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 项目根目录
ROOT_DIR = Path(__file__).resolve().parents[1]


def _resolve_path(env_name: str, default: str) -> Path:
    raw = (os.getenv(env_name, default) or default).strip()
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _int(env_name: str, default: int) -> int:
    try:
        return int(os.getenv(env_name, str(default)))
    except (TypeError, ValueError):
        return default


# ── 目录 ─────────────────────────────────────────────────────────────────────
DATA_DIR = _resolve_path("ZCODE_DATA_DIR", "data")
# 账号与设置持久化到本地 SQLite（与 grok2api 的 local 后端一致）
DB_PATH = DATA_DIR / "accounts.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
STATIC_DIR = Path(__file__).resolve().parent / "statics"

# ── 服务 ─────────────────────────────────────────────────────────────────────
PORT = _int("ZCODE_PORT", 3000)
HOST = os.getenv("ZCODE_HOST", "0.0.0.0")

# ── 鉴权 ─────────────────────────────────────────────────────────────────────
# 后台管理密码默认值，首次启动写入 data/accounts.db，之后以数据库（meta 表）为准。
DEFAULT_ADMIN_KEY = os.getenv("ZCODE_ADMIN_KEY", "zcode")

# ── 验证码缓存 ───────────────────────────────────────────────────────────────
CAPTCHA_CACHE_TTL = _int("CAPTCHA_CACHE_TTL", 45_000)          # ms
CAPTCHA_CONFIG_CACHE_TTL = _int("CAPTCHA_CONFIG_CACHE_TTL", 600_000)  # ms

# 阿里云无痕验证反向代理前缀（留空则直连阿里云）
REVERSE_URL = os.getenv("REVERSE_URL", "").strip().rstrip("/")

# 验证码求解（无浏览器：Node + jsdom 模拟浏览器环境，运行阿里云无痕 SDK）
# 求解后端：jsdom（默认，速度快但可能被设备指纹检测） | camoufox（真实浏览器指纹，通过率高）
CAPTCHA_SOLVER = os.getenv("ZCODE_CAPTCHA_SOLVER", "jsdom").strip().lower()
NODE_PATH = os.getenv("ZCODE_NODE_PATH", "node")
CAPTCHA_SOLVER_DIR = ROOT_DIR / "captcha_node"
CAPTCHA_SOLVER_JS = CAPTCHA_SOLVER_DIR / "solver.js"
CAPTCHA_SOLVE_RETRIES = _int("ZCODE_CAPTCHA_RETRIES", 4)
CAPTCHA_SOLVE_TIMEOUT = _int("ZCODE_CAPTCHA_TIMEOUT", 40)  # 每次求解超时（秒）

# camoufox 求解器（真实浏览器环境，绕过阿里云设备指纹检测）
# Camoufox 无头模式：1=无头（默认） | 0=有头（调试用）
CAMOUFOX_HEADLESS = os.getenv("ZCODE_CAMOUFOX_HEADLESS", "1").strip() not in ("0", "false", "False", "")
# camoufox 求解页面超时（秒）
CAMOUFOX_SOLVE_TIMEOUT = _int("ZCODE_CAMOUFOX_TIMEOUT", 60)
# camoufox 浏览器池大小（常驻浏览器实例数，并发求解时提高吞吐）
CAMOUFOX_POOL_SIZE = max(1, _int("ZCODE_CAMOUFOX_POOL_SIZE", 1))

# Node 求解/反代常驻 HTTP 服务
# 启用后：Python 通过 HTTP 调 Node 的 /solve 与 /messages；不再每次 spawn 子进程
SOLVER_SERVER_ENABLED = os.getenv("ZCODE_SOLVER_SERVER", "1").strip() not in ("0", "false", "False", "")
SOLVER_SERVER_JS = CAPTCHA_SOLVER_DIR / "server.js"
# 端口：留空时由 Python 自动选取一个空闲端口
SOLVER_PORT = _int("ZCODE_SOLVER_PORT", 0)
SOLVER_HOST = "127.0.0.1"
# zcode 上游请求是否经 rnet (Chrome131) 发送（zai provider；bigmodel 仍由 Python httpx 直连）
SOLVER_PROXY_ZAI = os.getenv("ZCODE_SOLVER_PROXY_ZAI", "1").strip() not in ("0", "false", "False", "")
# 调用 Node /solve 的 HTTP 超时（秒）
SOLVER_HTTP_TIMEOUT = _int("ZCODE_SOLVER_HTTP_TIMEOUT", 60)

# ── 用量监控 ─────────────────────────────────────────────────────────────────
# 后台自动刷新账号额度的间隔（秒）。0 表示关闭后台轮询，仅按需刷新。
QUOTA_REFRESH_INTERVAL = _int("ZCODE_QUOTA_REFRESH_INTERVAL", 60)
# 限流（cooling）冷却时长（秒）
COOLING_SECONDS = _int("ZCODE_COOLING_SECONDS", 300)

# ── 代理 ─────────────────────────────────────────────────────────────────────
# Node 验证码求解器的 HTTP(S) 代理
PROXY_URL = os.getenv("PROXY_URL", "").strip()

# ── TLS 校验 ───────────────────────────────────────────────────────────────
# 禁用 TLS 证书校验（调试 / 反代自签证书用）。1=禁用，0=启用校验（默认）
TLS_VERIFY = os.getenv("ZCODE_TLS_VERIFY", "1").strip() not in ("0", "false", "False", "")

# ── 上游端点 ─────────────────────────────────────────────────────────────────
UPSTREAM = {
    "zai": os.getenv(
        "ZAI_UPSTREAM_URL",
        "https://zcode.z.ai/api/v1/zcode-plan/anthropic/v1/messages",
    ),
    "zai_fallback": os.getenv(
        "ZAI_FALLBACK_URL",
        "https://api.z.ai/api/anthropic/v1/messages",
    ),
    "bigmodel": os.getenv(
        "BIGMODEL_UPSTREAM_URL",
        "https://open.bigmodel.cn/api/anthropic/v1/messages",
    ),
}

# ZCode 计费 / 额度查询端点
ZCODE_BILLING_BASE = "https://zcode.z.ai/api/v1/zcode-plan"

USER_AGENT = os.getenv("UPSTREAM_USER_AGENT", "ZCode/3.0.1")
APP_VERSION = "2.0.0"
