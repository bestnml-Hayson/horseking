#!/usr/bin/env python3
"""Post-race results quality / coverage / speed-baseline report (Line 2-A).

Read-only. Uses race_runners.finish_time (seconds) and margin (lengths) written
by the results importers. Produces:
  * quality checks: value ranges, winner margin, winner-is-fastest sanity,
  * coverage by venue / distance / class / month with missing reasons,
  * a same-venue + same-distance + same-course winning-time baseline table
    (>=4 finishers, group marked insufficient below 5 races).

Display only: nothing here enters P_model or any weight. finish_time_margin and
speed_engine flags stay off; has_best_time=0 rows keep their original trip score.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from statistics import mean, median, pstdev
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase
from results_fields import (
    FINISH_TIME_MAX, FINISH_TIME_MIN, MARGIN_OUTLIER)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_ID = 'results_quality_report'


def _paginate(supabase, table, columns, order_col, extra=None):
    rows, start, page = [], 0, 1000
    while True:
        def build(start=start):
            query = supabase.table(table).select(columns).order(order_col).range(
                start, start + page - 1)
            return (extra(query) if extra else query).execute()
        batch = retry_supabase(build).data or []
        rows.extend(batch)
        if len(batch) < page:
            return rows
        start += page


def _coverage(rows):
    total = len(rows)
    times = sum(1 for r in rows if r.get('finish_time') is not None)
    margins = sum(1 for r in rows if r.get('margin') is not None)
    return {
        'runners': total,
        'finish_time': times,
        'margin': margins,
        'finish_time_rate': times / total if total else 0.0,
        'margin_rate': margins / total if total else 0.0,
    }


def _group(race_meta, by_race, key_fn):
    groups = defaultdict(list)
    for race_id, rows in by_race.items():
        meta = race_meta.get(race_id)
        if meta:
            groups[key_fn(meta)].extend(rows)
    return {key: _coverage(rows) for key, rows in sorted(groups.items(),
                                                         key=lambda kv: str(kv[0]))}


def build_quality(races, runners):
    """Aggregate coverage and quality checks over finished runners."""
    race_meta = {r['race_id']: r for r in races}
    by_race = defaultdict(list)
    for row in runners:
        if row.get('finish_position'):
            by_race[row['race_id']].append(row)
    tracked_ids = [rid for rid in by_race if rid in race_meta]
    finished = [row for rid in tracked_ids for row in by_race[rid]]

    issues = []
    for row in finished:
        finish_time = row.get('finish_time')
        margin = row.get('margin')
        if finish_time is not None and not (
                FINISH_TIME_MIN <= float(finish_time) <= FINISH_TIME_MAX):
            issues.append({'race_id': row['race_id'], 'horse_no': row.get('horse_no'),
                           'field': 'finish_time', 'value': finish_time})
        if margin is not None and not 0 <= float(margin) <= MARGIN_OUTLIER:
            issues.append({'race_id': row['race_id'], 'horse_no': row.get('horse_no'),
                           'field': 'margin', 'value': margin})

    winner_margin_positive = []
    winner_not_fastest = []
    for race_id in tracked_ids:
        rows = by_race[race_id]
        times = [float(r['finish_time']) for r in rows if r.get('finish_time') is not None]
        winner = next((r for r in rows if r.get('finish_position') == 1), None)
        if winner is None:
            continue
        if winner.get('margin') not in (None, 0, 0.0):
            winner_margin_positive.append({'race_id': race_id,
                                           'margin': winner.get('margin')})
        if times and winner.get('finish_time') is not None \
                and float(winner['finish_time']) > min(times) + 0.01:
            winner_not_fastest.append({'race_id': race_id,
                                       'winner': winner['finish_time'],
                                       'fastest': min(times)})

    monthly = _group(race_meta, by_race,
                     lambda m: str(m.get('race_date') or '')[:7] or 'UNK')
    low_months = [month for month, cov in monthly.items()
                  if cov['finish_time_rate'] < 0.5]
    low_margin_months = [month for month, cov in monthly.items()
                         if cov['margin_rate'] < 0.5]
    reasons = []
    if low_months:
        reasons.append('低覆蓋月份（finish_time <50%）：' + ', '.join(sorted(low_months))
                       + '；舊版 results parser 只寫 finish_position，本 commit 起新抓取會寫入，'
                         '歷史月份需重抓才有數。')
    if low_margin_months:
        reasons.append('低覆蓋月份（margin <50%）：' + ', '.join(sorted(low_margin_months))
                       + '；舊 scraper 未寫入馬位，同樣要重抓。')
    class_names = {m.get('class_level') for m in races if m.get('class_level')}
    if any(name.startswith('Class ') for name in class_names) and \
            any(name.startswith('第') for name in class_names):
        reasons.append('班次命名新舊並存（Class N vs 第N班）：Class N 屬舊資料，'
                       '新抓取統一寫第N班。')

    return {
        'races': len(tracked_ids),
        'runners': len(finished),
        'overall': _coverage(finished),
        'by_venue': _group(race_meta, by_race, lambda m: m.get('venue') or 'UNK'),
        'by_distance': _group(race_meta, by_race, lambda m: m.get('distance')),
        'by_class': _group(race_meta, by_race, lambda m: m.get('class_level') or '未分類'),
        'by_month': monthly,
        'issues': issues,
        'winner_margin_positive': winner_margin_positive,
        'winner_not_fastest': winner_not_fastest,
        'reasons': reasons,
    }


def build_speed_baseline(races, runners, min_races=5):
    """Winning-time baseline per venue + distance + course; display only."""
    race_meta = {r['race_id']: r for r in races}
    by_race = defaultdict(list)
    for row in runners:
        if row.get('finish_position'):
            by_race[row['race_id']].append(row)

    groups = defaultdict(list)
    for race_id, rows in by_race.items():
        meta = race_meta.get(race_id)
        if not meta or meta.get('distance') is None:
            continue
        times = [float(r['finish_time']) for r in rows if r.get('finish_time') is not None]
        winner = next((r for r in rows if r.get('finish_position') == 1
                       and r.get('finish_time') is not None), None)
        if not winner or len(times) < 4:
            continue
        key = (meta.get('venue') or 'UNK', meta.get('distance'),
               meta.get('track_course') or '未分類')
        groups[key].append({
            'winner_time': float(winner['finish_time']),
            'field_mean': mean(times),
            'runners': len(times),
        })

    baseline = []
    for (venue, distance, course), items in sorted(
            groups.items(), key=lambda kv: (str(kv[0][0]), kv[0][1] or 0, str(kv[0][2]))):
        winner_times = [i['winner_time'] for i in items]
        baseline.append({
            'venue': venue,
            'distance': distance,
            'track_course': course,
            'races': len(items),
            'sufficient': len(items) >= min_races,
            'winner_mean': round(mean(winner_times), 2),
            'winner_median': round(median(winner_times), 2),
            'winner_std': round(pstdev(winner_times), 2) if len(items) > 1 else 0.0,
            'winner_min': round(min(winner_times), 2),
            'winner_max': round(max(winner_times), 2),
            'field_mean': round(mean(i['field_mean'] for i in items), 2),
        })
    return baseline


def _pct(value):
    return f'{value * 100:.1f}%'


def render_markdown(quality, baseline, generated):
    overall = quality['overall']
    lines = [
        f'# 賽果數據品質／覆蓋率／締速基準（{generated}）',
        '',
        '- 唯讀報表；finish_time（秒）與 margin（馬位）只作展示，不入任何權重。',
        f'- 已完成賽事：{quality["races"]} 場；有完成名次的馬：{quality["runners"]} 匹。',
        f'- 整體覆蓋：finish_time {_pct(overall["finish_time_rate"])}'
        f'（{overall["finish_time"]}/{overall["runners"]}）、'
        f'margin {_pct(overall["margin_rate"])}（{overall["margin"]}/{overall["runners"]}）。',
        '',
        '## 覆蓋率：場地',
        '',
        '| venue | 馬數 | finish_time | 比率 | margin | 比率 |',
        '|---|---|---|---|---|---|',
    ]
    for venue, cov in quality['by_venue'].items():
        lines.append(f'| {venue} | {cov["runners"]} | {cov["finish_time"]} '
                     f'| {_pct(cov["finish_time_rate"])} | {cov["margin"]} '
                     f'| {_pct(cov["margin_rate"])} |')
    lines += [
        '',
        '## 覆蓋率：途程',
        '',
        '| 距離 | 馬數 | finish_time | 比率 | margin | 比率 |',
        '|---|---|---|---|---|---|',
    ]
    for distance, cov in quality['by_distance'].items():
        lines.append(f'| {distance} | {cov["runners"]} | {cov["finish_time"]} '
                     f'| {_pct(cov["finish_time_rate"])} | {cov["margin"]} '
                     f'| {_pct(cov["margin_rate"])} |')
    lines += [
        '',
        '## 覆蓋率：班次',
        '',
        '| 班次 | 馬數 | finish_time | 比率 | margin | 比率 |',
        '|---|---|---|---|---|---|',
    ]
    for class_level, cov in quality['by_class'].items():
        lines.append(f'| {class_level} | {cov["runners"]} | {cov["finish_time"]} '
                     f'| {_pct(cov["finish_time_rate"])} | {cov["margin"]} '
                     f'| {_pct(cov["margin_rate"])} |')
    lines += [
        '',
        '## 覆蓋率：月份（低覆蓋原因）',
        '',
        '| 月份 | 馬數 | finish_time | 比率 | margin | 比率 |',
        '|---|---|---|---|---|---|',
    ]
    for month, cov in quality['by_month'].items():
        lines.append(f'| {month} | {cov["runners"]} | {cov["finish_time"]} '
                     f'| {_pct(cov["finish_time_rate"])} | {cov["margin"]} '
                     f'| {_pct(cov["margin_rate"])} |')
    if quality['reasons']:
        lines += [''] + [f'- {reason}' for reason in quality['reasons']]
    lines += [
        '',
        '## 品質檢查',
        '',
        f'- 超範圍 finish_time：{sum(1 for i in quality["issues"] if i["field"] == "finish_time")} 行；'
        f'margin >30 馬位（尾隨馬，仍保留）：{sum(1 for i in quality["issues"] if i["field"] == "margin")} 行。',
        f'- 頭馬 margin > 0：{len(quality["winner_margin_positive"])} 場。',
        f'- 頭馬非全場最快：{len(quality["winner_not_fastest"])} 場。',
    ]
    for issue in quality['issues'][:10]:
        lines.append(f'  - {issue["race_id"]} 馬{issue["horse_no"]} '
                     f'{issue["field"]}={issue["value"]}')
    for race in quality['winner_not_fastest'][:10]:
        lines.append(f'  - {race["race_id"]} 頭馬 {race["winner"]}s > 最快 {race["fastest"]}s')
    lines += [
        '',
        '## 締速基準（同場同程同場地；只作展示，未入權重）',
        '',
        '| venue | 距離 | 場地 | 賽事 | 樣本足夠(≥5) | 頭馬平均(秒) | 中位數 | 標準差 | 最快 | 最慢 | 全場平均 |',
        '|---|---|---|---|---|---|---|---|---|---|---|',
    ]
    for row in baseline:
        lines.append(
            f'| {row["venue"]} | {row["distance"]} | {row["track_course"]} '
            f'| {row["races"]} | {"是" if row["sufficient"] else "否（不結論）"} '
            f'| {row["winner_mean"]} | {row["winner_median"]} | {row["winner_std"]} '
            f'| {row["winner_min"]} | {row["winner_max"]} | {row["field_mean"]} |')
    lines += [
        '',
        '未達 5 場的組合只列數字、不結論；`speed_engine` 與 `finish_time_margin` flag 維持 off。',
        '',
    ]
    return '\n'.join(lines)


def generate(supabase=None, date=None, out=None, baseline_out=None, min_races=5):
    supabase = supabase or get_supabase()
    generated = date or datetime.now(HKT).strftime('%Y-%m-%d')
    races = _paginate(supabase, 'races',
                      'race_id,race_date,venue,race_no,distance,class_level,'
                      'track_course,going,is_finished', 'race_id')
    runners = _paginate(
        supabase, 'race_runners',
        'race_id,horse_no,finish_position,finish_time,margin', 'runner_id',
        extra=lambda q: q.not_.is_('finish_position', 'null'))

    quality = build_quality(races, runners)
    baseline = build_speed_baseline(races, runners, min_races=min_races)
    markdown = render_markdown(quality, baseline, generated)

    out = out or os.path.join(ROOT, 'reports', f'results_quality_{generated}.md')
    baseline_out = baseline_out or os.path.join(
        ROOT, 'reports', f'speed_baseline_{generated}.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(markdown)
    with open(baseline_out, 'w', encoding='utf-8') as fh:
        json.dump({'generated': generated, 'groups': baseline}, fh,
                  ensure_ascii=False, indent=2)

    try:
        retry_supabase(lambda: supabase.table('pipeline_status').upsert({
            'id': REPORT_ID,
            'last_run': datetime.now(HKT).isoformat(),
            'status_json': {
                'date': generated,
                'path': os.path.relpath(out, ROOT),
                'races': quality['races'],
                'runners': quality['runners'],
                'finish_time_rate': round(quality['overall']['finish_time_rate'], 4),
                'margin_rate': round(quality['overall']['margin_rate'], 4),
                'baseline_groups': len(baseline),
                'insufficient_groups': sum(1 for g in baseline if not g['sufficient']),
                'updated_at': datetime.now(HKT).isoformat(),
            },
        }, on_conflict='id').execute())
    except Exception as e:
        print(f'[ResultsQuality] WARN summary not persisted: {e}')
    return out, baseline_out, quality, baseline


def main():
    parser = argparse.ArgumentParser(description='Results quality / coverage / speed baseline')
    parser.add_argument('--date', default=datetime.now(HKT).strftime('%Y-%m-%d'))
    parser.add_argument('--min-races', type=int, default=5)
    args = parser.parse_args()
    out, baseline_out, quality, baseline = generate(
        date=args.date, min_races=args.min_races)
    print(f"[ResultsQuality] {quality['races']} races, {quality['runners']} runners, "
          f"finish_time {quality['overall']['finish_time_rate'] * 100:.1f}%, "
          f"baseline groups {len(baseline)} -> {out} | {baseline_out}")


if __name__ == '__main__':
    main()