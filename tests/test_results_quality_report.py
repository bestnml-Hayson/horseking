import results_quality_report as R


def _runner(race_id, horse_no, pos, time=None, margin=None):
    return {'race_id': race_id, 'horse_no': horse_no,
            'finish_position': pos, 'finish_time': time, 'margin': margin}


def _race(race_id, date='2026-11-01', venue='ST', distance=1200,
          class_level='第四班', track_course='A'):
    return {'race_id': race_id, 'race_date': date, 'venue': venue,
            'distance': distance, 'class_level': class_level,
            'track_course': track_course}


def test_build_quality_coverage_groups_and_missing_months():
    races = [_race('A', venue='ST', distance=1200, class_level='第四班'),
             _race('B', date='2026-09-01', venue='HV', distance=1650,
                   class_level='第三班', track_course=None)]
    runners = [
        _runner('A', 1, 1, 69.5, 0.0),
        _runner('A', 2, 2, 70.0, 0.5),
        _runner('A', 3, 3, 70.4, 1.0),
        _runner('A', 4, 4, 71.0, 2.0),
        _runner('A', 5, 5, 72.0, 3.0),
        _runner('B', 1, 1, None, 0.0),
        _runner('B', 2, 2, 101.0, 0.5),
        _runner('B', 3, 3, None, 31.0),
        _runner('B', 4, 4, None, None),
        _runner('B', 5, None, 99.0, None),   # unplaced/withdrawn: excluded
    ]
    quality = R.build_quality(races, runners)

    assert quality['races'] == 2
    assert quality['runners'] == 9
    assert quality['overall']['finish_time'] == 6
    assert quality['overall']['finish_time_rate'] == 6 / 9
    assert quality['overall']['margin'] == 8
    assert quality['by_venue']['ST']['finish_time_rate'] == 1.0
    assert quality['by_venue']['HV']['finish_time_rate'] == 1 / 4
    assert quality['by_distance'][1650]['runners'] == 4
    assert quality['by_class']['第三班']['runners'] == 4
    assert quality['by_month']['2026-09']['finish_time_rate'] == 0.25
    assert any('2026-09' in reason for reason in quality['reasons'])

    # margin=31 is out of range; winner margin=0 is not an anomaly.
    assert len(quality['issues']) == 1
    assert quality['issues'][0]['field'] == 'margin'
    assert quality['winner_margin_positive'] == []


def test_build_quality_low_month_reason_and_winner_checks():
    races = [_race('C', date='2026-09-01', venue='HV'),
             _race('D', date='2026-09-02', venue='ST'),
             _race('E', date='2026-10-01', venue='ST')]
    runners = [
        # winner slower than a rival -> winner_not_fastest
        _runner('C', 1, 1, 101.5, 0.0),
        _runner('C', 2, 2, 101.0, 0.5),
        _runner('C', 3, 3, 101.8, 1.0),
        # healthy race, but winner margin > 0
        _runner('D', 1, 1, 70.0, 1.5),
        _runner('D', 2, 2, 70.2, 2.0),
        # no times at all -> low coverage month
        _runner('E', 1, 1, None, 0.0),
        _runner('E', 2, 2, None, 1.0),
    ]
    quality = R.build_quality(races, runners)

    assert quality['by_month']['2026-09']['finish_time_rate'] == 1.0
    assert quality['by_month']['2026-10']['finish_time_rate'] == 0.0
    assert any('2026-10' in reason and '重抓' in reason
               for reason in quality['reasons'])
    assert [r['race_id'] for r in quality['winner_margin_positive']] == ['D']
    assert [r['race_id'] for r in quality['winner_not_fastest']] == ['C']


def test_build_speed_baseline_groups_and_sufficiency():
    races, runners = [], []
    for i in range(5):
        rid = f'R{i}'
        races.append(_race(rid, venue='ST', distance=1200, track_course='A'))
        base = 69.5 + i * 0.2
        runners += [
            _runner(rid, 1, 1, round(base, 2), 0.0),
            _runner(rid, 2, 2, round(base + 0.3, 2), 0.5),
            _runner(rid, 3, 3, round(base + 0.6, 2), 1.0),
            _runner(rid, 4, 4, round(base + 0.9, 2), 1.5),
        ]
    # A group with only 4 races and one race short of 4 timed finishers.
    for i in range(4):
        rid = f'H{i}'
        races.append(_race(rid, venue='HV', distance=1650, track_course=None))
        runners += [
            _runner(rid, 1, 1, 101.0, 0.0),
            _runner(rid, 2, 2, 101.5, 0.5),
            _runner(rid, 3, 3, 102.0, 1.0),
            _runner(rid, 4, 4, None if i == 0 else 102.5, None),
        ]
    # Races with unknown distance must never enter a baseline group.
    races.append(_race('X', venue='HV', distance=None))
    runners += [_runner('X', i, i, 90.0 + i, float(i)) for i in range(1, 5)]

    baseline = R.build_speed_baseline(races, runners, min_races=5)
    by_key = {(g['venue'], g['distance'], g['track_course']): g for g in baseline}
    assert all(key[1] is not None for key in by_key)

    st = by_key[('ST', 1200, 'A')]
    assert st['races'] == 5
    assert st['sufficient'] is True
    assert st['winner_mean'] == 69.9
    assert st['winner_min'] == 69.5
    assert st['winner_max'] == 70.3

    hv = by_key[('HV', 1650, '未分類')]
    assert hv['races'] == 3      # one of the four races has only 3 timed finishers
    assert hv['sufficient'] is False


def test_render_markdown_contains_required_sections(tmp_path):
    races = [_race('A')]
    runners = [
        _runner('A', 1, 1, 69.5, 0.0),
        _runner('A', 2, 2, 70.0, 0.5),
        _runner('A', 3, 3, 70.4, 1.0),
        _runner('A', 4, 4, 71.0, 2.0),
    ]
    quality = R.build_quality(races, runners)
    baseline = R.build_speed_baseline(races, runners, min_races=5)
    markdown = R.render_markdown(quality, baseline, '2026-11-28')

    assert '賽果數據品質' in markdown
    assert '## 覆蓋率：場地' in markdown
    assert '## 覆蓋率：途程' in markdown
    assert '## 覆蓋率：班次' in markdown
    assert '## 品質檢查' in markdown
    assert '## 締速基準' in markdown
    assert '否（不結論）' in markdown
    assert '`speed_engine`' in markdown and '`finish_time_margin`' in markdown