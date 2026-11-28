#!/usr/bin/env python3
"""Forward pre-race odds snapshots (P2).

Every tick writes the freshly scraped price into odds_snapshots with the exact
capture time as available_at. When the table is not reachable (this instance has
no DDL path), the same rows go to pipeline_status.odds_snapshots instead; shape
and semantics are identical, so a later migration can copy them across.

Bucket edges, measured to post time:
  > 60m -> open, 16-60m -> 60m, 6-15m -> 15m, <= 5m -> close
The unique (race_id, horse_id, snapshot_type, available_at) key keeps every
distinct capture and drops only exact repeats, so a race is "complete" once all
four buckets carry at least one price. Historical SP rows are never written as
pre-race. The fallback store keeps 120 days so the 50-race gate can actually be
reached before the migration lands.
"""
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import retry_supabase

TABLE = 'odds_snapshots'
STATE_ID = 'odds_snapshots'
PROGRESS_ID = 'odds_snapshot_progress'
KEEP_DAYS = 120
TARGET_COMPLETE_RACES = 50
BUCKETS = ('open', '60m', '15m', 'close')
_table_available = None


def snapshot_bucket(minutes_to_post):
    """open / 60m / 15m / close from minutes remaining to the start."""
    if minutes_to_post is None or minutes_to_post > 60:
        return 'open'
    if minutes_to_post > 15:
        return '60m'
    if minutes_to_post > 5:
        return '15m'
    return 'close'


def minutes_to_post(race, now):
    date_str = race.get('race_date')
    race_time = race.get('race_time')
    if not date_str or not race_time:
        return None
    try:
        hour, minute = (int(x) for x in str(race_time).split(':')[:2])
        day = datetime.strptime(str(date_str)[:10], '%Y-%m-%d')
    except (TypeError, ValueError):
        return None
    start = day.replace(hour=hour, minute=minute, tzinfo=HKT)
    return (start - now).total_seconds() / 60


def build_snapshot_rows(race_id, horse_ids_by_no, odds_by_no, bucket, now):
    """Rows for priced horses with a known horse_id (SP never passes through here)."""
    rows = []
    for horse_no, price in (odds_by_no or {}).items():
        try:
            horse_no = int(horse_no)
        except (TypeError, ValueError):
            continue
        horse_id = (horse_ids_by_no or {}).get(horse_no)
        if not horse_id or price is None or float(price) <= 1.0:
            continue
        rows.append({
            'race_id': race_id,
            'horse_id': horse_id,
            'odds': round(float(price), 2),
            'available_at': now.isoformat(),
            'source': 'pre-race',
            'snapshot_type': bucket,
        })
    return rows


def _load_state(supabase):
    try:
        resp = retry_supabase(
            lambda: supabase.table('pipeline_status').select('status_json')
            .eq('id', STATE_ID).execute()
        )
        rows = resp.data or []
        return (rows[0].get('status_json') or {}) if rows else {}
    except Exception as e:
        print(f"    [WARN] odds snapshot state unreadable: {e}")
        return {}


def _write_fallback(supabase, race_id, race_date, rows, now):
    state = _load_state(supabase)
    races = state.get('races') or {}
    entry = races.get(race_id) or {'race_date': race_date, 'rows': {}}
    entry['race_date'] = race_date
    bucket_rows = entry.setdefault('rows', {})
    seen = set(entry.get('buckets') or [])
    added = 0
    for row in rows:
        key = f"{row['horse_id']}|{row['snapshot_type']}|{row['available_at']}"
        if key in bucket_rows:
            continue
        bucket_rows[key] = row
        seen.add(row['snapshot_type'])
        added += 1
    entry['buckets'] = [b for b in BUCKETS if b in seen]
    races[race_id] = entry
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime('%Y-%m-%d')
    races = {rid: v for rid, v in races.items()
             if str(v.get('race_date', ''))[:10] >= cutoff}
    retry_supabase(lambda: supabase.table('pipeline_status').upsert({
        'id': STATE_ID,
        'last_run': now.isoformat(),
        'status_json': {'races': races, 'updated_at': now.isoformat()},
    }, on_conflict='id').execute())
    return added


def record_pre_race_snapshots(supabase, race, odds_by_no, runner_horse_ids=None, now=None):
    """Store this tick's prices; returns (rows written, store used)."""
    global _table_available
    now = now or datetime.now(HKT)
    race_id = race['race_id']
    if runner_horse_ids is None:
        try:
            resp = retry_supabase(
                lambda: supabase.table('race_runners').select('horse_no,horse_id')
                .eq('race_id', race_id).execute())
            runner_horse_ids = {r['horse_no']: r.get('horse_id') for r in (resp.data or [])}
        except Exception as e:
            print(f"    [WARN] odds snapshot runners unreadable: {e}")
            return 0, 'none'

    bucket = snapshot_bucket(minutes_to_post(race, now))
    rows = build_snapshot_rows(race_id, runner_horse_ids, odds_by_no, bucket, now)
    if not rows:
        return 0, 'none'

    if _table_available is not False:
        try:
            retry_supabase(lambda: supabase.table(TABLE).upsert(
                rows, on_conflict='race_id,horse_id,snapshot_type,available_at',
                ignore_duplicates=True).execute())
            _table_available = True
            return len(rows), 'table'
        except Exception as e:
            _table_available = False
            print(f"    [WARN] odds_snapshots unavailable ({str(e)[:80]}); "
                  'falling back to pipeline_status')

    added = _write_fallback(supabase, race_id, str(race.get('race_date') or now.date()), rows, now)
    return added, 'pipeline_status'


def _table_ready(supabase):
    global _table_available
    if _table_available is None:
        try:
            retry_supabase(lambda: supabase.table(TABLE).select('race_id').limit(1).execute())
            _table_available = True
        except Exception:
            _table_available = False
    return bool(_table_available)


def fetch_snapshot_rows(supabase):
    """Every captured row plus the store it came from."""
    if _table_ready(supabase):
        rows, start = [], 0
        while True:
            resp = retry_supabase(lambda: supabase.table(TABLE).select(
                'race_id,horse_id,odds,available_at,source,snapshot_type'
            ).range(start, start + 999).execute())
            batch = resp.data or []
            rows.extend(batch)
            if len(batch) < 1000:
                break
            start += 1000
        return rows, 'table'

    state = _load_state(supabase)
    rows = []
    for race_id, entry in (state.get('races') or {}).items():
        for row in (entry.get('rows') or {}).values():
            if isinstance(row, dict):
                rows.append(dict(row, race_id=row.get('race_id') or race_id))
    return rows, 'pipeline_status'


def _valid_row(row):
    """A price counts only when odds > 1 and the capture time is recorded."""
    try:
        odds = float(row.get('odds') or 0)
    except (TypeError, ValueError):
        return False
    return odds > 1.0 and bool(row.get('available_at'))


def snapshot_progress(supabase):
    """Count races with all four buckets of valid prices (the 50-race gate)."""
    rows, store = fetch_snapshot_rows(supabase)
    by_race = {}
    for row in rows:
        entry = by_race.setdefault(row.get('race_id'), {'valid': set()})
        bucket = row.get('snapshot_type')
        if bucket in BUCKETS and _valid_row(row):
            entry['valid'].add(bucket)

    complete = 0
    missing_counts = Counter()
    for entry in by_race.values():
        missing = [b for b in BUCKETS if b not in entry['valid']]
        if missing:
            missing_counts['缺 ' + '/'.join(missing)] += 1
        else:
            complete += 1

    progress = {
        'complete_pre_race_races': complete,
        'partial_races': len(by_race) - complete,
        'total_races': len(by_race),
        'missing_reason_counts': dict(missing_counts),
        'target': TARGET_COMPLETE_RACES,
        'store': store,
    }
    if store == 'pipeline_status':
        try:
            progress['fallback_json_bytes'] = len(
                json.dumps(_load_state(supabase)).encode('utf-8'))
        except Exception:
            progress['fallback_json_bytes'] = None
    return progress


def log_progress(supabase, out=print):
    """Print and persist the daily X/50 progress line."""
    progress = snapshot_progress(supabase)
    missing = ', '.join(f"{k}: {v}"
                        for k, v in sorted(progress['missing_reason_counts'].items()))
    size = progress.get('fallback_json_bytes')
    size_txt = 'n/a' if size is None else f'{size / 1024:.1f} KB'
    out(f"[Snapshot] complete_pre_race_races = "
        f"{progress['complete_pre_race_races']}/{TARGET_COMPLETE_RACES} "
        f"| partial={progress['partial_races']} "
        f"| missing={{{missing or 'none'}}} "
        f"| store={progress['store']} | fallback={size_txt}")
    now = datetime.now(HKT)
    try:
        retry_supabase(lambda: supabase.table('pipeline_status').upsert({
            'id': PROGRESS_ID,
            'last_run': now.isoformat(),
            'status_json': {**progress, 'updated_at': now.isoformat()},
        }, on_conflict='id').execute())
    except Exception as e:
        out(f"    [WARN] snapshot progress not persisted: {e}")
    return progress


def reset_table_cache():
    """Tests: force the next call to probe the table again."""
    global _table_available
    _table_available = None


def main():
    from common import get_supabase
    log_progress(get_supabase())
    print(json.dumps(snapshot_progress(get_supabase()), ensure_ascii=False))


if __name__ == '__main__':
    main()