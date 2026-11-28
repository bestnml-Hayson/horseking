#!/usr/bin/env python3
"""Phase 0 read-only audit: coverage, leakage surface, odds honesty.

No writes. Prints a JSON summary used to author reports/phase0_audit_*.md.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

if hasattr(sys.stdout, 'buffer'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase

SINCE = '2026-06-01'
RUNNER_COLS = (
    'runner_id,race_id,horse_id,horse_no,draw,actual_weight,official_rating,'
    'win_odds,best_time,sectional_times,gear,rest_days,finish_time,margin,'
    'form_history,form_positions,jockey,trainer,jockey_win_rate,trainer_win_rate,'
    'weight_change,season_prize,age,career_starts,career_wins,career_places,'
    'trial_count,fast_work_count,swim_count,fitness_score,fitness_label,'
    'races!inner(race_date,venue,distance,class_level)'
)
HIST_COLS = ('runner_id,horse_id,jockey,jockey_win_rate,finish_position,'
             'races!inner(race_date,venue,distance)')


def page1000(build):
    rows, offset = [], 0
    while True:
        got = retry_supabase(lambda o=offset: build(o).range(o, o + 999).execute()).data or []
        rows.extend(got)
        if len(got) < 1000:
            break
        offset += 1000
    return rows


def pct(n, d):
    return round(100.0 * n / d, 2) if d else 0.0


def coverage(rows, key, pred):
    ok = sum(1 for r in rows if pred(r.get(key)))
    return {'n': ok, 'pct': pct(ok, len(rows))}


def main():
    sb = get_supabase()
    out = {'since': SINCE}

    races = page1000(lambda o: sb.table('races')
                     .select('race_id,race_date,venue,race_no,distance,class_level,going,track_course')
                     .eq('is_finished', True).gte('race_date', SINCE)
                     .in_('venue', ['HV', 'ST']).order('race_id'))
    out['races'] = {'n': len(races)}
    out['races']['venues'] = dict(Counter(r['venue'] for r in races))
    out['races']['date_range'] = [min(r['race_date'] for r in races), max(r['race_date'] for r in races)] if races else None
    out['races']['going'] = dict(Counter((r.get('going') or '∅') for r in races).most_common(8))
    out['races']['track_course_nonnull'] = coverage(races, 'track_course', lambda v: bool(v))

    race_meta = {r['race_id']: r for r in races}
    runners = []
    ids = list(race_meta)
    for i in range(0, len(ids), 40):
        chunk = set(ids[i:i + 40])
        runners.extend(page1000(lambda o, c=chunk: sb.table('race_runners')
                                .select(RUNNER_COLS).in_('race_id', list(c))
                                .order('runner_id')))
    for r in runners:
        race = r.get('races')
        if isinstance(race, list):
            race = race[0] if race else {}
        r['_race'] = race or {}

    out['runners'] = {'n': len(runners)}
    C = out['runners']['coverage'] = {}
    C['win_odds_gt1'] = coverage(runners, 'win_odds', lambda v: v is not None and float(v) > 1)
    C['actual_weight_gt0'] = coverage(runners, 'actual_weight', lambda v: v is not None and float(v) > 0)
    C['official_rating'] = coverage(runners, 'official_rating', lambda v: v is not None)
    C['jockey_win_rate_nonnull'] = coverage(runners, 'jockey_win_rate', lambda v: v is not None)
    C['jockey_win_rate_eq_010'] = coverage(runners, 'jockey_win_rate', lambda v: v is not None and abs(float(v) - 0.10) < 1e-9)
    C['trainer_win_rate_nonnull'] = coverage(runners, 'trainer_win_rate', lambda v: v is not None)
    C['trainer_win_rate_eq_010'] = coverage(runners, 'trainer_win_rate', lambda v: v is not None and abs(float(v) - 0.10) < 1e-9)
    C['rest_days'] = coverage(runners, 'rest_days', lambda v: v is not None)
    C['gear_nonempty'] = coverage(runners, 'gear', lambda v: bool(str(v or '').strip()))
    C['form_history_nonempty'] = coverage(runners, 'form_history', lambda v: bool(str(v or '').strip()))
    C['form_positions_nonempty'] = coverage(runners, 'form_positions', lambda v: bool(str(v or '').strip()))
    C['weight_change_column'] = coverage(runners, 'weight_change', lambda v: v is not None)
    C['season_prize'] = coverage(runners, 'season_prize', lambda v: v is not None)
    C['age'] = coverage(runners, 'age', lambda v: v is not None)
    C['career_starts'] = coverage(runners, 'career_starts', lambda v: v is not None)
    C['trial_count'] = coverage(runners, 'trial_count', lambda v: v is not None)
    C['fast_work_count'] = coverage(runners, 'fast_work_count', lambda v: v is not None)
    C['swim_count'] = coverage(runners, 'swim_count', lambda v: v is not None)
    C['fitness_score'] = coverage(runners, 'fitness_score', lambda v: v is not None)
    C['finish_time_nonempty'] = coverage(runners, 'finish_time', lambda v: bool(str(v or '').strip()))
    C['margin_nonempty'] = coverage(runners, 'margin', lambda v: bool(str(v or '').strip()))

    bt_re = re.compile(r'^\d+\.\d{2}\.\d{2}$')
    C['best_time_parseable'] = coverage(runners, 'best_time', lambda v: bool(bt_re.match(str(v or '').strip())))
    C['best_time_nonempty'] = coverage(runners, 'best_time', lambda v: bool(str(v or '').strip()))
    sec_re = re.compile(r'^\d+\|[\d\s]+$')
    C['sectional_parseable'] = coverage(runners, 'sectional_times', lambda v: bool(sec_re.match(str(v or '').strip())))
    out['runners']['samples'] = {
        'best_time': [r.get('best_time') for r in runners if r.get('best_time')][:5],
        'finish_time': [r.get('finish_time') for r in runners if r.get('finish_time')][:5],
        'margin': [r.get('margin') for r in runners if r.get('margin')][:5],
        'sectional': [r.get('sectional_times') for r in runners if r.get('sectional_times')][:3],
        'form_history': [r.get('form_history') for r in runners if r.get('form_history')][:3],
    }

    # Field size / draw integrity
    by_race = defaultdict(list)
    for r in runners:
        by_race[r['race_id']].append(r)
    sizes = [len(v) for v in by_race.values()]
    bad_draw = 0
    for rid, rows in by_race.items():
        n = len(rows)
        if any((r.get('draw') or 0) > n for r in rows):
            bad_draw += 1
    out['field'] = {
        'races': len(by_race),
        'size_min': min(sizes) if sizes else 0,
        'size_median': sorted(sizes)[len(sizes) // 2] if sizes else 0,
        'size_max': max(sizes) if sizes else 0,
        'draw_gt_fieldsize_races': bad_draw,
    }

    # SP honesty check
    sp = {}
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        got = page1000(lambda o, c=chunk: sb.table('race_results')
                       .select('race_id,horse_no,win_odds').in_('race_id', c).order('race_id'))
        for row in got:
            if row.get('win_odds'):
                sp[(row['race_id'], row.get('horse_no'))] = float(row['win_odds'])
    differ_races, compared = 0, 0
    for rid, rows in by_race.items():
        pairs = [(float(r['win_odds']), sp.get((rid, r.get('horse_no'))))
                 for r in rows if r.get('win_odds') and float(r['win_odds']) > 1]
        pairs = [(a, b) for a, b in pairs if b]
        if not pairs:
            continue
        compared += 1
        if any(abs(a - b) > 1e-6 for a, b in pairs):
            differ_races += 1
    out['odds_honesty'] = {'races_compared': compared, 'races_with_pre_race_price': differ_races,
                           'races_sp_copy': compared - differ_races}

    # Odds drift snapshots in pipeline_status
    drift = sb.table('pipeline_status').select('status_json,updated_at').eq('id', 'odds_drift').execute().data or []
    dr = {'races': 0, 'runners': 0, 'runners_ge2_points': 0, 'points': 0, 'ts_min': None, 'ts_max': None}
    if drift:
        sj = drift[0].get('status_json') or {}
        races_json = sj.get('races') or {}
        dr['races'] = len(races_json)
        for rid, race in races_json.items():
            for runner in (race.get('runners') or {}).values():
                pts = runner.get('points') or []
                dr['runners'] += 1
                dr['points'] += len(pts)
                if len(pts) >= 2:
                    dr['runners_ge2_points'] += 1
                for p in pts:
                    ts = p[0] if isinstance(p, list) and p else None
                    if ts:
                        dr['ts_min'] = ts if dr['ts_min'] is None else min(dr['ts_min'], ts)
                        dr['ts_max'] = ts if dr['ts_max'] is None else max(dr['ts_max'], ts)
        dr['updated_at'] = drift[0].get('updated_at')
    out['odds_drift'] = dr

    # All-time start history for the sampled horses
    horse_ids = sorted({r['horse_id'] for r in runners if r.get('horse_id')})
    hist = defaultdict(list)
    for i in range(0, len(horse_ids), 40):
        batch = horse_ids[i:i + 40]
        rows = page1000(lambda o, b=batch: sb.table('race_runners')
                        .select(HIST_COLS).in_('horse_id', b)
                        .not_.is_('finish_position', 'null').order('runner_id'))
        for row in rows:
            race = row.get('races')
            if isinstance(race, list):
                race = race[0] if race else {}
            if not race or not race.get('race_date'):
                continue
            hist[row['horse_id']].append({
                'date': race.get('race_date'), 'venue': race.get('venue'),
                'distance': race.get('distance'), 'jockey': row.get('jockey'),
                'jockey_win_rate': row.get('jockey_win_rate'),
                'finish_position': row.get('finish_position'),
            })
    for v in hist.values():
        v.sort(key=lambda x: x['date'])

    prior_any = prior3 = prior_cd = prior_cd3 = 0
    for r in runners:
        race = r['_race']
        date = race.get('race_date')
        venue = race.get('venue')
        dist = race.get('distance')
        starts = [h for h in hist.get(r.get('horse_id'), []) if h['date'] < date]
        if starts:
            prior_any += 1
            if len(starts) >= 3:
                prior3 += 1
            same = [h for h in starts if h['venue'] == venue and h['distance'] == dist]
            if same:
                prior_cd += 1
                if len(same) >= 3:
                    prior_cd3 += 1
    n = len(runners)
    out['history'] = {
        'sample_runners': n,
        'runners_with_1_prior': {'n': prior_any, 'pct': pct(prior_any, n)},
        'runners_with_3_prior': {'n': prior3, 'pct': pct(prior3, n)},
        'runners_with_same_cd': {'n': prior_cd, 'pct': pct(prior_cd, n)},
        'runners_with_3_same_cd': {'n': prior_cd3, 'pct': pct(prior_cd3, n)},
        'total_history_starts': sum(len(v) for v in hist.values()),
        'jockey_per_start_pct': pct(sum(1 for v in hist.values() for h in v if h.get('jockey')),
                                    sum(len(v) for v in hist.values())),
    }

    # Jockey rate stability (leakage surface)
    rates = defaultdict(set)
    dates = defaultdict(list)
    for horse, rows in hist.items():
        for h in rows:
            j = h.get('jockey')
            if not j or h.get('jockey_win_rate') is None:
                continue
            rates[j].add(round(float(h['jockey_win_rate']), 4))
            dates[j].append(h['date'])
    elig = {j: (rates[j], dates[j]) for j in rates if len(dates[j]) >= 10}
    distinct = [len(v[0]) for v in elig.values()]
    out['jockey_rate_stability'] = {
        'jockeys_ge10_starts': len(elig),
        'jockeys_single_rate': sum(1 for d in distinct if d == 1),
        'distinct_rates_median': sorted(distinct)[len(distinct) // 2] if distinct else 0,
        'distinct_rates_max': max(distinct) if distinct else 0,
    }

    # Run-style mix among runners with parsable positions
    styles = Counter()
    for r in runners:
        raw = str(r.get('sectional_times') or '').strip()
        if not sec_re.match(raw):
            continue
        try:
            pos = [int(x) for x in raw.split('|')[1].split()]
        except Exception:
            continue
        if len(pos) < 2:
            continue
        first, last = pos[0], pos[-1]
        if first <= 2:
            styles['leader'] += 1
        elif first >= max(6, len(pos) + 1) or last < first - 2:
            styles['closer'] += 1
        else:
            styles['stalker'] += 1
    out['run_style_mix'] = dict(styles)

    path = os.path.join(os.path.dirname(__file__), '..', 'reports',
                        f"phase0_audit_{datetime.now().strftime('%Y-%m-%d')}.json")
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f'[OK] wrote {os.path.abspath(path)}')
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()