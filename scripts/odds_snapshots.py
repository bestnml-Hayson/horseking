#!/usr/bin/env python3
"""Forward pre-race odds snapshots (P2).

Every tick writes the freshly scraped price into odds_snapshots with the exact
capture time as available_at. When the table is not reachable (this instance has
no DDL path), the same rows go to pipeline_status.odds_snapshots instead; shape
and semantics are identical, so a later migration can copy them across.

Bucket edges, measured to post time:
  > 60m -> open, 16-60m -> 60m, 6-15m -> 15m, <= 5m -> close
The unique (race_id, horse_id, snapshot_type) key keeps the first price per
bucket, so 'open' is the earliest morning price and 'close' the last one inside
five minutes. Historical SP rows are never written as pre-race.
"""
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import retry_supabase

TABLE = 'odds_snapshots'
STATE_ID = 'odds_snapshots'
KEEP_DAYS = 7
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
    added = 0
    for row in rows:
        key = f"{row['horse_id']}|{row['snapshot_type']}"
        if key in bucket_rows:
            continue
        bucket_rows[key] = row
        added += 1
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
                rows, on_conflict='race_id,horse_id,snapshot_type',
                ignore_duplicates=True).execute())
            _table_available = True
            return len(rows), 'table'
        except Exception as e:
            _table_available = False
            print(f"    [WARN] odds_snapshots unavailable ({str(e)[:80]}); "
                  'falling back to pipeline_status')

    added = _write_fallback(supabase, race_id, str(race.get('race_date') or now.date()), rows, now)
    return added, 'pipeline_status'


def reset_table_cache():
    """Tests: force the next call to probe the table again."""
    global _table_available
    _table_available = None