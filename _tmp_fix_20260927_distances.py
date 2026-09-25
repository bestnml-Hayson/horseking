# -*- coding: utf-8 -*-
"""
Fix ST-20260927 all 11 races:
  - Re-parse correct race_info (distance_m / surface / track / class / rating_range / prize / post_time) from HKJC
  - Preserve ALL horses entries + odds / cc_* / results / payouts etc. (safe merge — only update race_info & meta top-level)
  - Rename files to correct {dist}m_{cls_suffix}
  - Update list.json entries
  - Mirror to public/data/history
"""
import sys, os, re, json, shutil
sys.path.insert(0, r'd:\Trae\horse')
sys.dont_write_bytecode = True

from datetime import datetime
from collections import OrderedDict

import _auto_bootstrap_next_raceday as _boot

ROOT = r'd:\Trae\horse'
DATA_HIST = os.path.join(ROOT, 'data', 'history')
PUB_HIST = os.path.join(ROOT, 'public', 'data', 'history')
LIST_JSON = os.path.join(ROOT, 'public', 'api', 'list.json')

DATE_SLASH = '2026/09/27'
DATE_DASH = '2026-09-27'
DATE_COMPACT = '20260927'
VENUE_CODE = 'ST'
VENUE_CN = '沙田'

def read_json(p):
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f, object_pairs_hook=OrderedDict)

def write_json(p, d):
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

def find_existing_file(hist_dir, race_no):
    # Find any existing file matching ST-20260927-XX_raceXX_* (both CURRENT and non-CURRENT)
    prefix = f'ST-20260927-{race_no:02d}_'
    candidates = []
    for fn in os.listdir(hist_dir):
        if fn.startswith(prefix) and fn.endswith('.json'):
            candidates.append(fn)
    if not candidates:
        return None
    # Prefer non-CURRENT, otherwise CURRENT
    non_cur = [c for c in candidates if '_CURRENT' not in c]
    return (non_cur or candidates)[0]

# ========== Step 1: Parse all 11 races correctly ==========
print('=== Step 1: Re-parse 11 races from HKJC ===')
correct_parsed = {}
for r in range(1, 12):
    urls = [
        f'https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={DATE_SLASH}&Racecourse=ST&RaceNo={r}',
        f'https://racing.hkjc.com/racing/information/chinese/Racing/Racecard.aspx?racedate={DATE_SLASH}&Racecourse=ST&RaceNo={r}',
    ]
    html = None
    iu = None
    for u in urls:
        try:
            tmp = _boot._scraper_mod.fetch_url(u, retries=2, delay=1)
            if isinstance(tmp, bytes):
                tmp = tmp.decode('utf-8', 'replace')
            if len(tmp) > 20000:
                html = tmp
                iu = u
                break
        except Exception as _e:
            pass
    if not html:
        raise RuntimeError(f'R{r} fetch FAILED')
    parsed = _boot._parse_racecard_page(html, DATE_SLASH, VENUE_CODE, r, iu)
    ri = parsed['race_info']
    # Sanity: distance must be > 0
    assert ri['distance_m'] > 0, f'R{r} distance=0 after parse'
    correct_parsed[r] = parsed
    print(f"  R{r}: {parsed['meta']['race_name_full']}  {ri['distance_m']}m  {ri['surface']}  {ri['track']}  {ri['class']}  post={ri['post_time']}")

# ========== Step 2: For each race, load existing JSON, update meta & race_info ==========
print('\n=== Step 2: Update existing JSONs (safe-merge) ===')
file_rename_map = {}  # old_fname -> new_fname
for r in range(1, 12):
    parsed = correct_parsed[r]
    correct_ri = parsed['race_info']
    correct_meta = parsed['meta']
    
    existing_fn = find_existing_file(DATA_HIST, r)
    if not existing_fn:
        # No CURRENT exists yet — we'll write it fresh later from parsed
        print(f"  R{r}: [SKIP] no existing file in data/history")
        continue
    existing_path = os.path.join(DATA_HIST, existing_fn)
    data = read_json(existing_path)
    
    # ---- Merge meta ----
    if 'meta' not in data:
        data['meta'] = OrderedDict()
    # Preserve odds/result timestamps if already there
    keep_meta_keys = ['odds_update_time', 'odds_source', 'result_update_time', 
                      'cc_fetch_time', 'hkjc_supplement_time']
    preserved_meta_sub = {k: data['meta'][k] for k in keep_meta_keys if k in data.get('meta', {})}
    # Overwrite meta from parsed (import_from / import_time / race_name_full / note)
    for k in correct_meta:
        data['meta'][k] = correct_meta[k]
    data['meta']['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data['meta']['note'] = (f"distance/surface/track/class/rating_range/prize/post_time "
                           f"re-parsed & corrected from HKJC zh-hk racecard @ {data['meta']['update_time']}; "
                           f"horses / odds / cc_* / payouts untouched.")
    # Restore preserved timestamps
    for k, v in preserved_meta_sub.items():
        data['meta'][k] = v
    
    # ---- Merge race_info ----
    # Which race_info keys to overwrite from parsed? All EXCEPT:
    #   result_available, num_horses, official_result, split_times, payouts, last_3_winners
    race_info_protect = {'result_available', 'num_horses', 'official_result', 
                         'split_times', 'payouts', 'last_3_winners'}
    if 'race_info' not in data:
        data['race_info'] = OrderedDict()
    for k in correct_ri:
        if k in race_info_protect:
            continue
        data['race_info'][k] = correct_ri[k]
    # Ensure num_horses is consistent with horses len
    data['race_info']['num_horses'] = len(data.get('horses', [])) or correct_ri.get('num_horses', 0)
    
    # ---- Compute new filename ----
    dist = int(data['race_info']['distance_m'])
    cls_suf, _ = _boot._cls_num_suffix(data['race_info'].get('class', ''))
    new_fn = f'ST-{DATE_COMPACT}-{r:02d}_race{r}_{dist}m_{cls_suf}.json'
    
    # Remove CURRENT variant if present (we want clean non-CURRENT after correction)
    if existing_fn != new_fn:
        file_rename_map[existing_fn] = new_fn
        print(f"  R{r}: RENAME  {existing_fn}  ->  {new_fn}")
    else:
        print(f"  R{r}: KEEP NAME  {existing_fn}")
    
    # ---- Save back (to existing path first, rename happens in Step 3) ----
    write_json(existing_path, data)

# ========== Step 3: Rename files in data/history ==========
print('\n=== Step 3: Rename files in data/history ===')
for old_fn, new_fn in file_rename_map.items():
    old_p = os.path.join(DATA_HIST, old_fn)
    new_p = os.path.join(DATA_HIST, new_fn)
    if os.path.exists(old_p):
        # Handle collision: if new_p exists, unlink old target first
        if os.path.exists(new_p) and new_p != old_p:
            os.remove(new_p)
        os.rename(old_p, new_p)
        print(f"  data rename OK: {old_fn} -> {new_fn}")
    else:
        print(f"  [WARN] old not found: {old_p}")

# ========== Step 4: Mirror data -> public/data/history (copy + rename) ==========
print('\n=== Step 4: Mirror corrected files to public/data/history ===')
for r in range(1, 12):
    # Name in DATA_HIST after rename
    correct_ri = correct_parsed[r]['race_info']
    dist = int(correct_ri['distance_m'])
    cls_suf, _ = _boot._cls_num_suffix(correct_ri.get('class', ''))
    canon_fn = f'ST-{DATE_COMPACT}-{r:02d}_race{r}_{dist}m_{cls_suf}.json'
    
    src_p = os.path.join(DATA_HIST, canon_fn)
    if not os.path.exists(src_p):
        # Maybe still CURRENT variant in data? Try that
        alt = f'ST-{DATE_COMPACT}-{r:02d}_race{r}_{dist}m_{cls_suf}_CURRENT.json'
        alt_p = os.path.join(DATA_HIST, alt)
        if os.path.exists(alt_p):
            src_p = alt_p
        else:
            print(f"  R{r}: [SKIP MIRROR] no source at {canon_fn} / {alt}")
            continue
    
    # First, clean up ST-20260927-XX old variants in PUBLIC
    prefix_pub = f'ST-20260927-{r:02d}_'
    for old_pub in list(os.listdir(PUB_HIST)):
        if old_pub.startswith(prefix_pub) and old_pub.endswith('.json') and old_pub != canon_fn:
            old_pub_p = os.path.join(PUB_HIST, old_pub)
            try:
                os.remove(old_pub_p)
                print(f"  pub remove old: {old_pub}")
            except:
                pass
    
    dst_p = os.path.join(PUB_HIST, canon_fn)
    shutil.copy2(src_p, dst_p)
    print(f"  pub copy OK: {canon_fn}")

# ========== Step 5: Rebuild list.json ==========
print('\n=== Step 5: Update public/api/list.json ===')
lj = read_json(LIST_JSON)

# Step 5a: Remove ALL ST-20260927-* entries (both CURRENT and non-CURRENT, any dist/class suffix)
clean_list = []
removed = 0
for item in lj['race_files']:
    if 'ST-20260927-' in item:
        removed += 1
    else:
        clean_list.append(item)
print(f'  removed {removed} stale ST-20260927 entries')

# Step 5b: For each race 1..11, build canonical filename & append at the position before last
all_races = []
for r in range(1, 12):
    correct_ri = correct_parsed[r]['race_info']
    dist = int(correct_ri['distance_m'])
    cls_suf, _ = _boot._cls_num_suffix(correct_ri.get('class', ''))
    canon_fn = f'ST-{DATE_COMPACT}-{r:02d}_race{r}_{dist}m_{cls_suf}.json'
    all_races.append(canon_fn)
    # Verify file exists in public
    p = os.path.join(PUB_HIST, canon_fn)
    if not os.path.exists(p):
        print(f"  [WARN] list entry missing in public: {canon_fn}")

# Insert — convention: append them. (User can reorder if needed.)
clean_list.extend(all_races)
lj['race_files'] = clean_list
lj['total'] = len(clean_list)
lj['generated_at'] = datetime.now().astimezone().isoformat()
write_json(LIST_JSON, lj)
print(f"  list.json total now = {lj['total']}  (added 11 corrected ST-20260927)")

print('\n===== ALL DONE =====')
print('Next steps: 1) git add -A  2) git commit -m "Fix ST-20260927 distances/track/class from HKJC re-parse"  3) git push')
