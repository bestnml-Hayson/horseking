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
from email.utils import parsedate_to_datetime
from typing import Dict
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

ODDS_SEED_HOURS = 26
ODDS_LEAD_MIN = 180
POST_RACE_SETTLE_MIN = 25
DISCOVERY_HORIZON_DAYS = 2
DISCOVERY_MARKER_ID = 'tick_discovery'
STALE_MARKER_ID = 'tick_stale_archive'

URL = os.environ.get('SUPABASE_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
KEY = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ.get('NEXT_PUBLIC_SUPABASE_ANON_KEY')

CLOCK_HOSTS = ('https://racing.hkjc.com/zh-hk/index', 'https://api.github.com')
CLOCK_TOLERANCE_MIN = 15
_clock_offset = None


def server_now():
    """Real wall clock from an HTTPS server's Date header, as HKT."""
    for host in CLOCK_HOSTS:
        try:
            req = urllib.request.Request(host, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                header = resp.headers.get('Date')
            if header:
                return parsedate_to_datetime(header).astimezone(HKT)
        except Exception as e:
            print(f'[CLOCK] {host} unusable: {type(e).__name__}: {e}')
    return None


def clock_now():
    """Local time corrected by the server offset, so a drifted machine clock can
    never silently point the whole pipeline at the wrong race day."""
    global _clock_offset
    local = datetime.now(HKT)
    if _clock_offset is None:
        server = server_now()
        _clock_offset = (server - local) if server else timedelta(0)
        if abs(_clock_offset) > timedelta(minutes=CLOCK_TOLERANCE_MIN):
            print(f'[CLOCK] local clock is off by {_clock_offset} — using server time instead')
    return local + _clock_offset


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

    now = clock_now()
    today = now.strftime('%Y-%m-%d')
    d = decide(now, today)

    if d['discover']:
        mark_discovery_attempt(today)
    if d['stale_wait']:
        mark_attempt(STALE_MARKER_ID, today)
    print(f"[GATE] today={today} upcoming={d['upcoming']} stale={d['stale']} "
          f"odds={'yes' if d['odds'] else 'no'} archive={'yes' if d['archive'] else 'no'} "
          f"discover={'yes' if d['discover'] else 'no'} — {d['reason']}")
    emit(d['odds'] or d['archive'] or d['discover'], d['odds'], d['archive'], d['discover'], d['reason'])
    return 0


def decide(now, today: str) -> Dict:
    """What does the database need right now? Shared by Actions and the local tick."""
    seed_until = (now + timedelta(hours=ODDS_SEED_HOURS)).strftime('%Y-%m-%d')
    queued = fetch(
        'races?select=race_id,race_date,venue,race_no,race_time'
        f'&race_date=lte.{seed_until}&or=(is_finished.eq.false,is_finished.is.null)&limit=200'
    )
    do_discover, reason_seed = seed_check(now, today)

    overdue = [r for r in queued if str(r['race_date'])[:10] <= today]
    if not queued:
        return {'odds': False, 'archive': False, 'discover': do_discover, 'stale_wait': False,
                'upcoming': 0, 'stale': 0,
                'reason': reason_seed or 'nothing queued up to tomorrow'}

    todays = [r for r in overdue if str(r['race_date'])[:10] == today]
    stale = [r for r in overdue if str(r['race_date'])[:10] < today]

    settled = any(
        (start := race_start(r)) is not None and (now - start).total_seconds() >= POST_RACE_SETTLE_MIN * 60
        for r in todays
    )
    # A race from an earlier day may have been voided, or HKJC may have dropped its
    # results page for good. Retrying it every tick only burns scraper runs, so
    # stale work gets one attempt per calendar day; today's races retry freely.
    stale_wait = bool(stale) and not attempted_today(STALE_MARKER_ID, today)
    do_archive = settled or stale_wait

    # A race is worth a price as soon as it is within a race-day's reach, then it
    # is re-pulled on every tick inside the lead window so the stored price ends
    # up near the barrier.
    seed = timedelta(hours=ODDS_SEED_HOURS)
    lead = timedelta(minutes=ODDS_LEAD_MIN)
    upcoming = [r for r in queued
                if (start := race_start(r)) is not None and now < start <= now + seed]
    do_odds = False
    if upcoming:
        ids = ','.join(f'"{r["race_id"]}"' for r in upcoming)
        priced_rows = fetch(
            f'race_runners?select=race_id,win_odds&race_id=in.({ids})&win_odds=gt.1.0&limit=1000'
        )
        priced = set(r['race_id'] for r in priced_rows)
        for r in upcoming:
            if r['race_id'] not in priced or (race_start(r) - now) <= lead:
                do_odds = True
                break

    return {'odds': do_odds, 'archive': do_archive, 'discover': do_discover, 'stale_wait': stale_wait,
            'upcoming': len(upcoming), 'stale': len(stale),
            'reason': f'{len(upcoming)} upcoming, {len(stale)} stale'
                      + (f'; {reason_seed}' if reason_seed else '')}


def seed_check(now, today: str):
    """Is the database too thin around us to serve the next meetings?"""
    if discovery_attempted_today(today):
        return False, 'discovery already attempted today'

    if not fetch(f'races?select=race_id&race_date=eq.{today}&limit=1'):
        return True, f'no meeting dated {today} in DB'

    horizon = (now + timedelta(days=DISCOVERY_HORIZON_DAYS)).strftime('%Y-%m-%d')
    near = fetch(f'races?select=race_date&and=(race_date.gte.{today},race_date.lte.{horizon})&limit=1')
    if not near:
        return True, f'no meeting between {today} and {horizon}'

    ahead = fetch(f'races?select=race_date&and=(race_date.gt.{today},race_date.lte.{horizon})&limit=1')
    if not ahead:
        return True, f'nothing queued after {today}'
    return False, None


def attempted_today(marker_id: str, today: str) -> bool:
    try:
        rows = fetch(f'pipeline_status?select=status_json&id=eq.{marker_id}')
    except Exception as e:
        print(f'[GATE] could not read marker {marker_id}: {e}')
        return False
    return bool(rows) and rows[0].get('status_json', {}).get('attempted_date') == today


def mark_attempt(marker_id: str, today: str):
    body = json.dumps({
        'id': marker_id,
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
        print(f'[GATE] could not record marker {marker_id}: {e}')


def discovery_attempted_today(today: str) -> bool:
    return attempted_today(DISCOVERY_MARKER_ID, today)


def mark_discovery_attempt(today: str):
    mark_attempt(DISCOVERY_MARKER_ID, today)


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
