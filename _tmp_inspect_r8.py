# -*- coding: utf-8 -*-
import sys, os, re, json
sys.path.insert(0, r'd:\Trae\horse')
sys.dont_write_bytecode = True

import _auto_bootstrap_next_raceday as _boot

date_slash = '2026/09/27'
race_no = 8

url = f'https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date_slash}&Racecourse=ST&RaceNo={race_no}'
html = _boot._scraper_mod.fetch_url(url, retries=2, delay=1)
out = os.path.join(r'd:\Trae\horse', f'_tmp_r{race_no}_raw.html')
with open(out, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved R{race_no} len={len(html)} to {out}')

# Search for the div with class f_fs13
for m in re.finditer(r'f_fs13[^>]*>([^<]*(?:<[^/][^>]*>[^<]*)*)<\/div>', html):
    txt = m.group(0)
    if '第 8 場' in txt or '第8場' in txt or '沙田' in txt and '米' in txt:
        print(f'\nFOUND div around:')
        print(repr(txt[:500]))
        break

# Also search for 第 8 場 directly
for m in re.finditer(r'第\s*8\s*場[^<\n]{0,200}', html):
    idx = m.start()
    print(f'\n第8場 hit at {idx}: >>>{repr(html[idx:idx+300])}<<<')
    break

# Search for 米 around the class area
for m in re.finditer(r'(\d+)\s*米[^<]{0,100}', html):
    idx = m.start()
    s = html[max(0,idx-100):idx+200]
    if '獎金' in s or '評分' in s or '錦標' in s:
        print(f'\nNear 米 + 獎金/評分/錦標:')
        print(repr(s))
