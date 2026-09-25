# -*- coding: utf-8 -*-
import sys, os, re, json
sys.path.insert(0, r'd:\Trae\horse')
sys.dont_write_bytecode = True

import _auto_bootstrap_next_raceday as _boot

date_slash = '2026/09/27'

race_data = {}

for race_no in range(1, 12):
    url = f'https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date_slash}&Racecourse=ST&RaceNo={race_no}'
    try:
        html = _boot._scraper_mod.fetch_url(url, retries=2, delay=1)
    except Exception as e:
        print(f'R{race_no} fetch ERR: {e}')
        continue
    
    info = {'race': race_no, 'distance_m': 0, 'surface': '', 'track': '', 'class': '', 
            'rating_range': '', 'prize': '', 'post_time': '', 'race_name': ''}
    
    # Correct pattern from Line 1757:
    # 第 1 場 - 熱帶鳥讓賽</span><br>2026年9月27日, 星期日, 沙田, 12:45<br>全天候跑道, 1200米<br>獎金: $875,000, 評分: 40-0, 第五班
    # 第 2 場 - 孔雀讓賽</span><br>2026年9月27日, 星期日, 沙田, 13:15<br>草地, "C+3" 賽道, 1200米<br>獎金: $1,170,000, 評分: 60-40, 第四班
    m = re.search(
        r'第\s*' + str(race_no) + r'\s*場\s*-\s*([^<\n]+?)</span>\s*<br\s*/?>\s*'
        r'\d{4}年\d{1,2}月\d{1,2}日\s*,\s*[^,]+,\s*沙田\s*,\s*(\d{1,2}:\d{2})\s*<br\s*/?>\s*'
        r'([^,]+?)\s*(?:,\s*"([^"]+)"\s*賽道)?\s*,\s*(\d+)\s*米\s*<br\s*/?>\s*'
        r'獎金\s*[:：]\s*(\$[\d,]+)\s*,\s*評分\s*[:：]\s*([^,]+)\s*,\s*(第[一二三四五]班)',
        html
    )
    if m:
        info['race_name'] = m.group(1).strip()
        info['post_time'] = m.group(2).strip()
        info['surface'] = m.group(3).strip()
        if m.group(4):
            info['track'] = m.group(4).strip() + '賽道'
        info['distance_m'] = int(m.group(5))
        info['prize'] = 'HK' + m.group(6).strip()
        info['rating_range'] = m.group(7).strip()
        info['class'] = m.group(8).strip()
    else:
        print(f'R{race_no}: PRIMARY PATTERN FAILED — try innerText extractor')
    
    race_data[race_no] = info
    print(f"R{race_no}: {info['race_name']}  dist={info['distance_m']}m  surface={info['surface']}  track={info['track']}  class={info['class']}  rating={info['rating_range']}  prize={info['prize']}  post={info['post_time']}")

out = os.path.join(r'd:\Trae\horse', '_tmp_correct_race_info.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(race_data, f, ensure_ascii=False, indent=2)
print(f'\nSaved to {out}')
