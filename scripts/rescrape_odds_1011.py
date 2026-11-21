"""
Re-scrape HKJC live odds for 2026-10-11 ST and update race_runners + model_predictions
"""
import os, sys, json, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from supabase import create_client, Client
from playwright.sync_api import sync_playwright

load_dotenv('.env.local')
sb: Client = create_client(os.getenv('NEXT_PUBLIC_SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

DATE = '2026-10-11'
DATE_SLASH = '2026/10/11'
VENUE = 'ST'
RACES = list(range(1, 12))


def scrape_odds(page, race_no):
    url = f"https://bet.hkjc.com/racing/wp/{DATE_SLASH}/{VENUE}/{race_no}"
    page.goto(url, timeout=20000)
    page.wait_for_load_state('networkidle', timeout=15000)
    time.sleep(2)

    odds_map = page.evaluate("""
        () => {
            const result = {};
            const rows = document.querySelectorAll('tr');
            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 8) {
                    const noCell = cells[0] || cells[1];
                    const noText = noCell ? noCell.textContent.trim() : '';
                    if (/^\\d+$/.test(noText)) {
                        let oddsText = '';
                        for (let i = 2; i < cells.length; i++) {
                            const t = cells[i].textContent.trim();
                            if (/^\\d+\\.?\\d*$/.test(t) && parseFloat(t) > 1) {
                                oddsText = t;
                                break;
                            }
                        }
                        if (oddsText) {
                            result[noText] = parseFloat(oddsText);
                        }
                    }
                }
            }
            return result;
        }
    """)
    return odds_map


def main():
    print("=" * 60)
    print(f"Re-scrape odds for {DATE} {VENUE}")
    print("=" * 60)

    all_odds = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for race_no in RACES:
            try:
                odds = scrape_odds(page, race_no)
                all_odds[race_no] = odds
                print(f"  R{race_no}: {len(odds)} horses, sample: {list(odds.items())[:3]}")
            except Exception as e:
                print(f"  R{race_no}: ERROR {e}")
                all_odds[race_no] = {}
        browser.close()

    total_updated = 0
    for race_no in RACES:
        odds_map = all_odds.get(race_no, {})
        if not odds_map:
            continue

        race_id = f"{VENUE}-{DATE.replace('-','')}-{race_no:02d}"

        resp = sb.table('race_runners').select('runner_id,horse_no,win_odds').eq('race_id', race_id).execute()
        runners = resp.data or []

        for runner in runners:
            hno = runner['horse_no']
            new_odds = odds_map.get(str(hno))
            if new_odds is None:
                continue

            old_odds = runner.get('win_odds')
            if old_odds == new_odds:
                continue

            sb.table('race_runners').update({'win_odds': new_odds}).eq('runner_id', runner['runner_id']).execute()
            total_updated += 1
            if old_odds != new_odds:
                print(f"  R{race_no} #{hno}: {old_odds} -> {new_odds}")

    print(f"\nUpdated {total_updated} odds records")

    # Recompute P_market for affected races
    for race_no in RACES:
        race_id = f"{VENUE}-{DATE.replace('-','')}-{race_no:02d}"
        runners_resp = sb.table('race_runners').select('runner_id,horse_no,win_odds').eq('race_id', race_id).execute()
        runners = runners_resp.data or []

        odds_list = [(r['runner_id'], r['win_odds']) for r in runners if r.get('win_odds') and r['win_odds'] > 0]
        if not odds_list:
            continue

        total_inv = sum(1.0 / o for _, o in odds_list)
        if total_inv < 0.01:
            continue

        for runner_id, odds in odds_list:
            p_market = (1.0 / odds) / total_inv
            p_model_resp = sb.table('model_predictions').select('raw_model_prob').eq('runner_id', runner_id).execute()
            if not p_model_resp.data:
                continue
            p_model = p_model_resp.data[0].get('raw_model_prob')
            if not p_model:
                continue

            # Linear fusion 50/50
            p_final = 0.5 * p_model + 0.5 * p_market
            ev = p_final * odds - 1.0
            kelly = max(0, ev / (odds - 1)) * 0.25 if odds > 1 else 0

            sb.table('model_predictions').update({
                'market_implied_prob': round(p_market, 5),
                'final_prob': round(p_final, 5),
                'expected_value': round(ev, 4),
                'kelly_fraction': round(kelly, 4),
            }).eq('runner_id', runner_id).execute()

    print("P_market/P_final/EV/Kelly recomputed")


if __name__ == '__main__':
    main()
