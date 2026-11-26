"""
Race-day tick gate — decides whether the Auto-Pilot tick has anything to do.

Runs on the bare GitHub runner (stdlib only, no pip install) so an idle
half-hour costs seconds instead of a Playwright bootstrap. Writes the
need_work / do_odds / do_archive / do_discover / do_integrity outputs that the
following steps are gated on.

Usage: python3 scripts/tick_gate.py
"""
import os
import sys
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

ODDS_SEED_HOURS = 26
ODDS_LEAD_MIN = 180
ODDS_REFRESH_MIN = 20
DRIFT_MARKER_ID = 'odds_drift'
POST_RACE_SETTLE_MIN = 25
DISCOVERY_HORIZON_DAYS = 2
DISCOVERY_RETRY_HOURS = 6
DISCOVERY_MARKER_ID = 'tick_discovery'
STALE_MARKER_ID = 'tick_stale_archive'
INTEGRITY_MARKER_ID = 'tick_integrity_backfill'
VOID_REGISTRY_ID = 'void_races'
INTEGRITY_LOOKBACK_DAYS = 45
MIN_RUNNERS = 4

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
    if d['integrity_work']:
        mark_attempt(INTEGRITY_MARKER_ID, today)
    print(f"[GATE] today={today} upcoming={d['upcoming']} stale={d['stale']} "
          f"odds={'yes' if d['odds'] else 'no'} archive={'yes' if d['archive'] else 'no'} "
          f"discover={'yes' if d['discover'] else 'no'} "
          f"integrity={'yes' if d['integrity_work'] else 'no'} — {d['reason']}")
    emit(d['odds'] or d['archive'] or d['discover'] or d['integrity_work'],
         d['odds'], d['archive'], d['discover'], d['reason'],
         do_integrity=d['integrity_work'],
         integrity_dates=';'.join(f"{m['race_date']}:{m['venue']}" for m in d['integrity']))
    return 0


def decide(now, today: str) -> Dict:
    """What does the database need right now? Shared by Actions and the local tick."""
    seed_until = (now + timedelta(hours=ODDS_SEED_HOURS)).strftime('%Y-%m-%d')
    queued = fetch(
        'races?select=race_id,race_date,venue,race_no,race_time'
        f'&race_date=lte.{seed_until}&or=(is_finished.eq.false,is_finished.is.null)&limit=200'
    )
    do_discover, reason_seed = seed_check(now, today)

    # A finished race can lose its race_runners rows to the scraper's purge-then-write
    # cycle, and the queued-work query above cannot see it (unfinished races only).
    # Check for them explicitly, once a day.
    do_integrity = False
    integrity = []
    if not attempted_today(INTEGRITY_MARKER_ID, today):
        integrity = runnerless_races(now, today)
        do_integrity = bool(integrity)

    overdue = [r for r in queued if str(r['race_date'])[:10] <= today]
    if not queued:
        idle = reason_seed or 'nothing queued up to tomorrow'
        return {'odds': False, 'archive': False, 'discover': do_discover, 'stale_wait': False,
                'integrity': integrity, 'integrity_work': do_integrity,
                'upcoming': 0, 'stale': 0,
                'reason': f'{len(integrity)} runnerless meeting(s); {idle}'
                          if do_integrity else idle}

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
        near_age = None
        for r in upcoming:
            if r['race_id'] not in priced:
                do_odds = True
                break
            if (race_start(r) - now) <= lead:
                # Even with every runner priced, the last 3 hours are where the
                # money moves — re-pull so the drift series sees it, throttled.
                if near_age is None:
                    near_age = last_attempt_age_hours(DRIFT_MARKER_ID, now)
                if near_age is None or near_age * 60 >= ODDS_REFRESH_MIN:
                    do_odds = True
                    break

    return {'odds': do_odds, 'archive': do_archive, 'discover': do_discover,
            'integrity': integrity, 'integrity_work': do_integrity,
            'stale_wait': stale_wait,
            'upcoming': len(upcoming), 'stale': len(stale),
            'reason': f'{len(upcoming)} upcoming, {len(stale)} stale'
                      + (f'; {len(integrity)} runnerless meeting(s)' if do_integrity else '')
                      + (f'; {reason_seed}' if reason_seed else '')}


def void_race_ids() -> set:
    """Races HKJC declared void — every pool refunded, so no result page will ever exist."""
    try:
        rows = fetch(f'pipeline_status?select=status_json&id=eq.{VOID_REGISTRY_ID}')
    except Exception as e:
        print(f'[GATE] could not read the void registry: {e}')
        return set()
    return set(rows[0].get('status_json', {}).get('race_ids', [])) if rows else set()


def runnerless_races(now, today: str):
    """Finished meetings in the lookback window whose runner rows or result rows are missing."""
    since = (now - timedelta(days=INTEGRITY_LOOKBACK_DAYS)).strftime('%Y-%m-%d')
    rows = fetch(f'races?select=race_id,race_date,venue,race_no&race_date=gte.{since}'
                 f'&race_date=lte.{today}&is_finished=eq.true&order=race_date.desc&limit=400')
    if not rows:
        return []
    voided = void_race_ids()
    rows = [r for r in rows if r['race_id'] not in voided]
    by_id = {r['race_id']: r for r in rows}
    ids = list(by_id)
    counts, positions = {}, {}
    for i in range(0, len(ids), 60):
        chunk = ','.join(f'"{x}"' for x in ids[i:i + 60])
        got = fetch(f'race_runners?select=race_id,finish_position&race_id=in.({chunk})&limit=5000')
        for g in got:
            rid = g['race_id']
            counts[rid] = counts.get(rid, 0) + 1
            if g.get('finish_position'):
                positions[rid] = positions.get(rid, 0) + 1
    broken = [by_id[x] for x in ids if counts.get(x, 0) < MIN_RUNNERS or not positions.get(x)]
    meetings = {}
    for r in broken:
        key = (str(r['race_date'])[:10], r['venue'])
        meetings.setdefault(key, []).append(r['race_no'])
    return [{'race_date': d, 'venue': v, 'races': sorted(n for n in ns)}
            for (d, v), ns in sorted(meetings.items())]


def seed_check(now, today: str):
    """Is the database too thin around us to serve the next meetings?

    Not "once a day": HKJC publishes a card during the day, and whichever tick
    stamps the marker first (Actions at dawn, or the local loop) would lock
    discovery out until the next morning, leaving a meeting unpriced. With
    nothing queued the tick has no other work anyway, so retry on a timer.
    """
    horizon = (now + timedelta(days=DISCOVERY_HORIZON_DAYS)).strftime('%Y-%m-%d')
    queued = fetch(f'races?select=race_id&race_date=gte.{today}&race_date=lte.{horizon}'
                   f'&or=(is_finished.eq.false,is_finished.is.null)&limit=1')
    if queued:
        return False, None

    age = last_attempt_age_hours(DISCOVERY_MARKER_ID, now)
    if age is not None and age < DISCOVERY_RETRY_HOURS:
        return False, f'nothing queued, next discovery in {DISCOVERY_RETRY_HOURS - age:.0f}h'
    return True, f'no meeting between {today} and {horizon}'


def last_attempt_age_hours(marker_id: str, now) -> Optional[float]:
    try:
        rows = fetch(f'pipeline_status?select=last_run&id=eq.{marker_id}')
    except Exception:
        return None
    stamp = (rows[0].get('last_run') if rows else None)
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=HKT)
    return (now - when).total_seconds() / 3600.0


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


def mark_discovery_attempt(today: str):
    mark_attempt(DISCOVERY_MARKER_ID, today)


def emit(need_work: bool, do_odds: bool, do_archive: bool, do_discover: bool, reason: str,
         do_integrity: bool = False, integrity_dates: str = ''):
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a', encoding='utf-8') as fh:
            fh.write(f'need_work={"true" if need_work else "false"}\n')
            fh.write(f'do_odds={"true" if do_odds else "false"}\n')
            fh.write(f'do_archive={"true" if do_archive else "false"}\n')
            fh.write(f'do_discover={"true" if do_discover else "false"}\n')
            fh.write(f'do_integrity={"true" if do_integrity else "false"}\n')
            fh.write(f'integrity_dates={integrity_dates}\n')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as fh:
            fh.write(f'- Tick: work={"yes" if need_work else "no"} ({reason}) '
                     f'odds={"yes" if do_odds else "no"} archive={"yes" if do_archive else "no"} '
                     f'discover={"yes" if do_discover else "no"} integrity={"yes" if do_integrity else "no"}\n')
    print(f'[GATE] need_work={need_work} do_odds={do_odds} do_archive={do_archive} '
          f'do_discover={do_discover} do_integrity={do_integrity}')


if __name__ == '__main__':
    sys.exit(main())
