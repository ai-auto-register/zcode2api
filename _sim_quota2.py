def fmt(n):
    n = int(n) if n else 0
    return f"{n/1000:.1f}k" if n >= 10000 else str(n)

def quota_cell(quota):
    rows = []
    for k, w in quota.items():
        rem = float(w["remaining"] or 0); tot = float(w["total"] or 0)
        pct = max(0, min(100, round(rem / tot * 100))) if tot > 0 else 0
        has_rem = rem > 0 and tot > 0
        if has_rem and pct < 2:
            pct = 2
        color = '#c9c9cf' if rem <= 0 else ('#d97706' if pct < 15 else '#4c9168')
        val_color = '' if (rem > 0 and pct >= 15) else ('color:#c9c9cf' if rem <= 0 else 'color:#d97706')
        rows.append(f"  {k:14s} rem={int(rem):>8d}/{int(tot):>8d}  pct={pct:>3d}%  color={color}  fill_visible={'YES' if pct>0 else 'NO'}")
    return "\n".join(rows)

# 用两个真实账号的数据测
cases = {
    "74b8b130 (用户给的，GLM-5.2 几乎用完)": {
        "GLM-5.2": {"total": 3000000, "used": 2995975, "remaining": 4025},
        "GLM-5-Turbo": {"total": 2000000, "used": 0, "remaining": 2000000},
    },
    "e9713345 (我的，几乎没用)": {
        "GLM-5.2": {"total": 3000000, "used": 16959, "remaining": 2983041},
        "GLM-5-Turbo": {"total": 2000000, "used": 0, "remaining": 2000000},
    },
    "极端：剩余1": {
        "GLM-5.2": {"total": 3000000, "used": 2999999, "remaining": 1},
    },
    "耗尽：剩余0": {
        "GLM-5.2": {"total": 3000000, "used": 3000000, "remaining": 0},
    },
}

for name, q in cases.items():
    print(f"\n=== {name} ===")
    print(quota_cell(q))
