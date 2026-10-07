#!/usr/bin/env python3
"""Import 10/7 race results (all 9 races) into Supabase."""
import io, sys, os, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase

RACE_DATE = '2026-10-07'
VENUE = 'HV'

RESULTS = {
    1: {
        'winning_time': 109.66,
        'finishers': [
            (1, 9, '連連好運', '艾道拿', '文家良', 4.7),
            (2, 4, '竣誠駒', '楊明綸', '告東尼', 6.6),
            (3, 8, '寶成智星', '梁家俊', '伍鵬志', 10),
            (4, 11, '幸運同行', '艾兆禮', '蔡約翰', 10),
            (5, 5, '蜜蜜送', '霍宏聲', '韋達', 9.8),
            (6, 3, '鴻圖大展', '金誠剛', '沈集成', 15),
            (7, 6, '競駿勇士', '黃智弘', '方嘉柏', 21),
            (8, 1, '獎星', '潘頓', '羅富全', 4),
            (9, 12, '戰騎飛', '巫顯東', '丁冠豪', 21),
            (10, 10, '揚威四海', '奧爾民', '葉楚航', 17),
            (11, 2, '一支箭', '田泰安', '賀賢', 11),
            (12, 7, '一風雲', '潘明輝', '丁冠豪', 83),
        ],
        'div_win': 47.5, 'div_place': [18.5, 24.0, 38.0],
    },
    2: {
        'winning_time': 69.48,
        'finishers': [
            (1, 7, '新力', '楊明綸', '鄭俊偉', 9.9),
            (2, 5, '環球英雄', '班德禮', '大衛希斯', 8.3),
            (3, 9, '駿馬之光', '鍾易禮', '告東尼', 24),
            (4, 2, '幸運愉快', '潘明輝', '巫偉傑', 5.9),
            (5, 8, '勝利君子', '何澤堯', '方嘉柏', 28),
            (6, 6, '千杯敬典', '袁幸堯', '姚本輝', 9.9),
            (7, 4, '紅錢到', '霍宏聲', '呂健威', 5.4),
            (8, 11, '威威神駒', '田泰安', '韋達', 84),
            (9, 10, '天下寵兒', '艾兆禮', '廖康銘', 2.6),
            (10, 1, '本領多好', '希威森', '桂福特', 31),
            (11, 12, '智勝攻略', '巴度', '黎昭昇', 38),
            (12, 3, '銳喜', '黃智弘', '徐雨石', 114),
        ],
        'div_win': 99.0, 'div_place': [30.0, 39.0, 72.0],
    },
    3: {
        'winning_time': 98.83,
        'finishers': [
            (1, 4, '卓越蒨鋒', '潘頓', '黎昭昇', 4.9),
            (2, 6, '有情有義', '霍宏聲', '方嘉柏', 3.9),
            (3, 3, '大文豪', '奧爾民', '姚本輝', 14),
            (4, 8, '金駒永騰', '黃智弘', '伍鵬志', 5.4),
            (5, 10, '康昌之星', '艾兆禮', '廖康銘', 6),
            (6, 1, '星願無限', '希威森', '沈集成', 12),
            (7, 7, '滿洛城', '班德禮', '大衛希斯', 42),
            (8, 9, '顏色的顏', '金誠剛', '韋達', 48),
            (9, 12, '保羅輝煌', '潘明輝', '羅富全', 27),
            (10, 5, '牛精新星', '蔡明紹', '告東尼', 10),
            (11, 11, '平天雄', '楊明綸', '丁冠豪', 74),
            (12, 2, '佳登', '艾道拿', '游達榮', 15),
        ],
        'div_win': 49.0, 'div_place': [18.0, 21.5, 52.0],
    },
    4: {
        'winning_time': 99.77,
        'finishers': [
            (1, 8, '超開心', '潘頓', '羅富全', 3.6),
            (2, 2, '深心星', '黃智弘', '方嘉柏', 6.3),
            (3, 10, '準希望', '巴度', '大衛希斯', 3.3),
            (4, 11, '焦點', '艾兆禮', '游達榮', 15),
            (5, 12, '瑞祺威楓', '田泰安', '姚本輝', 7),
            (6, 3, '紅海勁', '霍宏聲', '文家良', 39),
            (7, 7, '妙算強人', '巫顯東', '徐雨石', 114),
            (8, 5, '晉步贏', '何澤堯', '伍鵬志', 24),
            (9, 9, '奮鬥輝煌', '金誠剛', '游達榮', 22),
            (10, 6, '火流星', '潘明輝', '葉楚航', 42),
            (11, 1, '爆笑', '黃寶妮', '告東尼', 14),
            (12, 4, '先到先得', '艾道拿', '蔡約翰', 19),
        ],
        'div_win': 36.0, 'div_place': [16.5, 21.0, 19.5],
    },
    5: {
        'winning_time': 57.15,
        'finishers': [
            (1, 8, '佐治傳奇', '鍾易禮', '告東尼', 3.1),
            (2, 10, '鋼鐵安防', '黃寶妮', '徐雨石', 23),
            (3, 2, '長勝金剛', '袁幸堯', '伍鵬志', 71),
            (4, 7, '哥得寶', '奧爾民', '賀賢', 31),
            (5, 4, '巴閉王', '潘頓', '呂健威', 2.5),
            (6, 9, '赤兔再世', '艾道拿', '方嘉柏', 16),
            (7, 1, '鴻圖新星', '金誠剛', '蔡約翰', 18),
            (8, 12, '馬運高', '田泰安', '文家良', 7.6),
            (9, 3, '友駿同心', '梁家俊', '蘇偉賢', 118),
            (10, 5, '銳目', '班德禮', '大衛希斯', 22),
            (11, 11, '杰遜仔', '巴度', '黎昭昇', 38),
            (12, 6, '美麗登場', '艾兆禮', '羅富全', 12),
        ],
        'div_win': 31.0, 'div_place': [12.5, 37.0, 117.0],
    },
    6: {
        'winning_time': 69.92,
        'finishers': [
            (1, 10, '頑童', '楊明綸', '鄭俊偉', 3.1),
            (2, 4, '銳不可當', '梁家俊', '沈集成', 16),
            (3, 5, '加州勇勝', '田泰安', '告東尼', 9.4),
            (4, 6, '勝多多', '黃寶妮', '韋達', 21),
            (5, 2, '龍虎精神', '何澤堯', '羅富全', 21),
            (6, 1, '添開心', '艾兆禮', '伍鵬志', 47),
            (7, 8, '萬眾開心', '蔡明紹', '黎昭昇', 20),
            (8, 3, '星威心得', '金誠剛', '大衛希斯', 30),
            (9, 12, '首駿', '班德禮', '游達榮', 80),
            (10, 7, '文采風流', '奧爾民', '蘇偉賢', 30),
            (11, 11, '觀萬象', '潘明輝', '葉楚航', 139),
            (12, 9, '後無來者', '巴度', '方嘉柏', 2.1),
        ],
        'div_win': 31.0, 'div_place': [12.0, 27.0, 29.0],
    },
    7: {
        'winning_time': 69.05,
        'finishers': [
            (1, 9, '朗日自強', '梁家俊', '文家良', 7.2),
            (2, 5, '觀眾之力', '巴度', '方嘉柏', 5.7),
            (3, 10, '天馬行雲', '希威森', '桂福特', 11),
            (4, 1, '晨曦儷人', '楊明綸', '伍鵬志', 17),
            (5, 2, '東來欣賞', '袁幸堯', '告東尼', 6.1),
            (6, 6, '電源之駒', '霍宏聲', '廖康銘', 48),
            (7, 7, '耀寶', '艾兆禮', '羅富全', 25),
            (8, 4, '幸運星球', '潘明輝', '丁冠豪', 33),
            (9, 11, '丞匡掠影', '鍾易禮', '徐雨石', 3.9),
            (10, 12, '競駿非凡', '蔡明紹', '韋達', 8.2),
            (11, 3, '快活英雄', '黃寶妮', '黎昭昇', 27),
            (12, 8, '關鍵所在', '黃智弘', '沈集成', 11),
        ],
        'div_win': 72.5, 'div_place': [25.0, 23.0, 31.0],
    },
    8: {
        'winning_time': 98.30,
        'finishers': [
            (1, 9, '大千雄心', '黃智弘', '方嘉柏', 10),
            (2, 8, '金滙千帥', '黃寶妮', '賀賢', 66),
            (3, 3, '盈好威楓', '金誠剛', '姚本輝', 15),
            (4, 2, '幸運派彩', '巴度', '徐雨石', 3),
            (5, 10, '財富非凡', '班德禮', '巫偉傑', 11),
            (6, 7, '高高至高', '希威森', '廖康銘', 29),
            (7, 12, '太子', '梁家俊', '伍鵬志', 9),
            (8, 11, '開心三寶', '蔡明紹', '呂健威', 8.7),
            (9, 1, '一定超', '潘頓', '游達榮', 5.3),
            (10, 6, '傲視同群', '艾兆禮', '文家良', 42),
            (11, 5, '自動自覺', '袁幸堯', '羅富全', 35),
            (12, 4, '嘉應勇將', '鍾易禮', '告東尼', 8.8),
        ],
        'div_win': 102.5, 'div_place': [29.5, 76.0, 44.0],
    },
    9: {
        'winning_time': 68.89,
        'finishers': [
            (1, 7, '星運少爵', '何澤堯', '方嘉柏', 2),
            (2, 9, '烈焰光芒', '艾兆禮', '韋達', 6.2),
            (3, 1, '志滿同行', '潘頓', '文家良', 4.4),
            (4, 11, '勇霸龍', '黃寶妮', '黎昭昇', 16),
            (5, 10, '發發發', '金誠剛', '桂福特', 80),
            (6, 5, '傑出雷霆', '希威森', '呂健威', 16),
            (7, 8, '可靠大師', '潘明輝', '大衛希斯', 20),
            (8, 2, '馬達', '梁家俊', '巫偉傑', 14),
            (9, 4, '福星小子', '巴度', '蔡約翰', 39),
            (10, 12, '勁駿騰飛', '楊明綸', '蘇偉賢', 35),
            (11, 3, '得道猴王', '鍾易禮', '告東尼', 32),
        ],
        'div_win': 20.5, 'div_place': [11.0, 19.0, 21.5],
        'scratched': [6],
    },
}


def main():
    supabase = get_supabase()
    total_updated = 0
    total_results = 0

    for race_no, data in RESULTS.items():
        race_id = f'{VENUE}-{RACE_DATE.replace("-","")}-{race_no:02d}'
        print(f'\n--- R{race_no} ({race_id}) ---')

        # 1. Update race_runners.finish_position
        for pos, horse_no, name, jockey, trainer, odds in data['finishers']:
            resp = supabase.table('race_runners').select('runner_id') \
                .eq('race_id', race_id).eq('horse_no', horse_no).execute()
            if resp.data:
                runner_id = resp.data[0]['runner_id']
                supabase.table('race_runners').update({
                    'finish_position': pos
                }).eq('runner_id', runner_id).execute()
                total_updated += 1
            else:
                print(f'  [WARN] horse_no={horse_no} not found in race_runners')

        # 2. Mark race as finished
        supabase.table('races').update({'is_finished': True}).eq('race_id', race_id).execute()
        print(f'  [OK] Race marked finished, {len(data["finishers"])} runners updated')

        # 3. Write per-runner results to race_results table
        for pos, horse_no, name, jockey, trainer, odds in data['finishers']:
            result_row = {
                'race_id': race_id,
                'race_date': RACE_DATE,
                'venue': VENUE,
                'race_no': race_no,
                'finish_position': pos,
                'horse_no': horse_no,
                'horse_name': name,
                'jockey': jockey,
                'trainer': trainer,
                'win_odds': odds,
            }
            try:
                supabase.table('race_results').upsert(
                    result_row, on_conflict='race_id,horse_no'
                ).execute()
                total_results += 1
            except Exception as e:
                print(f'  [WARN] race_results write failed for #{horse_no}: {e}')

        # 4. Write race summary to race_results (per-race row)
        sorted_finishers = sorted(data['finishers'], key=lambda x: x[0])
        summary_row = {
            'race_id': race_id,
            'winning_time': data.get('winning_time'),
            'winning_odds': data.get('div_win'),
            'race_status': 'COMPLETED',
        }
        if len(sorted_finishers) >= 1:
            summary_row['first_horse_no'] = sorted_finishers[0][1]
        if len(sorted_finishers) >= 2:
            summary_row['second_horse_no'] = sorted_finishers[1][1]
        if len(sorted_finishers) >= 3:
            summary_row['third_horse_no'] = sorted_finishers[2][1]

        try:
            supabase.table('race_results').upsert(
                summary_row, on_conflict='race_id'
            ).execute()
        except Exception as e:
            pass

        print(f'  [OK] {len(data["finishers"])} runner results written')

    print(f'\n{"="*60}')
    print(f'SUMMARY')
    print(f'  race_runners updated: {total_updated}')
    print(f'  race_results rows: {total_results}')
    print(f'  All 9 races marked finished')
    print(f'{"="*60}')


if __name__ == '__main__':
    main()
