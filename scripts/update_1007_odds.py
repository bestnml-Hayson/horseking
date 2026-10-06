# -*- coding: utf-8 -*-
"""Update win_odds for 10/7 HV races - LIVE odds from HKJC (07/10 01:35)."""
import os, sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env.local'))

ODDS_DATA = {
    "HV-20261007-01": [
        (1, 4.1), (2, 15), (3, 9.5), (4, 4.8), (5, 9.2), (6, 13),
        (7, 41), (8, 12), (9, 7.2), (10, 15), (11, 14), (12, 24),
    ],
    "HV-20261007-02": [
        (1, 13), (2, 7.9), (3, 24), (4, 10), (5, 8.4), (6, 6.4),
        (7, 13), (8, 24), (9, 18), (10, 2.7), (11, 36), (12, 23),
    ],
    "HV-20261007-03": [
        (1, 14), (2, 26), (3, 9.6), (4, 5.6), (5, 6.6), (6, 6.7),
        (7, 31), (8, 11), (9, 42), (10, 2.9), (11, 59), (12, 48),
    ],
    "HV-20261007-04": [
        (1, 5.9), (2, 4.6), (3, 13), (4, 11), (5, 14), (6, 17),
        (7, 44), (8, 9.9), (9, 22), (10, 4.9), (11, 21), (12, 7.8),
    ],
    "HV-20261007-05": [
        (1, 10), (2, 29), (3, 27), (4, 3.2), (5, 16), (6, 11),
        (7, 17), (8, 4), (9, 6.9), (10, 23), (11, 22), (12, 24),
    ],
    "HV-20261007-06": [
        (1, 20), (2, 11), (3, 18), (4, 8.6), (5, 7.3), (6, 14),
        (7, 12), (8, 20), (9, 3.2), (10, 5), (11, 37), (12, 33),
    ],
    "HV-20261007-07": [
        (1, 17), (2, 6), (3, 17), (4, 20), (5, 4.3), (6, 15),
        (7, 19), (8, 17), (9, 11), (10, 11), (11, 4.2), (12, 16),
    ],
    "HV-20261007-08": [
        (1, 4.8), (2, 7.6), (3, 10), (4, 5.7), (5, 17), (6, 27),
        (7, 27), (8, 19), (9, 19), (10, 11), (11, 8.6), (12, 6.1),
    ],
    "HV-20261007-09": [
        (1, 5.5), (2, 8.7), (3, 14), (4, 18), (5, 12), (6, 6.9),
        (7, 4.5), (8, 19), (9, 12), (10, 20), (11, 12), (12, 12),
    ],
}

def main():
    url = os.environ['NEXT_PUBLIC_SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    sb = create_client(url, key)

    updated = 0
    for race_id, entries in ODDS_DATA.items():
        for horse_no, win_odds in entries:
            resp = sb.table('race_runners').update({'win_odds': win_odds}) \
                .eq('race_id', race_id).eq('horse_no', horse_no).execute()
            n = len(resp.data) if resp.data else 0
            if n == 0:
                print(f"  WARNING: no match for {race_id} No.{horse_no}")
            updated += n
        print(f"  {race_id}: {len(entries)} odds updated")

    print(f"\nTotal rows updated: {updated}")

if __name__ == '__main__':
    main()
