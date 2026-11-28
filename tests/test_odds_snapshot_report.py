from datetime import date, datetime
from zoneinfo import ZoneInfo

import odds_snapshot_report as R

HKT = ZoneInfo('Asia/Hong_Kong')
RACE = {'race_id': 'ST-20261202-01', 'race_no': 1, 'venue': 'ST',
        'race_date': '2026-12-02', 'race_time': '16:00'}


def _row(horse_id, bucket, hhmm):
    hour, minute = hhmm
    ts = datetime(2026, 12, 2, hour, minute, tzinfo=HKT)
    return {'race_id': RACE['race_id'], 'horse_id': horse_id,
            'odds': 3.0, 'available_at': ts.isoformat(),
            'source': 'pre-race', 'snapshot_type': bucket}


def test_build_report_marks_complete_race_and_missing_bucket():
    rows = [
        _row('h1', 'open', (14, 0)),
        _row('h1', '60m', (15, 20)),
        _row('h1', '15m', (15, 50)),
        _row('h1', 'close', (15, 57)),
        _row('h2', 'open', (14, 0)),
        _row('h2', '60m', (15, 20)),
        _row('h2', '15m', (15, 50)),
    ]
    report = R.build_report(
        rows, {RACE['race_id']: RACE}, {RACE['race_id']: {'h1', 'h2'}})
    complete = report['races'][0]
    assert complete['complete'] is True
    assert complete['coverage'] == 1.0
    assert complete['available_at_complete_rate'] == 1.0
    assert complete['odds_nonnull_rate'] == 1.0
    assert complete['bucket_offset_sec'] == {'avg': 0.0, 'max': 0.0}
    assert complete['n_runners'] == 2
    assert complete['n_horses_with_4_buckets'] == 1
    assert complete['race_date'] == '2026-12-02'
    assert complete['missing_reason'] == ''

    incomplete_rows = [r for r in rows if r['snapshot_type'] != 'close']
    report = R.build_report(
        incomplete_rows, {RACE['race_id']: RACE}, {RACE['race_id']: {'h1', 'h2'}})
    incomplete = report['races'][0]
    assert incomplete['complete'] is False
    assert incomplete['missing'] == ['close']
    assert incomplete['n_horses_with_4_buckets'] == 0
    assert '缺 bucket: close' in incomplete['missing_reason']
    assert any('缺 bucket: close' in reason for reason in incomplete['reasons'])


def test_invalid_price_or_capture_time_never_counts_as_a_bucket():
    rows = [_row('h1', b, hhmm) for b, hhmm in
            (('open', (14, 0)), ('60m', (15, 20)), ('15m', (15, 50)))]
    bad_close = dict(_row('h1', 'close', (15, 57)), odds=0.0)
    rows.append(bad_close)
    report = R.build_report(
        rows, {RACE['race_id']: RACE}, {RACE['race_id']: {'h1'}})
    race = report['races'][0]
    assert race['complete'] is False
    assert race['missing'] == ['close']
    assert race['odds_nonnull_rate'] == 0.75
    assert '1 行賠率無效' in race['missing_reason']


def test_build_report_groups_by_venue_and_field_band():
    race_big = dict(RACE, race_id='ST-20261202-02', race_no=2)
    rows = [
        _row('h1', 'open', (14, 0)),
        dict(_row('h1', '60m', (15, 20)), race_id=race_big['race_id']),
    ]
    report = R.build_report(
        rows,
        {RACE['race_id']: RACE, race_big['race_id']: race_big},
        {RACE['race_id']: {f'h{i}' for i in range(10)},
         race_big['race_id']: {f'h{i}' for i in range(15)}})
    bands = {(g['venue'], g['band']): g for g in report['summary']}
    assert ('ST', '≤10') in bands
    assert ('ST', '15+') in bands
    assert bands[('ST', '15+')]['races'] == 1


def test_render_markdown_contains_gate_columns_and_reasons():
    rows = [_row('h1', 'open', (14, 0))]
    report = R.build_report(
        rows, {RACE['race_id']: RACE}, {RACE['race_id']: {'h1', 'h2'}})
    md = R.render_markdown(
        report,
        {'complete_pre_race_races': 0, 'total_races': 1, 'target': 50, 'store': 'pipeline_status'},
        'pipeline_status', '2026-11-28')
    assert '0/50' in md
    for column in ('race_id', 'race_date', 'venue', 'n_runners',
                   'n_horses_with_4_buckets', 'odds_nonnull_rate',
                   'available_at_complete_rate', 'bucket_offset_sec',
                   'missing_reason'):
        assert column in md
    assert '缺 bucket: 60m/15m/close' in md
    assert '1 匹無快照' in md
    assert 'partial 一律不當完整' in md


def test_build_weekly_flags_chronic_bucket_and_venue_split():
    races = []
    for i, venue in enumerate(('ST', 'ST', 'HV')):
        race_id = f'{venue}-2026120{i + 1}-01'
        rows = [_row('h1', 'open', (14, 0)),
                _row('h1', '60m', (15, 20)),
                _row('h1', '15m', (15, 50))]
        for row in rows:
            row['race_id'] = race_id
        meta = {'race_id': race_id, 'venue': venue, 'race_date': '2026-12-0' + str(i + 1),
                'race_time': '16:00'}
        report = R.build_report(rows, {race_id: meta}, {race_id: {'h1'}})
        races.extend(report['races'])
    weekly = R.build_weekly({'races': races}, days=7, today=date(2026, 12, 3))
    assert weekly['races'] == 3
    assert weekly['complete'] == 0
    assert weekly['bucket_missing']['close'] == 3
    assert weekly['chronic'] == ['close']
    assert set(weekly['venues']) == {'HV', 'ST'}
    assert weekly['venues']['ST']['races'] == 2

    md = R.render_weekly_markdown(
        weekly,
        {'complete_pre_race_races': 0, 'total_races': 3, 'target': 50},
        '2026-12-03')
    assert '長期缺 close' in md
    assert '放寬 bucket 定義' in md
    assert 'partial 一律唔當完整' in md