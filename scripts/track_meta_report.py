#!/usr/bin/env python3
"""Descriptive going / track_course report (Line 2-B, read-only).

Coverage by venue/month, going distribution by surface, and how much variation
actually exists. Nothing here enters P_model: a track-bias model stays off
until going shows variation and per-bucket samples are large enough.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase
from track_meta import normalize_going, normalize_track_course

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_ID = 'track_meta_report'


def _paginate(supabase, table, columns, order_col):
    rows, start, page = [], 0, 1000
    while True:
        batch = retry_supabase(
            lambda s=start: supabase.table(table).select(columns).order(order_col)
            .range(s, s + page - 1).execute()).data or []
        rows.extend(batch)
        if len(batch) < page:
            return rows
        start += page


def _rate(part, total):
    return part / total if total else 0.0


def build_report(races):
    total = len(races)
    going_ok = track_ok = 0
    going_counter = Counter()
    surface_going = defaultdict(Counter)
    by_venue = defaultdict(lambda: {'races': 0, 'going': 0, 'track_course': 0,
                                    'going_values': Counter()})
    by_month = defaultdict(lambda: {'races': 0, 'going': 0, 'track_course': 0})
    invalid = Counter()
    meeting_surfaces = defaultdict(set)
    month_going = defaultdict(set)

    for race in races:
        raw_going = race.get('going')
        raw_course = race.get('track_course')
        going = normalize_going(raw_going)
        course = normalize_track_course(raw_course)
        venue = race.get('venue') or 'UNK'
        month = str(race.get('race_date') or '')[:7] or 'UNK'
        date = str(race.get('race_date') or '')[:10]

        by_venue[venue]['races'] += 1
        by_month[month]['races'] += 1
        if going:
            going_ok += 1
            going_counter[going] += 1
            by_venue[venue]['going'] += 1
            by_venue[venue]['going_values'][going] += 1
            by_month[month]['going'] += 1
            month_going[month].add(going)
            surface_going[course or '未分類'][going] += 1
        elif raw_going:
            invalid[raw_going[:40]] += 1
        if course:
            track_ok += 1
            by_venue[venue]['track_course'] += 1
            by_month[month]['track_course'] += 1
            meeting_surfaces[(date, venue)].add(course)

    for stats in by_venue.values():
        stats['going_values'] = dict(stats['going_values'].most_common())

    multi_surface = sum(1 for surfaces in meeting_surfaces.values()
                        if len(surfaces) > 1)
    non_good = sum(1 for r in races
                   if normalize_going(r.get('going')) not in (None, '好地'))
    venue_variation = {
        venue: {
            'distinct_going': len(stats['going_values']),
            'non_good_share': _rate(sum(stats['going_values'].values())
                                    - stats['going_values'].get('好地', 0),
                                    sum(stats['going_values'].values())),
        }
        for venue, stats in by_venue.items()
    }

    return {
        'races': total,
        'going': going_ok,
        'going_rate': _rate(going_ok, total),
        'track_course': track_ok,
        'track_course_rate': _rate(track_ok, total),
        'going_distribution': dict(going_counter.most_common()),
        'going_distinct': len(going_counter),
        'non_good_races': non_good,
        'non_good_share': _rate(non_good, going_ok),
        'by_venue': dict(by_venue),
        'by_month': dict(sorted(by_month.items())),
        'surface_going': {surface: dict(counter.most_common())
                          for surface, counter in sorted(surface_going.items())},
        'venue_variation': venue_variation,
        'month_distinct_going': {m: sorted(values)
                                 for m, values in sorted(month_going.items())},
        'multi_surface_meetings': multi_surface,
        'invalid_going': dict(invalid.most_common(10)),
        'invalid_going_values': sum(invalid.values()),
    }


def _pct(value):
    return f'{value * 100:.1f}%'


def render_markdown(report, generated):
    lines = [
        f'# 場地狀況／賽道覆蓋與變異（{generated}）',
        '',
        '- 唯讀描述性報表；going／track_course 只作展示，不入任何權重或跑道偏差模型。',
        f'- 賽事：{report["races"]} 場；going 可解析 {report["going"]} 場'
        f'（{_pct(report["going_rate"])}）；track_course {report["track_course"]} 場'
        f'（{_pct(report["track_course_rate"])}）。',
        '',
        '## 覆蓋率：場地',
        '',
        '| venue | 賽事 | going | 比率 | track_course | 比率 |',
        '|---|---|---|---|---|---|',
    ]
    for venue, stats in sorted(report['by_venue'].items()):
        n = stats['races']
        lines.append(f'| {venue} | {n} | {stats["going"]} | {_pct(_rate(stats["going"], n))} '
                     f'| {stats["track_course"]} | {_pct(_rate(stats["track_course"], n))} |')

    lines += ['', '## 覆蓋率：月份', '',
              '| 月份 | 賽事 | going | 比率 | track_course | 比率 |',
              '|---|---|---|---|---|---|']
    for month, stats in report['by_month'].items():
        n = stats['races']
        lines.append(f'| {month} | {n} | {stats["going"]} | {_pct(_rate(stats["going"], n))} '
                     f'| {stats["track_course"]} | {_pct(_rate(stats["track_course"], n))} |')

    lines += ['', '## going 分佈（按賽道）', '',
              '| 賽道 | going | 賽事 |', '|---|---|---|']
    for surface, values in report['surface_going'].items():
        for going, count in values.items():
            lines.append(f'| {surface} | {going} | {count} |')

    lines += ['', '## 變異程度', '',
              f'- 不同 going 值：{report["going_distinct"]} 種；非「好地」賽事 '
              f'{report["non_good_races"]} 場（{_pct(report["non_good_share"])}）。',
              f'- 同一賽馬日同時出現草地與全天候跑道：{report["multi_surface_meetings"]} 日。',
              '',
              '| venue | 不同 going | 非好地比率 |', '|---|---|---|']
    for venue, stats in sorted(report['venue_variation'].items()):
        lines.append(f'| {venue} | {stats["distinct_going"]} | {_pct(stats["non_good_share"])} |')

    lines += ['', '| 月份 | 不同 going |', '|---|---|']
    for month, values in report['month_distinct_going'].items():
        lines.append(f'| {month} | {", ".join(values)} |')

    if report['invalid_going']:
        lines += ['', '## 無法解析的 going（需重抓）', '']
        for value, count in report['invalid_going'].items():
            lines.append(f'- `{value}` × {count}')
        lines.append('')

    verdict = ('有變異，但未做跑道偏差模型；先累積每個 going×賽道桶 ≥30 場再考慮。'
               if report['going_distinct'] > 1 else
               'going 幾乎無變異：維持 off，不建跑道偏差模型。')
    lines += [
        '',
        '## 結論（描述性）',
        '',
        f'- {verdict}',
        '- 現時無任何 going／track_course 權重；`speed_engine`、`finish_time_margin` 等 flags 全部維持 off。',
        '',
    ]
    return '\n'.join(lines)


def generate(supabase=None, date=None, out=None):
    supabase = supabase or get_supabase()
    generated = date or datetime.now(HKT).strftime('%Y-%m-%d')
    races = _paginate(supabase, 'races',
                      'race_id,race_date,venue,race_no,distance,going,track_course',
                      'race_id')
    races = [r for r in races if str(r.get('race_date') or '')[:10] <= generated]
    report = build_report(races)
    markdown = render_markdown(report, generated)

    out = out or os.path.join(ROOT, 'reports', f'track_meta_{generated}.md')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(markdown)
    json_path = out.replace('.md', '.json')
    with open(json_path, 'w', encoding='utf-8') as fh:
        json.dump({'generated': generated, **report}, fh, ensure_ascii=False, indent=2)

    try:
        retry_supabase(lambda: supabase.table('pipeline_status').upsert({
            'id': REPORT_ID,
            'last_run': datetime.now(HKT).isoformat(),
            'status_json': {
                'date': generated,
                'path': os.path.relpath(out, ROOT),
                'races': report['races'],
                'going_rate': round(report['going_rate'], 4),
                'track_course_rate': round(report['track_course_rate'], 4),
                'going_distinct': report['going_distinct'],
                'invalid_going_values': report['invalid_going_values'],
                'updated_at': datetime.now(HKT).isoformat(),
            },
        }, on_conflict='id').execute())
    except Exception as e:
        print(f'[TrackMetaReport] WARN summary not persisted: {e}')
    return out, json_path, report


def main():
    parser = argparse.ArgumentParser(description='Going/track_course descriptive report')
    parser.add_argument('--date', default=datetime.now(HKT).strftime('%Y-%m-%d'))
    args = parser.parse_args()
    out, json_path, report = generate(date=args.date)
    print(f"[TrackMetaReport] {report['races']} races, going {report['going_rate'] * 100:.1f}%, "
          f"track {report['track_course_rate'] * 100:.1f}%, "
          f"{report['going_distinct']} going values -> {out} | {json_path}")


if __name__ == '__main__':
    main()