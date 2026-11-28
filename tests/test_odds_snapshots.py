from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import odds_snapshots as O

HKT = ZoneInfo('Asia/Hong_Kong')


class _Resp:
    def __init__(self, data=None):
        self.data = data or []


class _Table:
    def __init__(self, name, sb):
        self.name = name
        self.sb = sb
        self.action = None
        self.rows = None

    def select(self, *args, **kwargs):
        self.action = 'select'
        return self

    def eq(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def range(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def upsert(self, rows, **kwargs):
        self.action = 'upsert'
        self.rows = rows
        self.upsert_kwargs = kwargs
        return self

    def execute(self):
        if self.name == 'odds_snapshots' and self.sb.fail_table:
            raise RuntimeError('relation "odds_snapshots" does not exist')
        if self.action == 'select':
            if self.name == 'pipeline_status' and self.sb.state is not None:
                return _Resp([{'status_json': self.sb.state}])
            return _Resp([])
        if self.name == 'pipeline_status':
            self.sb.state = self.rows['status_json']
        self.sb.writes.append((self.name, self.rows, getattr(self, 'upsert_kwargs', {})))
        return _Resp([])


class _SB:
    def __init__(self, fail_table=True):
        self.fail_table = fail_table
        self.writes = []
        self.state = None

    def table(self, name):
        return _Table(name, self)


def _race():
    return {'race_id': 'ST-20261202-01', 'race_date': '2026-12-02',
            'race_time': '16:00'}


def test_snapshot_bucket_edges():
    assert O.snapshot_bucket(None) == 'open'
    assert O.snapshot_bucket(61) == 'open'
    assert O.snapshot_bucket(60) == '60m'
    assert O.snapshot_bucket(16) == '60m'
    assert O.snapshot_bucket(15) == '15m'
    assert O.snapshot_bucket(6) == '15m'
    assert O.snapshot_bucket(5) == 'close'
    assert O.snapshot_bucket(-3) == 'close'


def test_minutes_to_post_uses_hkt_race_time():
    now = datetime(2026, 12, 2, 15, 0, tzinfo=HKT)
    race = {'race_date': '2026-12-02', 'race_time': '16:00'}
    assert O.minutes_to_post(race, now) == pytest.approx(60.0)
    assert O.minutes_to_post({'race_date': '2026-12-02'}, now) is None
    assert O.minutes_to_post({'race_time': '16:00'}, now) is None


def test_build_snapshot_rows_filters_and_rounds():
    now = datetime(2026, 12, 2, 15, 30, tzinfo=HKT)
    rows = O.build_snapshot_rows(
        'ST-20261202-01', {1: 'h1', 2: 'h2', 3: None},
        {1: 3.456, 2: None, 3: 4.0, 4: 5.0, 'x': 2.0}, '60m', now)
    assert len(rows) == 1
    row = rows[0]
    assert row['horse_id'] == 'h1'
    assert row['odds'] == pytest.approx(3.46)
    assert row['source'] == 'pre-race'
    assert row['snapshot_type'] == '60m'
    assert row['available_at'] == now.isoformat()


def test_record_falls_back_to_pipeline_status_and_dedupes():
    O.reset_table_cache()
    sb = _SB(fail_table=True)
    now = datetime(2026, 12, 2, 15, 30, tzinfo=HKT)
    race = _race()
    written, store = O.record_pre_race_snapshots(
        sb, race, {1: 3.0, 2: 0.0}, {1: 'h1', 2: 'h2'}, now=now)
    assert (written, store) == (1, 'pipeline_status')
    status = sb.writes[-1][1]
    entry = status['status_json']['races']['ST-20261202-01']
    row = next(iter(entry['rows'].values()))
    assert row['horse_id'] == 'h1'
    assert row['snapshot_type'] == '60m'
    assert row['available_at'] == now.isoformat()
    assert row['source'] == 'pre-race'
    assert entry['buckets'] == ['60m']

    written, store = O.record_pre_race_snapshots(
        sb, race, {1: 3.4}, {1: 'h1'}, now=now)
    assert (written, store) == (0, 'pipeline_status')


def test_record_keeps_each_distinct_capture_time():
    O.reset_table_cache()
    sb = _SB(fail_table=True)
    now = datetime(2026, 12, 2, 15, 30, tzinfo=HKT)
    race = _race()
    O.record_pre_race_snapshots(sb, race, {1: 3.0}, {1: 'h1'}, now=now)
    written, store = O.record_pre_race_snapshots(
        sb, race, {1: 3.2}, {1: 'h1'}, now=now.replace(minute=31))
    assert (written, store) == (1, 'pipeline_status')
    entry = sb.writes[-1][1]['status_json']['races']['ST-20261202-01']
    assert len(entry['rows']) == 2
    keys = list(entry['rows'])
    assert all(k.startswith('h1|60m|') for k in keys)


def test_fallback_prunes_older_than_retention():
    assert O.KEEP_DAYS >= 120
    O.reset_table_cache()
    sb = _SB(fail_table=True)
    sb.state = {'races': {'OLD': {'race_date': '2025-01-01', 'rows': {}}}}
    now = datetime(2026, 12, 2, 15, 30, tzinfo=HKT)
    O.record_pre_race_snapshots(sb, _race(), {1: 3.0}, {1: 'h1'}, now=now)
    races = sb.writes[-1][1]['status_json']['races']
    assert 'OLD' not in races
    assert 'ST-20261202-01' in races


def test_record_uses_table_when_available():
    O.reset_table_cache()
    sb = _SB(fail_table=False)
    now = datetime(2026, 12, 2, 16, 2, tzinfo=HKT)
    written, store = O.record_pre_race_snapshots(
        sb, _race(), {1: 3.0}, {1: 'h1'}, now=now)
    assert (written, store) == (1, 'table')
    name, rows, kwargs = sb.writes[-1]
    assert name == 'odds_snapshots'
    assert rows[0]['snapshot_type'] == 'close'
    assert kwargs.get('on_conflict') == 'race_id,horse_id,snapshot_type,available_at'
    O.reset_table_cache()


def test_table_writer_is_idempotent_for_same_capture():
    O.reset_table_cache()
    sb = _SB(fail_table=False)
    now = datetime(2026, 12, 2, 16, 2, tzinfo=HKT)
    O.record_pre_race_snapshots(sb, _race(), {1: 3.0}, {1: 'h1'}, now=now)
    first = sb.writes[-1][1]
    O.record_pre_race_snapshots(sb, _race(), {1: 3.0}, {1: 'h1'}, now=now)
    second = sb.writes[-1][1]
    assert first == second
    O.reset_table_cache()


def _state_with_buckets(buckets):
    rows = {f"h1|{b}|2026-12-02T15:00:00+08:00": {'snapshot_type': b}
            for b in buckets}
    return {'races': {'ST-20261202-01': {'race_date': '2026-12-02', 'rows': rows}}}


def test_progress_counts_only_four_bucket_races():
    O.reset_table_cache()
    sb = _SB(fail_table=True)
    sb.state = _state_with_buckets(['open', '60m', '15m', 'close'])
    assert O.snapshot_progress(sb)['complete_pre_race_races'] == 1

    sb.state = _state_with_buckets(['open', '60m', '15m'])
    progress = O.snapshot_progress(sb)
    assert progress['complete_pre_race_races'] == 0
    assert progress['total_races'] == 1


def test_log_progress_prints_and_persists():
    O.reset_table_cache()
    sb = _SB(fail_table=True)
    sb.state = _state_with_buckets(['open', '60m', '15m', 'close'])
    lines = []
    progress = O.log_progress(sb, out=lines.append)
    assert progress['complete_pre_race_races'] == 1
    assert lines and 'complete_pre_race_races = 1/50' in lines[0]
    name, rows, _ = sb.writes[-1]
    assert name == 'pipeline_status'
    assert rows['id'] == 'odds_snapshot_progress'
    assert rows['status_json']['complete_pre_race_races'] == 1
    assert rows['status_json']['target'] == 50