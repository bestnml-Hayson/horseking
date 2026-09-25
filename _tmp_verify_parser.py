# -*- coding: utf-8 -*-
import sys, os, re, json
sys.path.insert(0, r'd:\Trae\horse')
sys.dont_write_bytecode = True

import _auto_bootstrap_next_raceday as _boot

date_slash = '2026/09/27'
venue_cn = '沙田'
venue_code = 'ST'
date_compact = '20260927'
date_dash = '2026-09-27'

print("===== Testing _parse_hkjc_racecard parser =====\n")
all_ok = True
for race_no in range(1, 12):
    urls = [
        f'https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date_slash}&Racecourse=ST&RaceNo={race_no}',
        f'https://racing.hkjc.com/racing/information/chinese/Racing/Racecard.aspx?racedate={date_slash}&Racecourse=ST&RaceNo={race_no}',
    ]
    html = None
    import_url = None
    for u in urls:
        try:
            tmp = _boot._scraper_mod.fetch_url(u, retries=2, delay=1)
            if isinstance(tmp, bytes):
                tmp = tmp.decode('utf-8', 'replace')
            if len(tmp) > 20000:
                html = tmp
                import_url = u
                break
        except:
            pass
    if not html:
        print(f'R{race_no}: FETCH FAILED')
        all_ok = False
        continue
    
    result = _boot._parse_racecard_page(html, date_slash, venue_code, race_no, import_url or urls[0])
    ri = result["race_info"]
    ok = ri["distance_m"] > 0
    if not ok:
        all_ok = False
    print(f"R{race_no} {'[OK]' if ok else '[FAIL]'}: name={result['meta']['race_name_full']}  dist={ri['distance_m']}m  surface={ri['surface']}  track={ri['track']}  class={ri['class']}  rating={ri['rating_range']}  prize={ri['prize']}  post={ri['post_time']}")

print(f"\n===== {'ALL PASS' if all_ok else 'SOME FAILED'} =====")
