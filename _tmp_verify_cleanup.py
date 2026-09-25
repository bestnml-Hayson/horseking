# -*- coding: utf-8 -*-
"""Cleanup leftover CURRENT files & duplicate HV dummy entries, verify corrections."""
import sys, os, json, re
sys.path.insert(0, r'd:\Trae\horse')
sys.dont_write_bytecode = True

ROOT = r'd:\Trae\horse'
DATA_HIST = os.path.join(ROOT, 'data', 'history')
PUB_HIST = os.path.join(ROOT, 'public', 'data', 'history')

# ===== Step A: Remove ALL CURRENT files for 20260927 (both ST and HV erroneous ones) =====
print('=== Step A: Cleanup CURRENT / 0m stub files ===')
for d in [DATA_HIST, PUB_HIST]:
    for fn in list(os.listdir(d)):
        if not fn.endswith('.json'):
            continue
        kill = False
        if '20260927' in fn and ('_CURRENT' in fn or '_0m_' in fn):
            kill = True
        # HV 20260927 race files never existed (Sun 9/27 is ST), remove all HV-20260927* duplicates
        if fn.startswith('HV-20260927-'):
            kill = True
        if kill:
            p = os.path.join(d, fn)
            try:
                os.remove(p)
                print(f'  DEL [{os.path.basename(d)}]: {fn}')
            except Exception as e:
                print(f'  FAIL DEL: {fn} -> {e}')

# ===== Step B: Verify each R1-R11 has correct distance_m & class in data & public =====
print('\n=== Step B: Verify 11 races data match ===')
EXPECTED = {
    1:  (1200, '第五班', '全天候跑道'),
    2:  (1200, '第四班', '草地'),
    3:  (1400, '第五班', '草地'),
    4:  (1000, '第四班', '草地'),
    5:  (1200, '第四班', '全天候跑道'),
    6:  (1400, '第四班', '草地'),
    7:  (1200, '第三班', '全天候跑道'),
    8:  (1400, '三級賽', '草地'),
    9:  (1600, '第三班', '草地'),
    10: (1200, '第二班', '草地'),
    11: (1400, '第三班', '草地'),
}
ok_all = True
for r in range(1, 12):
    prefix = f'ST-20260927-{r:02d}_'
    # find in DATA
    d_fn = next((f for f in os.listdir(DATA_HIST) if f.startswith(prefix) and f.endswith('.json')), None)
    p_fn = next((f for f in os.listdir(PUB_HIST) if f.startswith(prefix) and f.endswith('.json')), None)
    if not d_fn or not p_fn:
        print(f'  R{r}: MISSING  data={d_fn}  pub={p_fn}')
        ok_all = False
        continue
    with open(os.path.join(DATA_HIST, d_fn), 'r', encoding='utf-8') as f:
        d = json.load(f)
    with open(os.path.join(PUB_HIST, p_fn), 'r', encoding='utf-8') as f:
        p = json.load(f)
    ri_d = d['race_info']
    ri_p = p['race_info']
    exp = EXPECTED[r]
    ok = (ri_d['distance_m'] == exp[0] and ri_d['class'] == exp[1] and ri_d['surface'] == exp[2]
          and ri_p['distance_m'] == exp[0] and ri_p['class'] == exp[1] and ri_p['surface'] == exp[2])
    if not ok:
        ok_all = False
    mark = '[OK]' if ok else '[FAIL]'
    print(f"  R{r} {mark}: data={d_fn}  pub={p_fn}")
    if not ok:
        print(f"       data: dist={ri_d['distance_m']} cls={ri_d['class']} surf={ri_d['surface']}")
        print(f"       pub : dist={ri_p['distance_m']} cls={ri_p['class']} surf={ri_p['surface']}")
        print(f"       exp : dist={exp[0]} cls={exp[1]} surf={exp[2]}")
    # Same filename check
    if d_fn != p_fn:
        print(f"       [WARN] filename mismatch: data={d_fn} vs pub={p_fn}")

# ===== Step C: list.json consistency check =====
print('\n=== Step C: list.json consistency ===')
lj_path = os.path.join(ROOT, 'public', 'api', 'list.json')
with open(lj_path, 'r', encoding='utf-8') as f:
    lj = json.load(f)
st_count = sum(1 for x in lj['race_files'] if 'ST-20260927-' in x)
hv_count = sum(1 for x in lj['race_files'] if 'HV-20260927-' in x)
cur_count = sum(1 for x in lj['race_files'] if '_CURRENT' in x and '20260927' in x)
zero_m_count = sum(1 for x in lj['race_files'] if '_0m_' in x and '20260927' in x)
print(f"  list.json ST-20260927 entries: {st_count} (expected 11)")
print(f"  list.json HV-20260927 entries: {hv_count} (expected 0)")
print(f"  list.json CURRENT 20260927 entries: {cur_count} (expected 0)")
print(f"  list.json 0m 20260927 entries: {zero_m_count} (expected 0)")
if st_count != 11 or hv_count != 0 or cur_count != 0 or zero_m_count != 0:
    ok_all = False
    # Clean list.json again if stray entries
    if hv_count or cur_count or zero_m_count or st_count != 11:
        clean = []
        keep_st = set()
        for r in range(1, 12):
            for item in lj['race_files']:
                if item.startswith(f'ST-20260927-{r:02d}_race{r}_') and item.endswith('.json') and '_0m_' not in item and '_CURRENT' not in item:
                    keep_st.add(item)
                    break
        for item in lj['race_files']:
            if 'HV-20260927-' in item:
                continue
            if '20260927' in item and ('_CURRENT' in item or '_0m_' in item):
                continue
            if item in keep_st:
                continue
            clean.append(item)
        clean.extend(sorted(keep_st))
        lj['race_files'] = clean
        lj['total'] = len(clean)
        from datetime import datetime
        lj['generated_at'] = datetime.now().astimezone().isoformat()
        with open(lj_path, 'w', encoding='utf-8') as f:
            json.dump(lj, f, ensure_ascii=False, indent=4)
        print(f"  -> auto-fixed list.json, total now {lj['total']}")

print(f'\n===== {"ALL PASS" if ok_all else "HAS ISSUES"} =====')
if not ok_all:
    sys.exit(1)
