"""账号与设置的持久化存储。

数据保存在外部数据库（通过 DATABASE_URL 配置，支持 PostgreSQL / MySQL）
或项目本目录下的 data/accounts.db (SQLite)，采用 WAL 模式。

运行期账号对象常驻内存（保证轮询游标与状态实时性），
每次变更同步落库；进程启动时从数据库读取快照。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import urllib.parse
from contextlib import contextmanager

from . import settings
from .models import PROVIDERS, Account, Status

_TBL = "accounts"
_META = "meta"


def _detect_backend(url: str) -> str:
    if not url:
        return "sqlite"
    url = url.strip()
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        return "pg"
    if url.startswith("mysql://") or url.startswith("mysql2://"):
        return "mysql"
    raise ValueError(f"不支持的 DATABASE_URL 协议: {url}")


class DBAdapter:
    def __init__(self, backend: str, url: str):
        self.backend = backend
        self.url = url

        if self.backend == "pg":
            try:
                import psycopg
                from psycopg.rows import dict_row
                self.psycopg = psycopg
                self.dict_row = dict_row
            except ImportError:
                logging.error("使用 PostgreSQL 需要安装 psycopg。请执行: pip install psycopg[binary]")
                raise
        elif self.backend == "mysql":
            try:
                import pymysql
                import pymysql.cursors
                self.pymysql = pymysql
                parsed = urllib.parse.urlparse(self.url)
                self.mysql_kwargs = {
                    "host": parsed.hostname or "localhost",
                    "port": parsed.port or 3306,
                    "user": parsed.username or "root",
                    "password": parsed.password or "",
                    "database": parsed.path.lstrip("/"),
                    "cursorclass": pymysql.cursors.DictCursor,
                    "autocommit": True
                }
            except ImportError:
                logging.error("使用 MySQL 需要安装 pymysql。请执行: pip install pymysql cryptography")
                raise

    @contextmanager
    def get_connection(self):
        if self.backend == "sqlite":
            conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            try:
                yield conn
            finally:
                conn.close()
        elif self.backend == "pg":
            with self.psycopg.connect(self.url, row_factory=self.dict_row) as conn:
                yield conn
        elif self.backend == "mysql":
            conn = self.pymysql.connect(**self.mysql_kwargs)
            try:
                yield conn
            finally:
                conn.close()

    def translate_sql(self, sql: str) -> str:
        """根据后端将 ? 占位符转换为 $1 等（针对 PG）或 %s（针对 MySQL）。"""
        if self.backend == "sqlite":
            return sql
        if self.backend == "mysql":
            return sql.replace("?", "%s")
        # For PG: ? -> %s in psycopg 3 with auto mapping (or just keep it as %s)
        # Psycopg 3 supports %s.
        return sql.replace("?", "%s")

    def execute_schema(self, conn, sql: str):
        """执行建表等无参数语句，处理多语句分隔。"""
        if self.backend == "sqlite":
            conn.executescript(sql)
            return

        # PG and MySQL can execute multiple statements separated by semicolon (with some caveats)
        # We manually split them for safety
        cursor = conn.cursor()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                cursor.execute(stmt)
        if self.backend == "pg":
            conn.commit()
        cursor.close()

    def execute(self, conn, sql: str, params=()):
        sql = self.translate_sql(sql)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        if self.backend in ("sqlite", "pg"):
            conn.commit()
        return cursor


class Store:
    """线程安全的账号 / 设置存储，含轮询游标。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._accounts: dict[str, list[Account]] = {p: [] for p in PROVIDERS}
        self._settings: dict = {}
        self._rotation: dict[str, int] = {p: 0 for p in PROVIDERS}
        
        self.db = DBAdapter(_detect_backend(settings.DATABASE_URL), settings.DATABASE_URL)
        
        self._init_db()
        self._load()

    def _init_db(self) -> None:
        if self.db.backend == "sqlite":
            settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
            ddl = f"""
                CREATE TABLE IF NOT EXISTS {_META} (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {_TBL} (
                    id          TEXT PRIMARY KEY,
                    provider    TEXT NOT NULL,
                    name        TEXT,
                    mode        TEXT,
                    status      TEXT,
                    enabled     INTEGER NOT NULL DEFAULT 1,
                    created_at  REAL,
                    data        TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_acc_provider ON {_TBL} (provider);
                CREATE INDEX IF NOT EXISTS idx_acc_status   ON {_TBL} (status);
            """
        elif self.db.backend == "pg":
            ddl = f"""
                CREATE TABLE IF NOT EXISTS {_META} (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {_TBL} (
                    id          TEXT PRIMARY KEY,
                    provider    TEXT NOT NULL,
                    name        TEXT,
                    mode        TEXT,
                    status      TEXT,
                    enabled     INTEGER NOT NULL DEFAULT 1,
                    created_at  DOUBLE PRECISION,
                    data        TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_acc_provider ON {_TBL} (provider);
                CREATE INDEX IF NOT EXISTS idx_acc_status   ON {_TBL} (status);
            """
        else: # mysql
            ddl = f"""
                CREATE TABLE IF NOT EXISTS {_META} (
                    `key`   VARCHAR(128) PRIMARY KEY,
                    value   LONGTEXT NOT NULL
                ) CHARACTER SET utf8mb4;
                CREATE TABLE IF NOT EXISTS {_TBL} (
                    id          VARCHAR(128) PRIMARY KEY,
                    provider    VARCHAR(32) NOT NULL,
                    name        VARCHAR(255),
                    mode        VARCHAR(16),
                    status      VARCHAR(32),
                    enabled     INT NOT NULL DEFAULT 1,
                    created_at  DOUBLE,
                    data        LONGTEXT NOT NULL,
                    INDEX idx_acc_provider (provider),
                    INDEX idx_acc_status (status)
                ) CHARACTER SET utf8mb4;
            """

        with self.db.get_connection() as conn:
            try:
                self.db.execute_schema(conn, ddl)
            except Exception as e:
                # 捕获权限不足等错误，给出明确提示
                err_msg = str(e)
                if "CREATE command denied" in err_msg or "1142" in err_msg:
                    logging.error(f"数据库权限不足: 无法自动创建表。请确保你的数据库用户拥有 CREATE 权限，或者手动在数据库中执行建表语句。\n详细错误: {err_msg}")
                    # 不抛出异常的话后续 SELECT 会报错，所以这里最好还是抛出，但带上清晰的说明
                    raise RuntimeError(f"数据库权限不足，无法自动创建数据表，请赋予 CREATE 权限或手动建表: {err_msg}") from e
                raise
            
            # 初始化默认配置
            if self.db.backend == "sqlite":
                self.db.execute(conn, f"INSERT OR IGNORE INTO {_META} (key, value) VALUES (?, ?)", ('admin_key', settings.DEFAULT_ADMIN_KEY))
                self.db.execute(conn, f"INSERT OR IGNORE INTO {_META} (key, value) VALUES (?, ?)", ('gateway_key', ''))
                self.db.execute(conn, f"INSERT OR IGNORE INTO {_META} (key, value) VALUES (?, ?)", ('quota_refresh_interval', str(settings.QUOTA_REFRESH_INTERVAL)))
            elif self.db.backend == "pg":
                self.db.execute(conn, f"INSERT INTO {_META} (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING", ('admin_key', settings.DEFAULT_ADMIN_KEY))
                self.db.execute(conn, f"INSERT INTO {_META} (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING", ('gateway_key', ''))
                self.db.execute(conn, f"INSERT INTO {_META} (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING", ('quota_refresh_interval', str(settings.QUOTA_REFRESH_INTERVAL)))
            else: # mysql
                self.db.execute(conn, f"INSERT IGNORE INTO {_META} (`key`, value) VALUES (?, ?)", ('admin_key', settings.DEFAULT_ADMIN_KEY))
                self.db.execute(conn, f"INSERT IGNORE INTO {_META} (`key`, value) VALUES (?, ?)", ('gateway_key', ''))
                self.db.execute(conn, f"INSERT IGNORE INTO {_META} (`key`, value) VALUES (?, ?)", ('quota_refresh_interval', str(settings.QUOTA_REFRESH_INTERVAL)))


    def _load(self) -> None:
        with self.db.get_connection() as conn:
            if self.db.backend == "mysql":
                meta_rows = self.db.execute(conn, f"SELECT `key`, value FROM {_META}").fetchall()
            else:
                meta_rows = self.db.execute(conn, f"SELECT key, value FROM {_META}").fetchall()

            self._settings = {r["key"]: r["value"] for r in meta_rows}
            self._settings.setdefault("admin_key", settings.DEFAULT_ADMIN_KEY)
            self._settings.setdefault("gateway_key", "")
            self._settings.setdefault("quota_refresh_interval", str(settings.QUOTA_REFRESH_INTERVAL))

            self._accounts = {p: [] for p in PROVIDERS}
            rows = self.db.execute(conn, f"SELECT data FROM {_TBL} ORDER BY created_at ASC").fetchall()
            for row in rows:
                try:
                    account = Account.from_dict(json.loads(row["data"]))
                except (json.JSONDecodeError, TypeError):
                    continue
                if account.provider in self._accounts:
                    self._accounts[account.provider].append(account)

    def _persist_account(self, account: Account) -> None:
        args = (
            account.id, account.provider, account.name, account.mode,
            account.status, 1 if account.enabled else 0, account.created_at,
            json.dumps(account.to_dict(), ensure_ascii=False)
        )
        
        with self.db.get_connection() as conn:
            if self.db.backend == "sqlite":
                self.db.execute(conn, f"""
                    INSERT OR REPLACE INTO {_TBL}
                    (id, provider, name, mode, status, enabled, created_at, data)
                    VALUES (?,?,?,?,?,?,?,?)
                """, args)
            elif self.db.backend == "pg":
                self.db.execute(conn, f"""
                    INSERT INTO {_TBL}
                    (id, provider, name, mode, status, enabled, created_at, data)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT (id) DO UPDATE SET
                        provider = EXCLUDED.provider,
                        name = EXCLUDED.name,
                        mode = EXCLUDED.mode,
                        status = EXCLUDED.status,
                        enabled = EXCLUDED.enabled,
                        created_at = EXCLUDED.created_at,
                        data = EXCLUDED.data
                """, args)
            elif self.db.backend == "mysql":
                self.db.execute(conn, f"""
                    INSERT INTO {_TBL}
                    (id, provider, name, mode, status, enabled, created_at, data)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON DUPLICATE KEY UPDATE
                        provider = VALUES(provider),
                        name = VALUES(name),
                        mode = VALUES(mode),
                        status = VALUES(status),
                        enabled = VALUES(enabled),
                        created_at = VALUES(created_at),
                        data = VALUES(data)
                """, args)

    def _delete_account(self, account_id: str) -> None:
        with self.db.get_connection() as conn:
            self.db.execute(conn, f"DELETE FROM {_TBL} WHERE id = ?", (account_id,))

    def _set_meta(self, key: str, value: str) -> None:
        with self.db.get_connection() as conn:
            if self.db.backend == "sqlite":
                self.db.execute(conn, f"INSERT OR REPLACE INTO {_META} (key, value) VALUES (?, ?)", (key, value))
            elif self.db.backend == "pg":
                self.db.execute(conn, f"INSERT INTO {_META} (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))
            else:
                self.db.execute(conn, f"INSERT INTO {_META} (`key`, value) VALUES (?, ?) ON DUPLICATE KEY UPDATE value = VALUES(value)", (key, value))

    def save(self) -> None:
        """全量落库（兜底接口）。"""
        with self._lock:
            for accounts in self._accounts.values():
                for account in accounts:
                    self._persist_account(account)

    # ── 设置 ─────────────────────────────────────────────────────────────────
    def get_setting(self, key: str, default=None):
        with self._lock:
            return self._settings.get(key, default)

    def set_setting(self, key: str, value) -> None:
        with self._lock:
            self._settings[key] = str(value)
            self._set_meta(key, str(value))

    def admin_key(self) -> str:
        return str(self.get_setting("admin_key", settings.DEFAULT_ADMIN_KEY) or "")

    def gateway_key(self) -> str:
        return str(self.get_setting("gateway_key", "") or "")

    def quota_refresh_interval(self) -> int:
        try:
            return max(0, int(self.get_setting("quota_refresh_interval", settings.QUOTA_REFRESH_INTERVAL)))
        except (TypeError, ValueError):
            return settings.QUOTA_REFRESH_INTERVAL

    # ── 账号读取 ─────────────────────────────────────────────────────────────
    def list_accounts(self, provider: str | None = None) -> list[Account]:
        with self._lock:
            if provider:
                return list(self._accounts.get(provider, []))
            return [a for p in PROVIDERS for a in self._accounts[p]]

    def find(self, provider: str, id_or_name: str) -> Account | None:
        with self._lock:
            return self._find_locked(provider, id_or_name)

    def find_any(self, id_or_name: str) -> Account | None:
        with self._lock:
            for p in PROVIDERS:
                for a in self._accounts[p]:
                    if a.id == id_or_name:
                        return a
        return None

    def _find_locked(self, provider: str, id_or_name: str) -> Account | None:
        for a in self._accounts.get(provider, []):
            if a.id == id_or_name or a.name == id_or_name:
                return a
        return None

    # ── 账号增删改 ───────────────────────────────────────────────────────────
    def add_account(self, provider: str, name: str, secret: str) -> Account:
        if provider not in PROVIDERS:
            raise ValueError(f"不支持的 provider: {provider}")
        account = Account.create(provider, name, secret)
        with self._lock:
            for a in self._accounts[provider]:
                if a.secret and a.secret == account.secret:
                    return a  # 跳过重复 token
            self._accounts[provider].append(account)
            self._persist_account(account)
        return account

    def remove_account(self, provider: str, id_or_name: str) -> bool:
        with self._lock:
            items = self._accounts.get(provider, [])
            target = next((a for a in items if a.id == id_or_name or a.name == id_or_name), None)
            if not target:
                return False
            self._accounts[provider] = [a for a in items if a.id != target.id]
            self._delete_account(target.id)
            return True

    def update_account(self, account: Account) -> None:
        """持久化某个账号的当前状态。"""
        with self._lock:
            self._persist_account(account)

    def set_enabled(self, provider: str, id_or_name: str, enabled: bool) -> bool:
        with self._lock:
            account = self._find_locked(provider, id_or_name)
            if not account:
                return False
            account.enabled = enabled
            if not enabled:
                account.status = Status.DISABLED
            elif account.status == Status.DISABLED:
                account.status = Status.ACTIVE
            self._persist_account(account)
            return True

    # ── 轮询选择 ─────────────────────────────────────────────────────────────
    def select(self, provider: str, skip_ids: set[str] | None = None) -> Account | None:
        """按 round-robin 选择下一个可用账号。用完 / 失效的自动跳过。"""
        skip_ids = skip_ids or set()
        now = time.time()
        with self._lock:
            pool = [
                a for a in self._accounts.get(provider, [])
                if a.is_selectable(now) and a.id not in skip_ids
            ]
            if not pool:
                return None
            idx = self._rotation.get(provider, 0) % len(pool)
            account = pool[idx]
            self._rotation[provider] = (idx + 1) % len(pool)
            return account

    # ── 导入 / 导出 ─────────────────────────────────────────────────────────
    def export(self) -> dict:
        with self._lock:
            return {
                "version": 1,
                "exported_at": time.time(),
                "providers": {
                    p: [
                        {"name": a.name, "mode": a.mode, "secret": a.secret}
                        for a in self._accounts[p]
                    ]
                    for p in PROVIDERS
                },
            }

    def import_accounts(self, payload: dict) -> int:
        providers = payload.get("providers", {})
        count = 0
        for provider, items in providers.items():
            if provider not in PROVIDERS or not isinstance(items, list):
                continue
            for it in items:
                secret = it.get("secret") or it.get("token") or it.get("jwtToken") or it.get("apiKey")
                if not secret:
                    continue
                self.add_account(provider, it.get("name", provider), secret)
                count += 1
        return count


# 单例
store = Store()
