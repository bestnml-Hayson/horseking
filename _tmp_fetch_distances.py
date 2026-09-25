# -*- coding: utf-8 -*-
import sys, os, re, json
sys.path.insert(0, r'd:\Trae\horse')
sys.dont_write_bytecode = True

import _auto_bootstrap_next_raceday as _boot

date_slash = '2026/09/27'

for race_no in range(1, 12):
    url = f'https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date_slash}&Racecourse=ST&RaceNo={race_no}'
    try:
        html = _boot._scraper_mod.fetch_url(url, retries=2, delay=1)
    except Exception as e:
        print(f'R{race_no} fetch ERR: {e}')
        continue
    print(f'\n===== R{race_no} HTML len={len(html)} =====')
    
    print('--- class_dist search:')
    p1 = re.search(r'(第[一二三四五]班)[^|]*\s-\s*(\d+)\s*米\s*-\s*\(([^\)]+)\)', html)
    if p1:
        print(f'  Pattern1: class={p1.group(1)}  distance={p1.group(2)}m  range={p1.group(3)}')
    else:
        p2 = re.search(r'(第[一二三四五]班)[^<|]*\s*-\s*(\d+)\s*米', html)
        if p2:
            print(f'  Pattern2: class={p2.group(1)}  distance={p2.group(2)}m')
        else:
            print('  BOTH patterns FAILED — dumping relevant section:')
            for m in re.finditer(r'(第[一二三四五]班)', html[:10000]):
                idx = m.start()
                print(f'  班 hit at {idx}: >>>{repr(html[max(0,idx-10):idx+100])}<<<')
            for m in re.finditer(r'(\d+)\s*米', html[:10000]):
                idx = m.start()
                print(f'  米 hit at {idx}: >>>{repr(html[max(0,idx-50):idx+30])}<<<')
    
    m_t = re.search(r'賽道\s*[:：]\s*([^<\n|]+)', html)
    if m_t:
        print(f'  賽道: {m_t.group(1).strip()[:80]}')
    m_g = re.search(r'場地狀況\s*[:：]\s*([^\n<|]+)', html)
    if m_g:
        print(f'  場地: {m_g.group(1).strip()[:60]}')
    
    for m in re.finditer(r'(草地|全天候)[^0-9]{0,20}(\d{3,4})\s*米', html[:10000]):
        idx = m.start()
        print(f'  草地+米 wider: >>>{repr(html[max(0,idx-30):idx+80])}<<<')
