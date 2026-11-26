#!/usr/bin/env python3
"""
scripts/backfill_sp_ledger.py

One-time repair for the odds-semantics change: `race_runners.win_odds` is now the
pre-race price and the official 獨贏賠率 (SP) belongs in `race_results`. Races
archived before that change had their pre-race price overwritten by the SP, so
their `race_runners.win_odds` IS the dividend — copy it into the ledger before
anything else touches it.

Nothing here can recover the lost pre-race prices; those races stay unusable for
honest EV/ROI measurement and are excluded by date in the audit scripts.

CLI:
  python scripts/backfill_sp_ledger.py --dry-run
  python scripts/backfill_sp_ledger.py --from 2026-08-22 --to 2026-11-25
"""
import os
import sys
import argparse
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase


def fetch_all(table, select, filters, order='runner_id'):
    """Page by offset: max-rows=1000 clamps limit= on this server."""
    rows, frm = [], 0
    while True:
        q = table.select(select)
        for kind, args in filters:
            q = getattr(q, kind)(*args)
        resp = q.order(order).range(frm, frm + 999).execute()
        page = resp.data or []
        rows += page
        if len(page) < 1000:
            return rows
        frm += 1000


def main():
    parser = argparse.ArgumentParser(description='Copy pre-change SP into the race_results ledger')
    parser.add_argument('--from', dest='date_from', default='2026-08-22')
    parser.add_argument('--to', dest='date_to',
                        default=datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    supabase = get_supabase()
    if not supabase:
        return 1

    races = fetch_all(
        supabase.table('races'), 'race_id,race_date,venue,race_no',
        [('gte', ('race_date', args.date_from)), ('lte', ('race_date', args.date_to)),
         ('eq', ('is_finished', True))], order='race_id')
    print(f'已完成場次 {len(races)}（{args.date_from} → {args.date_to}）')

    # A race is covered only if the ledger holds per-runner dividends. The old
    # per-race summary rows (horse_no null) don't count.
    ledger_rows = fetch_all(
        supabase.table('race_results'), 'race_id,horse_no,win_odds',
        [('lte', ('race_date', args.date_to))], order='id')
    have = {r['race_id'] for r in ledger_rows
            if r.get('horse_no') is not None and (r.get('win_odds') or 0) > 1.0}
    todo = [r for r in races if r['race_id'] not in have]
    print(f'已有派帳記錄 {len(races) - len(todo)} 場，需補 {len(todo)} 場')
    if not todo:
        return 0

    meta = {r['race_id']: r for r in todo}
    total_rows = 0
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        runners = fetch_all(
            supabase.table('race_runners'),
            'runner_id,race_id,horse_id,horse_no,jockey,trainer,win_odds,finish_position',
            [('in_', ('race_id', [b['race_id'] for b in batch]))], order='runner_id')

        ledger = [
            {
                'race_id': r['race_id'],
                'race_date': meta[r['race_id']]['race_date'],
                'venue': meta[r['race_id']]['venue'],
                'race_no': meta[r['race_id']]['race_no'],
                'finish_position': r.get('finish_position'),
                'horse_no': r['horse_no'],
                'horse_name': r.get('horse_id'),
                'jockey': r.get('jockey'),
                'trainer': r.get('trainer'),
                'win_odds': r.get('win_odds'),
            }
            for r in runners
            if r.get('win_odds') and r['win_odds'] > 1.0 and r.get('finish_position')
        ]
        if not ledger:
            continue
        total_rows += len(ledger)
        if args.dry_run:
            print(f'  [DRY-RUN] {len(ledger)} 注派帳，例：{ledger[0]["race_id"]} H{ledger[0]["horse_no"]} @{ledger[0]["win_odds"]}')
            continue
        retry_supabase(lambda l=ledger: supabase.table('race_results').upsert(
            l, on_conflict='race_id,horse_no').execute())

    print(f'{"[DRY-RUN] 將寫入" if args.dry_run else "[OK] 已寫入"} race_results {total_rows} 注')
    return 0


if __name__ == '__main__':
    sys.exit(main())
