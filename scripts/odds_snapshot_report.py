#!/usr/bin/env python3
"""Snapshot completeness reports (P2 follow-up, Line 1 monitoring).

Read-only over odds_snapshots (table, else the pipeline_status fallback).

Daily report: one row per tracked race with the agreed fields
  race_id, race_date, venue, n_runners, n_horses_with_4_buckets,
  odds_nonnull_rate, available_at_complete_rate, bucket_offset_sec,
  missing_reason
plus venue x field-size groups and the X/50 gate.

Weekly report: which bucket goes missing most often, bucket_offset_sec drift,
HV/ST differences, and an explicit relax-or-fix recommendation when a bucket
is chronically absent. Partial races are never reported as complete.

A race counts as complete only when all four buckets carry at least one valid
price: odds > 1 and available_at recorded. SP copies are never written here.
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase
import odds_snapshots as O

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAND_ORDER = ('≤10', '11-12', '13-14', '15+')
IDEAL_WINDOW = {'open': (60, 180), '60m': (16, 60), '15m': (6, 15), 'close': (0, 5)}
REPORT_ID = 'odds_snapshot_report'
WEEKLY_ID = 'odds_snapshot_weekly_report'


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


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


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
        buckets = defaultdict(int)
        bucket_minutes = defaultdict(list)
        per_horse = defaultdict(set)
        offsets_sec = []
        odds_ok = 0
        avail_ok = 0
        for row in items:
            bucket = row.get('snapshot_type')
            valid = O._valid_row(row)
            ts = parse_ts(row.get('available_at'))
            if valid:
                odds_ok += 1
            if ts is not None:
                avail_ok += 1
            minutes = O.minutes_to_post(meta, ts) if ts is not None else None
            if valid and bucket in O.BUCKETS:
                buckets[bucket] += 1
                horse_id = row.get('horse_id')
                if horse_id:
                    per_horse[horse_id].add(bucket)
                if minutes is not None:
                    bucket_minutes[bucket].append(minutes)
                    off = bucket_offset(minutes, bucket)
                    if off is not None:
                        offsets_sec.append(off * 60)

        missing = [b for b in O.BUCKETS if buckets[b] == 0]
        horses_4 = sum(1 for bs in per_horse.values() if len(bs) == len(O.BUCKETS))
        n_runners = len(field) or len(per_horse)
        reasons = []
        if missing:
            reasons.append('缺 bucket: ' + '/'.join(missing))
        if not meta.get('race_time'):
            reasons.append('race_time 缺失（無法計偏移）')
        if field and len(per_horse) < len(field):
            reasons.append(f'{len(field - set(per_horse))} 匹無快照')
        if odds_ok < len(items):
            reasons.append(f'{len(items) - odds_ok} 行賠率無效（非空但 ≤1）')
        if avail_ok < len(items):
            reasons.append(f'{len(items) - avail_ok} 行 available_at 無效')

        races.append({
            'race_id': race_id,
            'race_date': str(meta.get('race_date') or '')[:10],
            'race_no': meta.get('race_no'),
            'venue': meta.get('venue') or 'UNK',
            'n_runners': n_runners,
            'n_horses_with_4_buckets': horses_4,
            'odds_nonnull_rate': odds_ok / len(items) if items else 0.0,
            'available_at_complete_rate': avail_ok / len(items) if items else 0.0,
            'bucket_offset_sec': {
                'avg': mean(offsets_sec) if offsets_sec else None,
                'max': max(offsets_sec) if offsets_sec else None,
            },
            'missing_reason': '; '.join(reasons),
            'reasons': reasons,
            'buckets': {b: buckets[b] for b in O.BUCKETS},
            'missing': missing,
            'complete': not missing,
            'horses': len(per_horse),
            'coverage': (len(per_horse) / len(field)) if field else None,
            'windows': {b: (min(v), max(v)) for b, v in bucket_minutes.items() if v},
        })

    groups = defaultdict(list)
    for r in races:
        groups[(r['venue'], field_band(r['n_runners']))].append(r)
    summary = []
    for (venue, band), group in sorted(groups.items(),
                                       key=lambda kv: (kv[0][0], BAND_ORDER.index(kv[0][1]))):
        offs = [r['bucket_offset_sec']['avg'] for r in group
                if r['bucket_offset_sec']['avg'] is not None]
        complete = sum(1 for r in group if r['complete'])
        summary.append({
            'venue': venue,
            'band': band,
            'races': len(group),
            'complete': complete,
            'complete_rate': complete / len(group) if group else 0.0,
            'horses_4': mean(r['n_horses_with_4_buckets'] for r in group),
            'odds_rate': mean(r['odds_nonnull_rate'] for r in group),
            'available_rate': mean(r['available_at_complete_rate'] for r in group),
            'offset_avg_sec': mean(offs) if offs else None,
        })
    return {'races': races, 'summary': summary}


def _pct(value):
    return 'n/a' if value is None else f'{value * 100:.0f}%'


def _window(window):
    if not window:
        return '—'
    lo, hi = window
    return f'{lo:.0f}–{hi:.0f}'


def _offset_cell(offset):
    avg, mx = offset.get('avg'), offset.get('max')
    if avg is None or mx is None:
        return 'n/a'
    return f'{avg:.0f}/{mx:.0f}'


def render_markdown(report, progress, store, generated):
    lines = [
        f'# 賽前賠率快照完整度報表（{generated}）',
        '',
        f'- 資料來源：`{store}`（表未建立時為 `pipeline_status.odds_snapshots` fallback）',
        f'- 完整賽事：**{progress["complete_pre_race_races"]}/{progress["target"]}**'
        f'（已追蹤 {progress["total_races"]} 場；四 bucket 齊全才計入）',
        '- 完整定義：open/60m/15m/close 四個 bucket 各至少一行有效賠率'
        '（odds > 1、available_at 可解析）；partial 一律不當完整。',
        '- Bucket 邊界（距開跑）：open >60、60m 16–60、15m 6–15、close ≤5 分鐘；'
        'bucket_offset_sec = 抓取時間落在名義 window 以外的秒數（平均/最大，open 以 60–180 為目標）。',
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
        '| 場地 | 馬數 | 賽事 | 完整 | 完整率 | 平均四 bucket 齊馬數 | 賠率有效率 | available_at 完整率 | 偏移(秒, 平均) |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for g in report['summary']:
        offset = 'n/a' if g['offset_avg_sec'] is None else f"{g['offset_avg_sec']:.0f}"
        lines.append(
            f"| {g['venue']} | {g['band']} | {g['races']} | {g['complete']} "
            f"| {g['complete_rate'] * 100:.0f}% | {g['horses_4']:.1f} "
            f"| {_pct(g['odds_rate'])} | {_pct(g['available_rate'])} | {offset} |")
    lines += [
        '',
        '## 每場明細',
        '',
        '| race_id | race_date | venue | n_runners | n_horses_with_4_buckets '
        '| odds_nonnull_rate | available_at_complete_rate | bucket_offset_sec | missing_reason |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for r in report['races']:
        lines.append(
            f"| {r['race_id']} | {r['race_date'] or '—'} | {r['venue']} | {r['n_runners']} "
            f"| {r['n_horses_with_4_buckets']} | {_pct(r['odds_nonnull_rate'])} "
            f"| {_pct(r['available_at_complete_rate'])} | {_offset_cell(r['bucket_offset_sec'])} "
            f"| {r['missing_reason'] or '—'} |")
    lines += [
        '',
        '## 捕獲窗口（分鐘，距離開跑）',
        '',
        '| race_id | open | 60m | 15m | close |',
        '|---|---|---|---|---|',
    ]
    for r in report['races']:
        cells = ' | '.join(_window(r['windows'].get(b)) for b in O.BUCKETS)
        lines.append(f"| {r['race_id']} | {cells} |")
    lines.append('')
    return '\n'.join(lines)


def build_weekly(report, days=7, today=None):
    """Aggregate tracked races inside the trailing window; pure and testable."""
    today = today or datetime.now(HKT).date()
    start = today - timedelta(days=max(days, 1) - 1)
    races = []
    for r in report['races']:
        d = parse_date(r.get('race_date'))
        if d is None or d >= start:
            races.append(r)

    tracked = len(races)
    bucket_missing = {
        b: sum(1 for r in races if r['buckets'].get(b, 0) == 0)
        for b in O.BUCKETS
    }
    chronic = [b for b in O.BUCKETS
               if tracked and bucket_missing[b] >= 0.8 * tracked]
    offset_avgs = [r['bucket_offset_sec']['avg'] for r in races
                   if r['bucket_offset_sec']['avg'] is not None]
    offset_maxes = [r['bucket_offset_sec']['max'] for r in races
                    if r['bucket_offset_sec']['max'] is not None]

    venues = {}
    for venue in sorted({r['venue'] for r in races}):
        group = [r for r in races if r['venue'] == venue]
        v_offs = [r['bucket_offset_sec']['avg'] for r in group
                  if r['bucket_offset_sec']['avg'] is not None]
        v_max = [r['bucket_offset_sec']['max'] for r in group
                 if r['bucket_offset_sec']['max'] is not None]
        complete = sum(1 for r in group if r['complete'])
        venues[venue] = {
            'races': len(group),
            'complete': complete,
            'complete_rate': complete / len(group) if group else 0.0,
            'horses_4': mean(r['n_horses_with_4_buckets'] for r in group),
            'odds_rate': mean(r['odds_nonnull_rate'] for r in group),
            'available_rate': mean(r['available_at_complete_rate'] for r in group),
            'offset_avg_sec': mean(v_offs) if v_offs else None,
            'offset_max_sec': max(v_max) if v_max else None,
        }

    return {
        'days': days,
        'start': start.isoformat(),
        'races': tracked,
        'complete': sum(1 for r in races if r['complete']),
        'bucket_missing': bucket_missing,
        'chronic': chronic,
        'offset_avg_sec': mean(offset_avgs) if offset_avgs else None,
        'offset_max_sec': max(offset_maxes) if offset_maxes else None,
        'offset_nonzero_races': sum(1 for r in races
                                    if (r['bucket_offset_sec']['max'] or 0) > 0),
        'venues': venues,
    }


def render_weekly_markdown(weekly, progress, generated):
    lines = [
        f'# 賽前賠率快照週報（截至 {generated}，視窗 {weekly["start"]} → {generated}）',
        '',
        f'- 總進度：**{progress["complete_pre_race_races"]}/{progress["target"]}**'
        f'（累計已追蹤 {progress["total_races"]} 場）',
        f'- 視窗內賽事：{weekly["races"]} 場，完整 {weekly["complete"]} 場',
        '- 完整定義不變：四 bucket 齊＋odds > 1＋available_at 可解析；partial 不當完整。',
        '',
        '## 缺 bucket 頻率（視窗內）',
        '',
        '| bucket | 缺場數 | 缺場率 | 長期缺（≥80%） |',
        '|---|---|---|---|',
    ]
    for b in O.BUCKETS:
        n = weekly['bucket_missing'][b]
        rate = (n / weekly['races']) if weekly['races'] else 0.0
        flag = '是' if b in weekly['chronic'] else '否'
        lines.append(f'| {b} | {n} | {rate * 100:.0f}% | {flag} |')
    lines += [
        '',
        '## 場地差異（視窗內）',
        '',
        '| venue | 賽事 | 完整 | 完整率 | 平均四 bucket 齊馬數 | 賠率有效率 | available_at 完整率 | 偏移(秒, 平均/最大) |',
        '|---|---|---|---|---|---|---|---|',
    ]
    for venue, v in weekly['venues'].items():
        off = ('n/a' if v['offset_avg_sec'] is None
               else f"{v['offset_avg_sec']:.0f}/{v['offset_max_sec']:.0f}")
        lines.append(
            f"| {venue} | {v['races']} | {v['complete']} | {v['complete_rate'] * 100:.0f}% "
            f"| {v['horses_4']:.1f} | {_pct(v['odds_rate'])} | {_pct(v['available_rate'])} | {off} |")
    off_avg = ('n/a' if weekly['offset_avg_sec'] is None
               else f"{weekly['offset_avg_sec']:.0f}")
    off_max = ('n/a' if weekly['offset_max_sec'] is None
               else f"{weekly['offset_max_sec']:.0f}")
    lines += [
        '',
        '## bucket_offset_sec 檢查',
        '',
        f'- 平均偏移：{off_avg} 秒；最大偏移：{off_max} 秒；'
        f'有非零偏移賽事：{weekly["offset_nonzero_races"]}/{weekly["races"]}。',
        '- bucket 本身由抓取時間距離開跑分鐘數決定，因此非零偏移主要出現在 open '
        '早於 180 分鐘的抓取；若長期非零，先檢查 tick 時鐘而非放寬定義。',
        '',
        '## 建議（自動規則，唔會自動改任何東西）',
        '',
    ]
    if weekly['chronic']:
        for b in weekly['chronic']:
            lines.append(
                f'- **長期缺 {b}**（{weekly["bucket_missing"][b]}/{weekly["races"]} 場）：'
                '請二選一——(a) 放寬 bucket 定義（必須在 FLAGS.md 記錄並保留對照）'
                '或 (b) 修 scraper。partial 一律唔當完整，亦唔計入 50 場門檻。')
    else:
        lines.append('- 視窗內無長期缺 bucket；維持現行定義。')
    lines += [
        '',
        '本報表唯讀；SP 不會被寫入為 pre-race 快照。',
        '',
    ]
    return '\n'.join(lines)


def load_report_inputs(supabase):
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
    return report, progress, store


def _persist_summary(supabase, report_id, payload):
    now = datetime.now(HKT)
    try:
        retry_supabase(lambda: supabase.table('pipeline_status').upsert({
            'id': report_id,
            'last_run': now.isoformat(),
            'status_json': {**payload, 'updated_at': now.isoformat()},
        }, on_conflict='id').execute())
    except Exception as e:
        print(f'[SnapshotReport] WARN summary not persisted: {e}')


def _write(path, markdown):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(markdown)


def generate_report(supabase=None, date=None, out=None):
    """Build the daily report, write the markdown, persist a compact summary."""
    supabase = supabase or get_supabase()
    generated = date or datetime.now(HKT).strftime('%Y-%m-%d')
    report, progress, store = load_report_inputs(supabase)
    markdown = render_markdown(report, progress, store, generated)
    out = out or os.path.join(
        ROOT, 'reports', f'odds_snapshot_completeness_{generated}.md')
    _write(out, markdown)
    _persist_summary(supabase, REPORT_ID, {
        'date': generated,
        'path': os.path.relpath(out, ROOT),
        'store': store,
        'races': len(report['races']),
        'complete': progress['complete_pre_race_races'],
        'target': progress['target'],
        'partial': progress['partial_races'],
        'missing_reason_counts': progress['missing_reason_counts'],
        'fallback_json_bytes': progress.get('fallback_json_bytes'),
    })
    return out, report, progress


def generate_weekly(supabase=None, days=7, date=None, out=None):
    supabase = supabase or get_supabase()
    generated = date or datetime.now(HKT).strftime('%Y-%m-%d')
    report, progress, store = load_report_inputs(supabase)
    weekly = build_weekly(report, days=days)
    markdown = render_weekly_markdown(weekly, progress, generated)
    out = out or os.path.join(
        ROOT, 'reports', f'odds_snapshot_weekly_{generated}.md')
    _write(out, markdown)
    _persist_summary(supabase, WEEKLY_ID, {
        'date': generated,
        'path': os.path.relpath(out, ROOT),
        'days': weekly['days'],
        'start': weekly['start'],
        'races': weekly['races'],
        'complete': weekly['complete'],
        'bucket_missing': weekly['bucket_missing'],
        'chronic': weekly['chronic'],
        'store': store,
    })
    return out, report, weekly


def main():
    parser = argparse.ArgumentParser(description='Pre-race odds snapshot completeness report')
    parser.add_argument('--date', default=datetime.now(HKT).strftime('%Y-%m-%d'))
    parser.add_argument('--out', default=None)
    parser.add_argument('--weekly', action='store_true',
                        help='Weekly aggregate instead of the daily table')
    parser.add_argument('--days', type=int, default=7, help='Weekly window in days')
    args = parser.parse_args()

    if args.weekly:
        out, _, weekly = generate_weekly(days=args.days, date=args.date, out=args.out)
        print(f"[SnapshotReport] weekly {weekly['races']} races, "
              f"complete {weekly['complete']}, chronic missing {weekly['chronic']} -> {out}")
    else:
        out, report, progress = generate_report(date=args.date, out=args.out)
        print(f"[SnapshotReport] {len(report['races'])} races, "
              f"complete {progress['complete_pre_race_races']}/{progress['target']} -> {out}")


if __name__ == '__main__':
    main()