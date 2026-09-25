# -*- coding: utf-8 -*-
import sys, re
sys.path.insert(0, r'D:\Trae\horse')
import _auto_bootstrap_next_raceday as _boot
html = open(r'D:\Trae\horse\_tmp_r1.html', 'r', encoding='utf-8').read()
url = 'https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/09/27&Racecourse=ST&RaceNo=1'
obj = _boot._parse_racecard_page(html, '2026/09/27', 'ST', 1, url)
print('R1 race_info:', {k: obj['race_info'][k] for k in obj['race_info'] if k in ('post_time','num_horses','class','distance_m','venue','track','going')})
horses = obj['horses']
print('horses count =', len(horses))
for h in horses[:6]:
    # print key 12 static fields
    print(f"H{h['number']:02d} name={h.get('name','?')} jockey={h.get('jockey','?')} trainer={h.get('trainer','?')}")
    print(f"   draw={h.get('draw')} rating={h.get('rating')} weight={h.get('weight')} gear={h.get('gear')}")
    print(f"   last_6={h.get('last_6')!r} last_3={h.get('last_3')} best_time={h.get('best_time_sec')}")
    print()
print('meta.note =', obj['meta'].get('note'))
print('meta.import_from =', obj['meta'].get('import_from'))
