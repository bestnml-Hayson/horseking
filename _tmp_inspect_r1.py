# -*- coding: utf-8 -*-
import sys, os, re, json
sys.path.insert(0, r'd:\Trae\horse')
sys.dont_write_bytecode = True

import _auto_bootstrap_next_raceday as _boot

date_slash = '2026/09/27'

for race_no in [1, 2]:
    url = f'https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date_slash}&Racecourse=ST&RaceNo={race_no}'
    try:
        html = _boot._scraper_mod.fetch_url(url, retries=2, delay=1)
    except Exception as e:
        print(f'R{race_no} fetch ERR: {e}')
        continue
    # Save raw html for inspection
    out_path = os.path.join(r'd:\Trae\horse', f'_tmp_r{race_no}_raw.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'R{race_no} saved: len={len(html)} -> {out_path}')
    
    # Search for distance/class in ENTIRE html (not just first 10k)
    print(f'\nR{race_no}: 第X班 hits:')
    hits_cls = [(m.start(), html[max(0,m.start()-20):m.start()+80]) for m in re.finditer(r'第[一二三四五]班', html)]
    for pos, snippet in hits_cls[:8]:
        print(f'  @{pos}: {repr(snippet)}')
    
    print(f'\nR{race_no}: 米 hits (first 10):')
    hits_mi = [(m.start(), html[max(0,m.start()-50):m.start()+30]) for m in re.finditer(r'\d{3,4}\s*米', html)]
    for pos, snippet in hits_mi[:10]:
        print(f'  @{pos}: {repr(snippet)}')
    
    print(f'\nR{race_no}: 草地 hits:')
    hits_gd = [(m.start(), html[max(0,m.start()-30):m.start()+80]) for m in re.finditer(r'草地', html)]
    for pos, snippet in hits_gd[:5]:
        print(f'  @{pos}: {repr(snippet)}')
    
    print(f'\nR{race_no}: JSON-like patterns with "distance":')
    for m in re.finditer(r'"distance"\s*[:=]\s*"?([^",}\s]+)', html[:50000]):
        idx = m.start()
        print(f'  @{idx}: {repr(html[max(0,idx-30):idx+80])}')
