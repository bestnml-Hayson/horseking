# -*- coding: utf-8 -*-
"""Update win_odds for 10/7 HV races from HKJC betting page scrape."""
import os, sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env.local'))

ODDS_DATA = {
    "HV-20261007-01": [
        (1, 14), (2, 21), (3, 6.4), (4, 11), (5, 7.6), (6, 12),
        (7, 4.6), (8, 16), (9, 15), (10, 26), (11, 9.8), (12, 24),
    ],
    "HV-20261007-02": [
        (1, 5.5), (2, 8.8), (3, 6.5), (4, 13), (5, 11), (6, 14),
        (7, 5.4), (8, 23), (9, 21), (10, 31), (11, 12), (12, 10),
    ],
    "HV-20261007-03": [
        (1, 5.9), (2, 6.8), (3, 5.9), (4, 16), (5, 13), (6, 9.1),
        (7, 6.5), (8, 7.9), (9, 21), (10, 14), (11, 11), (12, 10),
    ],
    "HV-20261007-04": [
        (1, 13), (2, 4.4), (3, 11), (4, 6.8), (5, 11), (6, 8.1),
        (7, 13), (8, 18), (9, 21), (10, 10), (11, 16), (12, 10),
    ],
    "HV-20261007-05": [
        (1, 6.5), (2, 12), (3, 11), (4, 5.8), (5, 7.1), (6, 17),
        (7, 13), (8, 16), (9, 9.7), (10, 11), (11, 13), (12, 7.1),
    ],
    "HV-20261007-06": [
        (1, 13), (2, 11), (3, 5.5), (4, 11), (5, 9.2), (6, 10),
        (7, 9.2), (8, 15), (9, 13), (10, 4.2), (11, 11), (12, 13),
    ],
    "HV-20261007-07": [
        (1, 10), (2, 8.4), (3, 10), (4, 7.2), (5, 11), (6, 13),
        (7, 11), (8, 4.2), (9, 21), (10, 11), (11, 14), (12, 7.6),
    ],
    "HV-20261007-08": [
        (1, 16), (2, 12), (3, 5.5), (4, 13), (5, 10), (6, 6.1),
        (7, 11), (8, 11), (9, 5.7), (10, 16), (11, 16), (12, 10),
    ],
    "HV-20261007-09": [
        (1, 4.4), (2, 8.9), (3, 11), (4, 20), (5, 11), (6, 7.3),
        (7, 5.6), (8, 17), (9, 12), (10, 17), (11, 11), (12, 19),
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
