#!/usr/bin/env python3
"""Fill missing/invalid going and track_course from HKJC results pages.

Reads the DB first, only fetches races that actually lack a value, and never
overwrites an existing valid value that disagrees (it reports a mismatch
instead). Uses httpx, not Playwright: the results page is server-rendered and
carries `場地狀況 : ...` plus `賽道 : ...` per race.
"""
import argparse
import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase
from track_meta import extract_track_meta, normalize_going, normalize_track_course

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_ID = 'track_meta_backfill'
MEETING_RE = re.compile(r'賽事日期:\s*(\d{2})/(\d{2})/(\d{4})')


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


def needs_fill(race):
    stored_going = race.get('going')
    stored_course = race.get('track_course')
    going_missing = not stored_going or normalize_going(stored_going) != stored_going
    course_missing = not stored_course or normalize_track_course(stored_course) != stored_course
    return going_missing or course_missing


def page_text(html):
    text = re.sub(r'<script[\s\S]*?</script>', ' ', html)
    text = re.sub(r'<style[\s\S]*?</style>', ' ', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    return re.sub(r'\s+', ' ', text)


def fetch_meta(client, race):
    date_slash = str(race['race_date']).replace('-', '/')
    url = (f"https://racing.hkjc.com/zh-hk/local/information/localresults"
           f"?racedate={date_slash}&Racecourse={race['venue']}&RaceNo={race['race_no']}")
    resp = client.get(url)
    if resp.status_code != 200:
        return None, f'HTTP {resp.status_code}'
    text = page_text(resp.text)
    match = MEETING_RE.search(text)
    if not match:
        return None, 'no meeting date'
    day, month, year = match.groups()
    if f'{year}-{month}-{day}' != str(race['race_date'])[:10]:
        return None, f'date mismatch {year}-{month}-{day}'
    if not re.search(rf'第\s*{int(race["race_no"])}\s*場\s*\(\d+\)', text):
        if '取消' in text:
            return None, 'race cancelled'
        return None, f'race {race["race_no"]} not on page'
    return extract_track_meta(text), None


def backfill(supabase=None, dry_run=False, limit=0, delay=0.5):
    supabase = supabase or get_supabase()
    today = datetime.now(HKT).strftime('%Y-%m-%d')
    races = _paginate(supabase, 'races',
                      'race_id,race_date,venue,race_no,going,track_course,is_finished',
                      'race_id')
    todo = [r for r in races
            if str(r.get('race_date') or '')[:10] <= today and needs_fill(r)]
    todo.sort(key=lambda r: (str(r.get('race_date')), r.get('race_id')))
    if limit:
        todo = todo[:limit]

    print(f"[TrackMeta] {len(races)} races, {len(todo)} need going/track_course"
          f"{' (dry-run)' if dry_run else ''}")
    summary = {'races': len(races), 'needed': len(todo), 'fetched': 0,
               'updated_going': 0, 'updated_track_course': 0,
               'mismatch': 0, 'missed': 0, 'errors': 0, 'misses': []}

    with httpx.Client(timeout=25, follow_redirects=True,
                      headers={'User-Agent': 'Mozilla/5.0'}) as client:
        for i, race in enumerate(todo, 1):
            try:
                meta, reason = fetch_meta(client, race)
            except Exception as e:
                summary['errors'] += 1
                reason = f'{type(e).__name__}: {e}'
                meta = None
            if not meta:
                summary['missed'] += 1
                if len(summary['misses']) < 20:
                    summary['misses'].append(f"{race['race_id']}: {reason}")
                print(f"  [{i}/{len(todo)}] {race['race_id']} MISS {reason}")
                time.sleep(delay)
                continue
            summary['fetched'] += 1

            patch = {}
            fetched_going = meta.get('going')
            fetched_course = meta.get('track_course')
            stored_going = race.get('going')
            stored_course = race.get('track_course')

            if fetched_going:
                if normalize_going(stored_going) == stored_going and stored_going:
                    if stored_going != fetched_going:
                        summary['mismatch'] += 1
                        if len(summary['misses']) < 20:
                            summary['misses'].append(
                                f"{race['race_id']}: going {stored_going} vs {fetched_going}")
                else:
                    patch['going'] = fetched_going
            if fetched_course:
                if stored_course and stored_course == normalize_track_course(stored_course):
                    if stored_course != fetched_course:
                        summary['mismatch'] += 1
                else:
                    patch['track_course'] = fetched_course

            if patch:
                if not dry_run:
                    retry_supabase(lambda rid=race['race_id'], p=patch: supabase.table('races')
                                   .update(p).eq('race_id', rid).execute())
                if 'going' in patch:
                    summary['updated_going'] += 1
                if 'track_course' in patch:
                    summary['updated_track_course'] += 1
            if i % 50 == 0 or i == len(todo):
                print(f"  [{i}/{len(todo)}] updated going={summary['updated_going']} "
                      f"track={summary['updated_track_course']} miss={summary['missed']} "
                      f"mismatch={summary['mismatch']}")
            time.sleep(delay)

    if not dry_run:
        try:
            retry_supabase(lambda: supabase.table('pipeline_status').upsert({
                'id': STATUS_ID,
                'last_run': datetime.now(HKT).isoformat(),
                'status_json': {**summary, 'updated_at': datetime.now(HKT).isoformat()},
            }, on_conflict='id').execute())
        except Exception as e:
            print(f"[TrackMeta] WARN status not persisted: {e}")
    print(f"[TrackMeta] fetched={summary['fetched']} updated going={summary['updated_going']} "
          f"track={summary['updated_track_course']} mismatch={summary['mismatch']} "
          f"missed={summary['missed']} errors={summary['errors']}")
    return summary


def main():
    parser = argparse.ArgumentParser(description='Backfill going/track_course from HKJC')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--delay', type=float, default=0.5)
    args = parser.parse_args()
    backfill(dry_run=args.dry_run, limit=args.limit, delay=args.delay)


if __name__ == '__main__':
    main()