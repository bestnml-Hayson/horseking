#!/usr/bin/env python3
"""
Backfill 沿途走位 (in-running positions) for finished races that have none.

Stores the results-page sequence in race_runners.sectional_times as
"場頭數|4 4 4 1"; lib/race-utils.ts and scripts/run_style.py derive the
領放/跟前/後上 style from it.

Usage:
  python scripts/backfill_run_styles.py --days 45
  python scripts/backfill_run_styles.py --days 45 --limit 40 --dry-run
"""
import argparse
import os
import random
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'buffer'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))

from common import get_supabase, retry_supabase
from run_style import encode_running_positions

HKT = ZoneInfo('Asia/Hong_Kong')
BATCH_RACES = 60
MIN_RUNNERS = 4


def races_needing_styles(supabase, since: str) -> List[Dict]:
    resp = retry_supabase(
        lambda: supabase.table('races')
        .select('race_id,race_date,venue,race_no')
        .gte('race_date', since)
        .eq('is_finished', True)
        .order('race_date', desc=True)
        .limit(400)
        .execute()
    )
    races = resp.data or []
    if not races:
        return []

    by_id = {r['race_id']: r for r in races}
    ids = list(by_id)
    runners: Dict[str, List[Dict]] = {}
    for i in range(0, len(ids), BATCH_RACES):
        chunk_ids = ids[i:i + BATCH_RACES]
        offset = 0
        while True:
            got = retry_supabase(
                lambda c=chunk_ids, o=offset: supabase.table('race_runners')
                .select('race_id,horse_no,finish_position,sectional_times')
                .in_('race_id', c).order('runner_id').range(o, o + 999).execute()
            ).data or []
            for g in got:
                runners.setdefault(g['race_id'], []).append(g)
            if len(got) < 1000:
                break
            offset += 1000

    need = []
    for rid, rows in runners.items():
        finished = [r for r in rows if r.get('finish_position')]
        if len(finished) < MIN_RUNNERS:
            continue
        missing = sum(1 for r in finished if not r.get('sectional_times'))
        if missing:
            race = dict(by_id[rid])
            race['missing'] = missing
            race['total'] = len(finished)
            need.append(race)
    need.sort(key=lambda r: (str(r['race_date']), r['race_no']), reverse=True)
    return need


def scrape_positions(page, date_str: str, venue: str, race_no: int):
    date_slash = date_str.replace('/', '-')
    url = (f"https://racing.hkjc.com/zh-hk/local/information/localresults"
           f"?racedate={date_slash}&Racecourse={venue}&RaceNo={race_no}")
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(random.randint(3000, 4500))
        date_path = date_slash.replace('-', '')
        if date_path not in page.url and date_slash not in page.url:
            print(f"    [SKIP] R{race_no}: HKJC redirected (date mismatch)")
            return {}

        entries = page.evaluate(r'''() => {
            const out = [];
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const rows = table.querySelectorAll('tr');
                if (rows.length < 4) continue;
                const headers = Array.from(rows[0].querySelectorAll('td, th')).map(c => c.textContent.trim());
                const posIdx = headers.indexOf('名次');
                const noIdx = headers.indexOf('馬號');
                const runIdx = headers.indexOf('沿途走位');
                if (posIdx < 0 || noIdx < 0 || runIdx < 0) continue;
                for (let i = 1; i < rows.length; i++) {
                    const cells = rows[i].querySelectorAll('td');
                    if (cells.length <= Math.max(posIdx, noIdx, runIdx)) continue;
                    const pos = parseInt(cells[posIdx].textContent.trim());
                    const horseNo = parseInt(cells[noIdx].textContent.trim());
                    if (isNaN(pos) || pos <= 0 || isNaN(horseNo)) continue;
                    const running = cells[runIdx].textContent.replace(/\s+/g, ' ').trim();
                    if (running) out.push({ no: horseNo, run: running });
                }
                break;
            }
            return out;
        }''')
        return {e['no']: e['run'] for e in entries or []}
    except Exception as e:
        print(f"    [FAIL] R{race_no}: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=45)
    parser.add_argument('--limit', type=int, default=120, help='max races to scrape')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    supabase = get_supabase()
    since = (datetime.now(HKT) - timedelta(days=args.days)).strftime('%Y-%m-%d')
    races = races_needing_styles(supabase, since)
    if not races:
        print(f'[OK] every finished race since {since} already has running positions')
        return 0

    print(f'[Plan] {len(races)} races missing running positions since {since}')
    print(f'       scraping at most {args.limit} (oldest first is skipped; newest first)')
    targets = races[:args.limit]
    if args.dry_run:
        for r in targets:
            print(f"  {r['race_date']} {r['venue']} R{r['race_no']}: {r['missing']}/{r['total']} runners missing")
        return 0

    from playwright.sync_api import sync_playwright

    updated_races = 0
    updated_runners = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()
        for race in targets:
            date_str = str(race['race_date'])[:10]
            venue, race_no = race['venue'], race['race_no']
            print(f"  {date_str} {venue} R{race_no}: ", end='', flush=True)
            positions = scrape_positions(page, date_str, venue, race_no)
            if not positions:
                print('no running positions')
                continue
            field_size = len(positions)
            resp = retry_supabase(
                lambda rid=race['race_id']: supabase.table('race_runners')
                .select('runner_id,horse_no,sectional_times').eq('race_id', rid).execute()
            )
            updated = 0
            for runner in resp.data or []:
                raw = positions.get(runner['horse_no'])
                encoded = encode_running_positions(field_size, raw)
                if not encoded or encoded == runner.get('sectional_times'):
                    continue
                retry_supabase(
                    lambda r=runner['runner_id'], s=encoded: supabase.table('race_runners')
                    .update({'sectional_times': s}).eq('runner_id', r).execute()
                )
                updated += 1
            if updated:
                updated_races += 1
                updated_runners += updated
            print(f'{updated} runners')
            time.sleep(random.uniform(1.0, 2.0))
        browser.close()

    print(f'\n[OK] {updated_runners} runners across {updated_races} races now carry running positions')
    return 0


if __name__ == '__main__':
    sys.exit(main())