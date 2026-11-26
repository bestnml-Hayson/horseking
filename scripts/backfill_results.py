#!/usr/bin/env python3
"""
Backfill results from HKJC for past race days not in DB.
Scrapes results pages, creates races + race_runners + horses,
runs Benter model and AI review.

Usage:
  python scripts/backfill_results.py
  python scripts/backfill_results.py --dates 2026-10-28,2026-11-01,2026-11-04
"""
import sys, os, io, time, re, argparse, random
if hasattr(sys.stdout, 'buffer'):  # a caller may already own the stream (tick_local's Tee)
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional

HKT = ZoneInfo('Asia/Hong_Kong')

from common import get_supabase, batch_upsert, retry_supabase
from run_style import encode_running_positions


def scrape_results_page(page, date_str: str, venue: str, race_no: int) -> Optional[Dict]:
    """Scrape a single race result from HKJC results page."""
    date_slash = date_str.replace('-', '/')
    date_path = date_str.replace('-', '')
    url = f"https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={date_slash}&Racecourse={venue}&RaceNo={race_no}"

    try:
        page.goto(url, wait_until='domcontentloaded', timeout=20000)
        time.sleep(random.uniform(3.0, 5.0))

        actual_url = page.url
        if date_slash not in actual_url and date_path not in actual_url:
            return None

        race_data = page.evaluate(r'''() => {
            const result = {horses: [], race_info: {}};

            // Extract race info (class, distance, going)
            const raceHeader = document.querySelector(".race_tab .current, [class*=raceHeader]");
            const bodyText = document.body.innerText;

            // Find the main results table
            const tables = document.querySelectorAll("table");
            for (const table of tables) {
                const rows = table.querySelectorAll("tr");
                if (rows.length < 5) continue;
                const headers = Array.from(rows[0].querySelectorAll("td, th")).map(c => c.textContent.trim());
                if (!headers.includes("名次") || !headers.includes("馬號")) continue;

                const colMap = {};
                headers.forEach((h, i) => { colMap[h] = i; });

                for (let i = 1; i < rows.length; i++) {
                    const cells = rows[i].querySelectorAll("td");
                    if (cells.length < 5) continue;

                    const get = (key) => {
                        const idx = colMap[key];
                        return idx !== undefined && idx < cells.length ? cells[idx].textContent.trim() : "";
                    };

                    const pos = parseInt(get("名次"));
                    if (isNaN(pos) || pos <= 0) continue;

                    const horseNo = parseInt(get("馬號"));
                    const horseNameRaw = get("馬名");
                    const horseName = horseNameRaw.replace(/\(.*\)/, '').trim();
                    const horseId = (horseNameRaw.match(/\(([A-Z]{1,2}\d{1,4})\)/) || [])[1] || "";

                    const winOdds = parseFloat(get("獨贏賠率")) || 0;
                    const draw = parseInt(get("檔位")) || 0;
                    const jockey = get("騎師");
                    const trainer = get("練馬師");
                    const weightCarried = parseInt(get("實際負磅")) || 0;
                    const declaredWeight = parseInt(get("排位體重")) || 0;
                    const margin = get("頭馬距離");
                    const finishTime = get("完成時間");
                    const runningPositions = get("沿途走位");

                    result.horses.push({
                        pos, horse_no: horseNo, horse_name: horseName, horse_id: horseId,
                        jockey, trainer, draw, weight_carried: weightCarried,
                        declared_weight: declaredWeight, win_odds: winOdds,
                        margin, finish_time: finishTime,
                        running_positions: runningPositions
                    });
                }
                break;
            }

            // Extract race metadata from page text
            const raceTitle = document.querySelector("td.raceNumber, .race_tab .current, h1");
            if (raceTitle) result.race_info.title = raceTitle.textContent.trim();

            // Try to find class, distance, going from page
            const allText = document.body.innerText;
            const classMatch = allText.match(/(第一班|第二班|第三班|第四班|第五班|新馬賽|國際一級賽|國際二級賽|國際三級賽|小組讓賽|不設分級)/);
            if (classMatch) result.race_info.class = classMatch[1];

            const distMatch = allText.match(/(\d+)\s*米/);
            if (distMatch) result.race_info.distance = parseInt(distMatch[1]);

            const goingMatch = allText.match(/(好地|好快地|好黏地|黏地|濕慢地|大爛地)/);
            if (goingMatch) result.race_info.going = goingMatch[1];

            // Check for race course indicator (ST/HV)
            const isST = allText.includes("沙田");
            const isHV = allText.includes("跑馬地");

            // A declared-void race publishes no finishers; every pool reads 退款.
            result.void_race = (allText.match(/退款/g) || []).length >= 3;

            return result;
        }''')

        if not race_data:
            return None
        if not race_data.get('horses') and not race_data.get('void_race'):
            return None

        return race_data

    except Exception as e:
        print(f"    [FAIL] R{race_no}: {e}")
        return None


def extract_race_class(title_text: str, page_text: str = "") -> Optional[str]:
    """Extract race class. Keep HKJC's own 第N班 wording — the racecard scraper
    writes that form, and mixing 'Class 4' rows into the same column used to make
    the class-movement factor unreadable."""
    labels = ('第一班', '第二班', '第三班', '第四班', '第五班',
              '國際一級賽', '國際二級賽', '國際三級賽', '新馬賽')
    for label in labels:
        if label in title_text or label in page_text:
            return label
    return None


MIN_RUNNERS = 4
DEFAULT_DATES = '2026-10-28:ST;2026-11-01:HV;2026-11-04:HV'


def parse_specs(specs_str: str) -> List[Dict]:
    """Parse ';'-separated 'DATE[:VENUE[:R1,R2]]' into meeting dicts."""
    out = []
    for raw in specs_str.split(';'):
        parts = raw.strip().split(':')
        if not parts[0].strip():
            continue
        out.append({
            'race_date': parts[0].strip(),
            'venue': parts[1].strip() if len(parts) > 1 and parts[1].strip() else None,
            'races': [int(x) for x in parts[2].split(',') if x.strip().isdigit()]
                     if len(parts) > 2 else [],
        })
    return out


def broken_race_nos(supabase, date_str: str, venue: str) -> List[int]:
    """Race numbers on this card that exist but have no (or purged) runner rows."""
    try:
        reg = retry_supabase(
            lambda: supabase.table('pipeline_status').select('status_json')
            .eq('id', VOID_REGISTRY_ID).limit(1).execute()
        ).data or []
        voided = set((reg[0].get('status_json') or {}).get('race_ids', [])) if reg else set()
    except Exception:
        voided = set()
    date_path = date_str.replace('-', '')
    races = retry_supabase(
        lambda: supabase.table('races').select('race_no')
        .eq('race_date', date_str).eq('venue', venue).order('race_no').limit(30).execute()
    ).data or []
    broken = []
    for r in races:
        if f"{venue}-{date_path}-{r['race_no']:02d}" in voided:
            continue
        rows = retry_supabase(
            lambda rn=r['race_no']: supabase.table('race_runners').select('finish_position')
            .eq('race_id', f"{venue}-{date_str.replace('-', '')}-{rn:02d}").limit(30).execute()
        ).data or []
        if len(rows) < MIN_RUNNERS or not any(x.get('finish_position') for x in rows):
            broken.append(r['race_no'])
    return broken


def scan_broken_meetings() -> List[Dict]:
    """Ask the tick gate which finished meetings are missing runners (DB-only, free)."""
    import tick_gate
    now = tick_gate.clock_now()
    return [{'race_date': m['race_date'], 'venue': m['venue'], 'races': m['races'],
             'from_gate': True}
            for m in tick_gate.runnerless_races(now, now.strftime('%Y-%m-%d'))]


def detect_venue(page, date_str: str) -> Optional[str]:
    """Which course ran on this date? HKJC answers with a different day if we guess wrong."""
    date_slash = date_str.replace('-', '/')
    for v in ['ST', 'HV']:
        url = (f'https://racing.hkjc.com/zh-hk/local/information/localresults'
               f'?racedate={date_slash}&Racecourse={v}&RaceNo=1')
        page.goto(url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(3)
        if date_slash not in page.url:
            continue
        horses = page.evaluate('''() => {
            for (const t of document.querySelectorAll("table")) {
                const rows = t.querySelectorAll("tr");
                if (rows.length >= 5) {
                    const headers = Array.from(rows[0].querySelectorAll("td, th")).map(c => c.textContent.trim());
                    if (headers.includes("名次")) return rows.length - 1;
                }
            }
            return 0;
        }''')
        if horses >= MIN_RUNNERS:
            return v
    return None


def build_meeting_records(date_str: str, venue: str, races_data: List[tuple]):
    """Turn scraped result pages into races / race_runners / horses rows."""
    date_path = date_str.replace('-', '')
    races, all_runners, all_horses, horse_set = [], [], [], set()

    for race_no, result in races_data:
        race_id = f"{venue}-{date_path}-{race_no:02d}"
        race_info = result.get('race_info', {})
        race_class = extract_race_class(race_info.get('title', ''), race_info.get('class', ''))

        races.append({
            'race_id': race_id,
            'race_date': date_str,
            'venue': venue,
            'race_no': race_no,
            'class_level': race_class or race_info.get('class'),
            'distance': race_info.get('distance'),
            'going': race_info.get('going'),
            'is_finished': True,
        })

        for h in result['horses']:
            horse_name = h['horse_name']
            horse_id_str = (h.get('horse_id') or '').strip() or horse_name

            all_runners.append({
                'runner_id': f"{race_id}_H{h['horse_no']:02d}",
                'race_id': race_id,
                'horse_no': h['horse_no'],
                'horse_id': horse_id_str,
                'jockey': h['jockey'],
                'trainer': h['trainer'],
                'draw': h['draw'],
                'actual_weight': h['weight_carried'],
                'declared_weight': h['declared_weight'],
                'win_odds': h['win_odds'] if h['win_odds'] > 1.0 else None,
                'finish_position': h['pos'],
                'sectional_times': encode_running_positions(
                    len(result['horses']), h.get('running_positions', '')
                ),
            })

            horse_key = horse_id_str or horse_name
            if horse_key not in horse_set:
                horse_set.add(horse_key)
                all_horses.append({'horse_name': horse_name, 'horse_id': horse_id_str or horse_name})

    return races, all_runners, all_horses


def scrape_meeting(page, date_str: str, venue: str, race_nos: List[int],
                   stop_at_first_miss: bool = False):
    """Scrape the given race numbers. Returns (races_data, void_race_ids)."""
    races_data, void_ids = [], []
    date_path = date_str.replace('-', '')
    for race_no in race_nos:
        print(f"  {date_str} {venue} R{race_no}: ", end='', flush=True)
        result = scrape_results_page(page, date_str, venue, race_no)
        if not result:
            print('no data')
            if stop_at_first_miss:
                break
            continue
        if not result.get('horses'):
            print('declared void (all pools refunded)')
            void_ids.append(f"{venue}-{date_path}-{race_no:02d}")
            continue
        print(f"{len(result['horses'])} horses")
        races_data.append((race_no, result))
        time.sleep(random.uniform(1.0, 2.0))
    return races_data, void_ids


VOID_REGISTRY_ID = 'void_races'


def record_void_races(supabase, race_ids: List[str]):
    """Close out declared-void races so neither the archive nor the integrity phase
    re-scrapes a result page that will never be published."""
    if not race_ids:
        return
    try:
        cur = retry_supabase(
            lambda: supabase.table('pipeline_status').select('status_json')
            .eq('id', VOID_REGISTRY_ID).limit(1).execute()
        ).data or []
        known = set((cur[0].get('status_json') or {}).get('race_ids', [])) if cur else set()
        known.update(race_ids)
        supabase.table('pipeline_status').upsert({
            'id': VOID_REGISTRY_ID,
            'last_run': datetime.now(HKT).isoformat(),
            'status_json': {'race_ids': sorted(known)},
        }, on_conflict='id').execute()
        for rid in race_ids:
            retry_supabase(
                lambda r=rid: supabase.table('races').update({'is_finished': True})
                .eq('race_id', r).execute()
            )
        print(f"  [OK] {len(race_ids)} race(s) recorded as void: {race_ids}")
    except Exception as e:
        print(f"  [WARN] could not record void races: {e}")


def split_dividends(supabase, races: List[Dict], all_runners: List[Dict]):
    """Results pages only carry the settled SP, but `race_runners.win_odds` must keep
    the price the app showed before the barrier — otherwise the backtest measures
    itself against the price it destroyed. Push the SP to the `race_results` ledger
    and restore any pre-race price already on the row."""
    meta = {r['race_id']: r for r in races}
    ids = list(meta)
    existing: Dict[str, float] = {}
    for i in range(0, len(ids), 10):
        chunk = ids[i:i + 10]
        resp = retry_supabase(
            lambda c=chunk: supabase.table('race_runners')
            .select('runner_id,win_odds').in_('race_id', c).execute()
        )
        existing.update({r['runner_id']: r.get('win_odds') for r in (resp.data or [])})

    ledger = []
    for row in all_runners:
        sp = row.get('win_odds')
        prior = existing.get(row['runner_id'])
        if prior and prior > 1.0:
            row['win_odds'] = prior
        if sp and sp > 1.0 and row.get('finish_position'):
            race = meta.get(row['race_id'], {})
            ledger.append({
                'race_id': row['race_id'],
                'race_date': race.get('race_date'),
                'venue': race.get('venue'),
                'race_no': race.get('race_no'),
                'finish_position': row['finish_position'],
                'horse_no': row['horse_no'],
                'horse_name': row['horse_id'],
                'jockey': row['jockey'],
                'trainer': row['trainer'],
                'win_odds': sp,
            })

    if ledger:
        try:
            batch_upsert(supabase, 'race_results', ledger, 'race_id,horse_no')
        except Exception as e:
            print(f"  [WARN] race_results dividend ledger failed: {e}")
    return len(ledger)


def write_meeting(supabase, races: List[Dict], all_runners: List[Dict], all_horses: List[Dict]):
    if all_horses:
        try:
            batch_upsert(supabase, 'horses', all_horses, 'horse_id')
        except Exception as e:
            print(f"  [WARN] horses upsert failed: {e}")
    split_dividends(supabase, races, all_runners)
    try:
        batch_upsert(supabase, 'races', races, 'race_id')
    except Exception as e:
        print(f"  [FAIL] races upsert: {e}")
        return False
    try:
        batch_upsert(supabase, 'race_runners', all_runners, 'runner_id')
    except Exception as e:
        print(f"  [FAIL] race_runners upsert: {e}")
        return False
    return True


def refill_meeting(supabase, page, date_str: str, venue: str, race_nos: List[int]) -> int:
    """Re-scrape races that exist but lost their runner rows (purge-then-write failures).

    Only horses and race_runners are written: the race rows themselves are what we
    keyed off, and rewriting their class/going would clobber the scraper's own
    format with the results page's.
    """
    races_data, void_ids = scrape_meeting(page, date_str, venue, race_nos)
    record_void_races(supabase, void_ids)
    if not races_data:
        return 0
    race_rows, all_runners, all_horses = build_meeting_records(date_str, venue, races_data)
    if all_horses:
        try:
            batch_upsert(supabase, 'horses', all_horses, 'horse_id')
        except Exception as e:
            print(f"  [WARN] horses upsert failed: {e}")
    split_dividends(supabase, race_rows, all_runners)
    try:
        batch_upsert(supabase, 'race_runners', all_runners, 'runner_id')
    except Exception as e:
        print(f"  [FAIL] race_runners upsert: {e}")
        return 0
    print(f"  [OK] {date_str} {venue}: refilled {len(all_runners)} runners over {len(races_data)} races")
    return len(all_runners)


def backfill_race_day(supabase, page, date_str: str, venue: str):
    """Scrape and write all races for a single race day."""
    # Check if already in DB
    existing = retry_supabase(
        lambda: supabase.table('races').select('race_id').eq('race_date', date_str).eq('venue', venue).limit(1).execute()
    )
    if existing.data and len(existing.data) > 0:
        print(f"  {date_str} {venue}: already in DB, skipping")
        return 0

    print(f"\n{'='*50}")
    print(f"  Backfilling {date_str} {venue}")
    print(f"{'='*50}")

    races_data, void_ids = scrape_meeting(page, date_str, venue, list(range(1, 12)),
                                          stop_at_first_miss=True)
    record_void_races(supabase, void_ids)
    if not races_data:
        print(f"  [WARN] No races found for {date_str} {venue}")
        return 0

    races, all_runners, all_horses = build_meeting_records(date_str, venue, races_data)

    print(f"\n  [Write] Writing {len(races)} races, {len(all_runners)} runners...")
    if not write_meeting(supabase, races, all_runners, all_horses):
        return 0

    return len(races)


def open_page(playwright):
    """Headless Chromium with the bot-detection tweaks the HKJC pages need."""
    browser = playwright.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-gpu', '--disable-blink-features=AutomationControlled'])
    page = browser.new_page()
    page.set_extra_http_headers({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Referer': 'https://racing.hkjc.com/',
    })
    page.add_init_script('()=>{Object.defineProperty(navigator,"webdriver",{get:()=>undefined})}')
    return browser, page


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dates', default='',
                        help=';-separated DATE[:VENUE[:R1,R2]] meetings to process. '
                             'Empty = auto (new cards for --dates, tick gate scan for --refill)')
    parser.add_argument('--refill', action='store_true',
                        help='Re-scrape races that exist but lost their runner rows')
    parser.add_argument('--skip-benter', action='store_true')
    parser.add_argument('--skip-review', action='store_true')
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv('.env.local')

    supabase = get_supabase()
    if not supabase:
        print("[FAIL] Cannot connect to Supabase")
        sys.exit(1)

    if args.refill:
        meetings = parse_specs(args.dates) if args.dates else scan_broken_meetings()
        for m in meetings:
            if not m['races']:
                m['races'] = broken_race_nos(supabase, m['race_date'], m['venue'])
        meetings = [m for m in meetings if m['venue'] and m['races']]
        if not meetings:
            print('[REFILL] nothing broken — all finished races have runners')
            return
        print(f"[REFILL] {len(meetings)} meeting(s): "
              + ', '.join(f"{m['race_date']} {m['venue']} R{m['races']}" for m in meetings))
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser, page = open_page(p)
            written = 0
            for m in meetings:
                written += refill_meeting(supabase, page, m['race_date'], m['venue'], m['races'])
            browser.close()
        print(f"\n[REFILL] done: {written} runner rows rewritten")
        return

    specs = parse_specs(args.dates or DEFAULT_DATES)
    dates = [f"{m['race_date']}:{m['venue']}" for m in specs] or []

    total_races = 0
    all_race_ids = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page = open_page(p)

        for spec in specs:
            date_str, venue = spec['race_date'], spec['venue']
            if not venue:
                venue = detect_venue(page, date_str)

            if not venue:
                print(f"[SKIP] {date_str}: cannot determine venue")
                continue

            races_count = backfill_race_day(supabase, page, date_str, venue)
            total_races += races_count

            # Collect race IDs for Benter/review
            date_path = date_str.replace('-', '')
            for rn in range(1, 12):
                all_race_ids.append(f"{venue}-{date_path}-{rn:02d}")

        browser.close()

    print(f"\n{'='*50}")
    print(f"Backfill complete: {total_races} races written")
    print(f"{'='*50}")

    # Run Benter model
    if total_races > 0 and not args.skip_benter:
        # Filter to only race IDs that actually exist
        existing = retry_supabase(
            lambda: supabase.table('races').select('race_id').in_('race_id', all_race_ids).execute()
        )
        actual_ids = [r['race_id'] for r in (existing.data or [])]

        if actual_ids:
            print(f"\n[Benter] Running model for {len(actual_ids)} races...")
            try:
                from benter_model import run_analysis
                run_analysis(supabase, race_ids=actual_ids, dry_run=False, pre_race=False)
                print(f"[OK] Benter model done")
            except Exception as e:
                print(f"[WARN] Benter model failed: {e}")

    # Run AI review
    if total_races > 0 and not args.skip_review:
        existing = retry_supabase(
            lambda: supabase.table('races').select('race_id').in_('race_id', all_race_ids).execute()
        )
        actual_ids = [r['race_id'] for r in (existing.data or [])]

        if actual_ids:
            print(f"\n[AI Review] Running review for {len(actual_ids)} races...")
            try:
                from ai_review import review_single_race
                reviewed = 0
                for race_id in actual_ids:
                    try:
                        summary = review_single_race(supabase, race_id)
                        if summary:
                            reviewed += 1
                    except Exception as e:
                        print(f"  {race_id}: {e}")
                print(f"[OK] AI review done: {reviewed}/{len(actual_ids)} races")
            except Exception as e:
                print(f"[WARN] AI review failed: {e}")


if __name__ == '__main__':
    main()
