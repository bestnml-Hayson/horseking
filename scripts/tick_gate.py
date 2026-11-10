"""
Race-day tick gate — decides whether the Auto-Pilot tick has anything to do.

Runs on the bare GitHub runner (stdlib only, no pip install) so an idle
half-hour costs seconds instead of a Playwright bootstrap. Writes four
outputs for the following steps: need_work, do_odds, do_archive, do_discover.

Usage: python3 scripts/tick_gate.py
"""
import os
import sys
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

ODDS_REFRESH_WINDOW_MIN = 45
ODDS_LEAD_MIN = 180
POST_RACE_SETTLE_MIN = 25
DISCOVERY_HORIZON_DAYS = 2

URL = os.environ.get('SUPABASE_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
KEY = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ.get('NEXT_PUBLIC_SUPABASE_ANON_KEY')


def fetch(path: str):
    url = f'{URL}/rest/v1/{urllib.parse.quote(path, safe="?&=,()*.:-")}'
    req = urllib.request.Request(
        url,
        headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Accept': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def race_start(race):
    date_str, race_time = race.get('race_date'), race.get('race_time')
    if not date_str or not race_time:
        return None
    try:
        hour, minute = (int(x) for x in str(race_time).split(':')[:2])
        day = datetime.strptime(str(date_str)[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return None
    return day.replace(hour=hour, minute=minute, tzinfo=HKT)


def main():
    if not URL or not KEY:
        print('[GATE] no Supabase credentials — skipping tick')
        emit(False, False, False, False, 'missing credentials')
        return 0

    now = datetime.now(HKT)
    today = now.strftime('%Y-%m-%d')

    unfinished = fetch(
        'races?select=race_id,race_date,venue,race_no,race_time'
        f'&race_date=lte.{today}&or=(is_finished.eq.false,is_finished.is.null)&limit=200'
    )

    # Nothing in the near future means Stage 1 never landed — odds and results
    # have no rows to attach to, so discovery is the only useful phase.
    horizon = (now + timedelta(days=DISCOVERY_HORIZON_DAYS)).strftime('%Y-%m-%d')
    upcoming_meeting = fetch(
        f'races?select=race_date&and=(race_date.gte.{today},race_date.lte.{horizon})&limit=1'
    )
    do_discover = not upcoming_meeting

    if not unfinished:
        print(f'[GATE] nothing unfinished up to today — {"discovery needed" if do_discover else "idle"}')
        emit(do_discover, False, False, do_discover,
             'no upcoming meeting in DB' if do_discover else 'no unfinished races')
        return 0

    todays = [r for r in unfinished if str(r['race_date'])[:10] == today]
    stale = [r for r in unfinished if str(r['race_date'])[:10] < today]

    do_archive = bool(stale) or any(
        (start := race_start(r)) is not None and (now - start).total_seconds() >= POST_RACE_SETTLE_MIN * 60
        for r in todays
    )

    lead = timedelta(minutes=ODDS_LEAD_MIN)
    upcoming = [r for r in todays
                if (start := race_start(r)) is not None and now < start <= now + lead]
    do_odds = False
    if upcoming:
        ids = ','.join(f'"{r["race_id"]}"' for r in upcoming)
        priced_rows = fetch(
            f'race_runners?select=race_id,win_odds&race_id=in.({ids})&win_odds=gt.1.0&limit=1000'
        )
        priced = set(r['race_id'] for r in priced_rows)
        for r in upcoming:
            if r['race_id'] not in priced:
                do_odds = True
                break
            if (race_start(r) - now) <= timedelta(minutes=ODDS_REFRESH_WINDOW_MIN):
                do_odds = True
                break

    print(f'[GATE] today={today} unfinished={len(unfinished)} upcoming={len(upcoming)} '
          f'odds={"yes" if do_odds else "no"} archive={"yes" if do_archive else "no"} '
          f'discover={"yes" if do_discover else "no"}')
    emit(do_odds or do_archive or do_discover, do_odds, do_archive, do_discover,
         f'{len(upcoming)} upcoming, {len(stale)} stale')
    return 0


def emit(need_work: bool, do_odds: bool, do_archive: bool, do_discover: bool, reason: str):
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a', encoding='utf-8') as fh:
            fh.write(f'need_work={"true" if need_work else "false"}\n')
            fh.write(f'do_odds={"true" if do_odds else "false"}\n')
            fh.write(f'do_archive={"true" if do_archive else "false"}\n')
            fh.write(f'do_discover={"true" if do_discover else "false"}\n')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as fh:
            fh.write(f'- Tick: work={"yes" if need_work else "no"} ({reason}) '
                     f'odds={"yes" if do_odds else "no"} archive={"yes" if do_archive else "no"} '
                     f'discover={"yes" if do_discover else "no"}\n')
    print(f'[GATE] need_work={need_work} do_odds={do_odds} do_archive={do_archive} do_discover={do_discover}')


if __name__ == '__main__':
    sys.exit(main())
