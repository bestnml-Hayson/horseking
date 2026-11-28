#!/usr/bin/env python3
"""Snapshot completeness report (P2 follow-up).

Read-only: pulls every captured pre-race price (table, else the
pipeline_status fallback) and reports, per race:
  * which of the four buckets exist,
  * horse coverage and odds non-empty rate,
  * available_at completeness,
  * observed capture windows vs the nominal bucket windows,
  * why a race is not complete.
Grouped by venue and field size, with the X/50 gate count on top.
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from statistics import mean
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase
import odds_snapshots as O

BAND_ORDER = ('≤10', '11-12', '13-14', '15+')
IDEAL_WINDOW = {'open': (60, 180), '60m': (16, 60), '15m': (6, 15), 'close': (0, 5)}


def field_band(size):
    if size <= 10:
        return '≤10'
    if size <= 12:
        return '11-12'
    if size <= 14:
        return '13-14'
    return '15+'


def parse_ts(value):
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=HKT)


def bucket_offset(minutes, bucket):
    """Minutes a capture falls outside its nominal bucket window."""
    if minutes is None:
        return None
    lo, hi = IDEAL_WINDOW[bucket]
    if minutes < lo:
        return lo - minutes
    if minutes > hi:
        return minutes - hi
    return 0.0


def _fetch_in_chunks(supabase, table, columns, key, values, chunk=40):
    out = []
    values = list(values)
    for i in range(0, len(values), chunk):
        part = values[i:i + chunk]
        start = 0
        while True:
            resp = retry_supabase(lambda: supabase.table(table).select(columns)
                                  .in_(key, part).range(start, start + 999).execute())
            batch = resp.data or []
            out.extend(batch)
            if len(batch) < 1000:
                break
            start += 1000
    return out


def build_report(rows, races_by_id, runners_by_race):
    """Pure aggregation so the markdown stays dumb."""
    by_race = defaultdict(list)
    for row in rows:
        by_race[row.get('race_id')].append(row)

    races = []
    for race_id, items in sorted(by_race.items()):
        meta = races_by_id.get(race_id) or {}
        field = runners_by_race.get(race_id) or set()
        horses = {r.get('horse_id') for r in items if r.get('horse_id')}
        buckets = defaultdict(list)
        offsets = []
        available_ok = 0
        for row in items:
            ts = parse_ts(row.get('available_at'))
            if ts is not None:
                available_ok += 1
            minutes = O.minutes_to_post(meta, ts) if ts is not None else None
            bucket = row.get('snapshot_type')
            buckets[bucket].append(minutes)
            off = bucket_offset(minutes, bucket) if bucket in IDEAL_WINDOW else None
            if off is not None:
                offsets.append(off)

        missing = [b for b in O.BUCKETS if not buckets.get(b)]
        reasons = []
        if missing:
            reasons.append('缺 bucket: ' + '/'.join(missing))
        if not meta.get('race_time'):
            reasons.append('race_time 缺失（無法計偏移）')
        coverage = (len(horses) / len(field)) if field else None
        if coverage is not None and coverage < 1:
            reasons.append(f'{len(field) - len(horses & field)} 匹無快照')
        if available_ok < len(items):
            reasons.append(f'{len(items) - available_ok} 行 available_at 無效')

        races.append({
            'race_id': race_id,
            'race_no': meta.get('race_no'),
            'venue': meta.get('venue') or 'UNK',
            'field_size': len(field),
            'buckets': {b: len(buckets.get(b, [])) for b in O.BUCKETS},
            'missing': missing,
            'complete': not missing,
            'horses': len(horses),
            'coverage': coverage,
            'available_rate': available_ok / len(items) if items else 0,
            'odds_rate': sum(1 for r in items if (r.get('odds') or 0) > 1.0) / len(items),
            'windows': {b: (min(v), max(v)) for b, v in buckets.items() if any(x is not None for x in v)},
            'offset_avg': mean(offsets) if offsets else None,
            'offset_max': max(offsets) if offsets else None,
            'reasons': reasons,
        })

    groups = defaultdict(list)
    for r in races:
        groups[(r['venue'], field_band(r['field_size']))].append(r)
    summary = []
    for (venue, band), group in sorted(groups.items(),
                                       key=lambda kv: (kv[0][0], BAND_ORDER.index(kv[0][1]))):
        cov = [r['coverage'] for r in group if r['coverage'] is not None]
        offs = [r['offset_avg'] for r in group if r['offset_avg'] is not None]
        summary.append({
            'venue': venue,
            'band': band,
            'races': len(group),
            'complete': sum(1 for r in group if r['complete']),
            'coverage': mean(cov) if cov else None,
            'available_rate': mean(r['available_rate'] for r in group),
            'offset_avg': mean(offs) if offs else None,
        })
    return {'races': races, 'summary': summary}


def _pct(value):
    return 'n/a' if value is None else f'{value * 100:.0f}%'


def _window(window):
    if not window:
        return '—'
    lo, hi = window
    return f'{lo:.0f}–{hi:.0f}'


def render_markdown(report, progress, store, generated):
    lines = [
        f'# 賽前賠率快照完整度報表（{generated}）',
        '',
        f'- 資料來源：`{store}`（表未建立時為 `pipeline_status.odds_snapshots` fallback）',
        f'- 完整賽事：**{progress["complete_pre_race_races"]}/{progress["target"]}**'
        f'（已追蹤 {progress["total_races"]} 場；四 bucket 齊全才計入）',
        '- Bucket 邊界（距開跑）：open >60、60m 16–60、15m 6–15、close ≤5 分鐘；'
        '偏移 = 實際抓取時間落在名義 window 以外的分鐘數（open 以 60–180 為目標）。',
        '- 本報表唯讀，不會改動任何預測或預設。',
        '',
    ]
    if not report['races']:
        lines += [
            '## 結果',
            '',
            '目前 **0 場**已收集快照。原因：尚未有 race-day tick 在市前窗口內抓到賠率，'
            '或表／fallback 仍未有寫入。下一次賽日 tick 後重跑：',
            '',
            '```bash',
            'python scripts/odds_snapshot_report.py',
            '```',
            '',
        ]
        return '\n'.join(lines)

    lines += [
        '## 分組摘要',
        '',
        '| 場地 | 馬數 | 賽事 | 完整 | 完整率 | 平均馬匹覆蓋 | 平均 available_at | 平均偏移(分) |',
        '|---|---|---|---|---|---|---|---|',
    ]
    for g in report['summary']:
        rate = g['complete'] / g['races'] if g['races'] else 0
        offset = 'n/a' if g['offset_avg'] is None else f"{g['offset_avg']:.1f}"
        lines.append(
            f"| {g['venue']} | {g['band']} | {g['races']} | {g['complete']} | {rate * 100:.0f}% "
            f"| {_pct(g['coverage'])} | {_pct(g['available_rate'])} | {offset} |")
    lines += [
        '',
        '## 每場明細',
        '',
        '| 賽事 | 場地 | 馬數 | open | 60m | 15m | close | 覆蓋 | 賠率非空 | available_at | 捕獲窗口(分) | 偏移(avg/max) | 缺失原因 |',
        '|---|---|---|---|---|---|---|---|---|---|---|---|---|',
    ]
    for r in report['races']:
        label = f"{r['race_id']}" + (f" (R{r['race_no']})" if r['race_no'] else '')
        bucket_cells = ' | '.join('✓' if r['buckets'][b] else '—' for b in O.BUCKETS)
        windows = '; '.join(f'{b} {_window(r["windows"].get(b))}' for b in O.BUCKETS
                            if r['windows'].get(b))
        off = ('n/a' if r['offset_avg'] is None
               else f"{r['offset_avg']:.1f}/{r['offset_max']:.1f}")
        lines.append(
            f"| {label} | {r['venue']} | {r['field_size']} | {bucket_cells} "
            f"| {_pct(r['coverage'])} | {_pct(r['odds_rate'])} | {_pct(r['available_rate'])} "
            f"| {windows or '—'} | {off} | {'; '.join(r['reasons']) or '—'} |")
    lines.append('')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Pre-race odds snapshot completeness report')
    parser.add_argument('--date', default=datetime.now(HKT).strftime('%Y-%m-%d'))
    parser.add_argument('--out', default=None)
    args = parser.parse_args()

    supabase = get_supabase()
    rows, store = O.fetch_snapshot_rows(supabase)
    progress = O.snapshot_progress(supabase)

    race_ids = sorted({r.get('race_id') for r in rows if r.get('race_id')})
    races_by_id = {}
    runners_by_race = defaultdict(set)
    if race_ids:
        for row in _fetch_in_chunks(
                supabase, 'races',
                'race_id,race_no,venue,race_date,race_time', 'race_id', race_ids):
            races_by_id[row['race_id']] = row
        for row in _fetch_in_chunks(
                supabase, 'race_runners', 'race_id,horse_id', 'race_id', race_ids):
            if row.get('horse_id'):
                runners_by_race[row['race_id']].add(row['horse_id'])

    report = build_report(rows, races_by_id, runners_by_race)
    markdown = render_markdown(report, progress, store, args.date)
    out = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'reports', f'odds_snapshot_completeness_{args.date}.md')
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(markdown)
    print(f"[SnapshotReport] {len(report['races'])} races, "
          f"complete {progress['complete_pre_race_races']}/{progress['target']} -> {out}")


if __name__ == '__main__':
    main()