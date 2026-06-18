"""从 zcode_tokens.txt 批量导入 MySQL（直接多行 INSERT）。

用法:
  python import_tokens.py [批大小]
"""

import json
import secrets
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import settings
from app.models import Account

TOKENS_FILE = Path(__file__).parent / "zcode_tokens.txt"
BATCH_SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 500

def _account_id(name: str) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in (name or "account").lower())
    safe = safe.strip("-")[:32] or "account"
    return f"{safe}-{secrets.token_hex(4)}"

def build_account(i: int, token: str) -> Account:
    return Account(
        id=_account_id(f"zai-{i}"),
        name=f"zai-{i}",
        provider="zai",
        mode="jwt",
        jwt_token=token,
    )

def main():
    from app.store import _detect_backend
    backend = _detect_backend(settings.DATABASE_URL)
    if backend != "mysql":
        print("仅支持 MySQL 数据库", file=sys.stderr)
        sys.exit(1)

    import pymysql
    import pymysql.cursors

    parsed = urllib.parse.urlparse(settings.DATABASE_URL)
    conn = pymysql.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=parsed.username or "root",
        password=parsed.password or "",
        database=parsed.path.lstrip("/"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )

    t0 = time.time()

    all_tokens = [
        line.strip()
        for line in TOKENS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    total = len(all_tokens)
    print(f"[1/4] 从文件读取 token: {total} 个 ({time.time() - t0:.2f}s)")

    cursor = conn.cursor()

    t1 = time.time()
    cursor.execute("SELECT data FROM accounts")
    rows = cursor.fetchall()
    print(f"[2/4] 查询数据库已有账号: {len(rows)} 条 ({time.time() - t1:.2f}s)")

    t2 = time.time()
    existing = set()
    for row in rows:
        try:
            acc = Account.from_dict(json.loads(row["data"]))
            if acc.secret:
                existing.add(acc.secret)
        except (json.JSONDecodeError, TypeError):
            continue
    print(f"[3/4] 比对去重: 已存在 {len(existing)} 个 ({time.time() - t2:.2f}s)")

    t3 = time.time()
    accounts = []
    skipped_existing = 0
    for i, token in enumerate(all_tokens, 1):
        if token in existing:
            skipped_existing += 1
            continue
        accounts.append(build_account(i, token))

    total_new = len(accounts)
    print(f"      待插入新 token: {total_new} 个, 跳过重复: {skipped_existing} 个")
    print(f"[4/4] 开始写入数据库 (批大小 {BATCH_SIZE})...")

    inserted = 0
    for start in range(0, total_new, BATCH_SIZE):
        batch = accounts[start:start + BATCH_SIZE]
        values = []
        for acc in batch:
            data = json.dumps(acc.to_dict(), ensure_ascii=False)
            values.append((
                acc.id, acc.provider, acc.name, acc.mode,
                acc.status, 1, acc.created_at, data,
            ))

        cursor.executemany(
            """INSERT INTO accounts
               (id, provider, name, mode, status, enabled, created_at, data)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
               provider = VALUES(provider), name = VALUES(name),
               mode = VALUES(mode), status = VALUES(status),
               enabled = VALUES(enabled), created_at = VALUES(created_at),
               data = VALUES(data)""",
            values,
        )
        inserted += len(batch)
        end = start + len(batch)
        print(f"  ✓ 第 {start + 1}~{end} 个 ({time.time() - t3:.2f}s)")

    elapsed = time.time() - t0
    cursor.close()
    conn.close()
    print(f"\n完成: 文件共 {total} 个，已存在 {skipped_existing} 个，新插入 {inserted} 个 | 耗时 {elapsed:.2f}s")

if __name__ == "__main__":
    main()
