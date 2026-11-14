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
from typing import Dict
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

ODDS_REFRESH_WINDOW_MIN = 45
ODDS_LEAD_MIN = 180
POST_RACE_SETTLE_MIN = 25
DISCOVERY_HORIZON_DAYS = 2
DISCOVERY_MARKER_ID = 'tick_discovery'

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
    d = decide(now, today)

    if d['discover']:
        mark_discovery_attempt(today)
    print(f"[GATE] today={today} upcoming={d['upcoming']} stale={d['stale']} "
          f"odds={'yes' if d['odds'] else 'no'} archive={'yes' if d['archive'] else 'no'} "
          f"discover={'yes' if d['discover'] else 'no'} — {d['reason']}")
    emit(d['odds'] or d['archive'] or d['discover'], d['odds'], d['archive'], d['discover'], d['reason'])
    return 0


def decide(now, today: str) -> Dict:
    """What does the database need right now? Shared by Actions and the local tick."""
    unfinished = fetch(
        'races?select=race_id,race_date,venue,race_no,race_time'
        f'&race_date=lte.{today}&or=(is_finished.eq.false,is_finished.is.null)&limit=200'
    )
    do_discover, reason_seed = seed_check(now, today)

    if not unfinished:
        return {'odds': False, 'archive': False, 'discover': do_discover, 'upcoming': 0, 'stale': 0,
                'reason': reason_seed or 'no unfinished races'}

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

    return {'odds': do_odds, 'archive': do_archive, 'discover': do_discover,
            'upcoming': len(upcoming), 'stale': len(stale),
            'reason': f'{len(upcoming)} upcoming, {len(stale)} stale'
                      + (f'; {reason_seed}' if reason_seed else '')}


def seed_check(now, today: str):
    """Is the database too thin ahead of us to serve the next meetings?"""
    if discovery_attempted_today(today):
        return False, 'discovery already attempted today'

    horizon = (now + timedelta(days=DISCOVERY_HORIZON_DAYS)).strftime('%Y-%m-%d')
    near = fetch(f'races?select=race_date&and=(race_date.gte.{today},race_date.lte.{horizon})&limit=1')
    if not near:
        return True, f'no meeting between {today} and {horizon}'

    ahead = fetch(f'races?select=race_date&and=(race_date.gt.{today},race_date.lte.{horizon})&limit=1')
    if not ahead:
        return True, f'nothing queued after {today}'
    return False, None


def discovery_attempted_today(today: str) -> bool:
    try:
        rows = fetch(f'pipeline_status?select=status_json&id=eq.{DISCOVERY_MARKER_ID}')
    except Exception as e:
        print(f'[GATE] could not read discovery marker: {e}')
        return False
    return bool(rows) and rows[0].get('status_json', {}).get('attempted_date') == today


def mark_discovery_attempt(today: str):
    body = json.dumps({
        'id': DISCOVERY_MARKER_ID,
        'last_run': datetime.now(HKT).isoformat(),
        'status_json': {'attempted_date': today},
    }).encode()
    req = urllib.request.Request(
        f'{URL}/rest/v1/pipeline_status', data=body, method='POST',
        headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}',
                 'Content-Type': 'application/json',
                 'Prefer': 'return=minimal,resolution=merge-duplicates'},
    )
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:
        print(f'[GATE] could not record discovery attempt: {e}')


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
