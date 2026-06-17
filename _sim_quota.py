import json
data = {'data': {'balances': [
    {'show_name': 'GLM-5.2', 'total_units': 3000000, 'used_units': 16959, 'remaining_units': 2983041, 'expires_at': 1781711999},
    {'show_name': 'GLM-5-Turbo', 'total_units': 2000000, 'used_units': 0, 'remaining_units': 2000000, 'expires_at': 1781711999},
]}}
# Simulate quota.py lines 79-86
quota_map = {}
for bal in (data.get('data') or {}).get('balances') or []:
    name = bal.get('show_name') or bal.get('model') or 'model'
    quota_map[name] = {'total': bal.get('total_units'), 'used': bal.get('used_units'),
                       'remaining': bal.get('remaining_units'), 'expires_at': bal.get('expires_at')}
print('quota_map:', json.dumps(quota_map, ensure_ascii=False))
# Simulate quotaCell JS
for k, w in quota_map.items():
    rem = w['remaining']; tot = w['total']
    pct = max(0, min(100, round(rem / tot * 100))) if tot and tot > 0 else 0
    color = '#c9c9cf' if (rem and rem <= 0) else ('#b0632a' if pct < 15 else '#4c9168')
    print(f'{k}: pct={pct}% color={color}  =>  fill width={pct}%  ({rem}/{tot})')
