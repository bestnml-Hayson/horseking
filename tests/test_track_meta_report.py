import track_meta_report as T
from backfill_track_meta import needs_fill


def _race(race_id, date, venue, going, course):
    return {'race_id': race_id, 'race_date': date, 'venue': venue,
            'race_no': 1, 'distance': 1200, 'going': going,
            'track_course': course}


def _fixture():
    return [
        _race('A', '2026-11-01', 'ST', '好地', '草地'),
        _race('B', '2026-11-01', 'ST', '好地至快地', '草地'),
        _race('C', '2026-11-01', 'ST', '濕快地', '全天候跑道'),
        _race('D', '2026-11-02', 'HV', '黏地', '草地'),
        _race('E', '2026-11-02', 'HV', '名次', None),
        _race('F', '2026-11-03', 'HV', None, None),
    ]


def test_build_report_coverage_distribution_variation():
    report = T.build_report(_fixture())

    assert report['races'] == 6
    assert report['going'] == 4
    assert report['going_rate'] == 4 / 6
    assert report['track_course'] == 4
    assert report['track_course_rate'] == 4 / 6
    assert report['going_distinct'] == 4
    assert report['non_good_races'] == 3
    assert report['non_good_share'] == 3 / 4
    assert report['multi_surface_meetings'] == 1

    assert report['by_venue']['ST']['races'] == 3
    assert report['by_venue']['ST']['going'] == 3
    assert report['by_venue']['HV']['races'] == 3
    assert report['by_venue']['HV']['going'] == 1
    assert report['by_venue']['HV']['track_course'] == 1

    assert report['surface_going']['草地'] == {'好地': 1, '好地至快地': 1, '黏地': 1}
    assert report['surface_going']['全天候跑道'] == {'濕快地': 1}

    assert report['venue_variation']['ST']['distinct_going'] == 3
    assert report['venue_variation']['HV']['distinct_going'] == 1
    assert report['invalid_going'] == {'名次': 1}
    assert report['invalid_going_values'] == 1


def test_render_markdown_states_display_only_and_variation():
    report = T.build_report(_fixture())
    markdown = T.render_markdown(report, '2026-11-28')

    assert '唯讀描述性報表' in markdown
    assert '## 覆蓋率：場地' in markdown
    assert '## 覆蓋率：月份' in markdown
    assert '## going 分佈（按賽道）' in markdown
    assert '## 變異程度' in markdown
    assert '有變異' in markdown
    assert '維持 off' in markdown
    assert '無法解析的 going' in markdown


def test_no_variation_keeps_model_off():
    report = T.build_report([
        _race('A', '2026-11-01', 'ST', '好地', '草地'),
        _race('B', '2026-11-02', 'HV', '好地', '草地'),
    ])
    markdown = T.render_markdown(report, '2026-11-28')
    assert report['going_distinct'] == 1
    assert '幾乎無變異' in markdown


def test_needs_fill_only_for_missing_or_non_canonical():
    assert needs_fill({'going': None, 'track_course': None})
    assert needs_fill({'going': '名次', 'track_course': '草地'})
    assert needs_fill({'going': '好地', 'track_course': None})
    assert needs_fill({'going': 'Good', 'track_course': '草地'})
    assert not needs_fill({'going': '好地', 'track_course': '草地'})
    assert not needs_fill({'going': '好地至快地', 'track_course': '全天候跑道'})

class _Resp:
    status_code = 200

    def __init__(self, text):
        self.text = text


class _Client:
    def __init__(self, text):
        self._text = text

    def get(self, url):
        return _Resp(self._text)


def test_fetch_meta_validates_date_and_race_number():
    from backfill_track_meta import fetch_meta

    page = ('<html>賽事日期: 04/07/2026 第 6 場 (832) 第四班 - 1200米 '
            '場地狀況 : 濕快地 賽道 : 全天候跑道 - "A" 賽道</html>')
    race = {'race_date': '2026-07-04', 'venue': 'ST', 'race_no': 6}
    meta, reason = fetch_meta(_Client(page), race)
    assert reason is None
    assert meta == {'going': '濕快地', 'track_course': '全天候跑道'}

    wrong_date = {'race_date': '2026-07-05', 'venue': 'ST', 'race_no': 6}
    meta, reason = fetch_meta(_Client(page), wrong_date)
    assert meta is None and 'date mismatch' in reason

    wrong_race = {'race_date': '2026-07-04', 'venue': 'ST', 'race_no': 7}
    meta, reason = fetch_meta(_Client(page), wrong_race)
    assert meta is None and 'not on page' in reason
