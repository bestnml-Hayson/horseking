from track_meta import extract_track_meta, normalize_going, normalize_track_course


def test_going_canonical_alias_and_english():
    assert normalize_going('好地') == '好地'
    assert normalize_going('好地至快地') == '好地至快地'
    assert normalize_going('好地至黏地') == '好地至黏地'
    assert normalize_going('好至快地') == '好地至快地'
    assert normalize_going('好至黏地') == '好地至黏地'
    assert normalize_going('濕快地') == '濕快地'
    assert normalize_going('濕慢地') == '濕慢地'
    assert normalize_going('大爛地') == '大爛地'
    assert normalize_going('封地') == '封地'
    assert normalize_going('Sealed') == '封地'
    assert normalize_going('Good') == '好地'
    assert normalize_going('Good to Firm') == '好地至快地'
    assert normalize_going('Wet Slow') == '濕慢地'


def test_going_single_token_inside_text_is_recovered():
    assert normalize_going('賽後場地狀況為好地。') == '好地'
    assert normalize_going('大爛地（泥地）') == '大爛地'


def test_going_ambiguous_or_invalid_returns_none():
    assert normalize_going('好地及濕慢地') is None
    assert normalize_going('名次') is None
    assert normalize_going('') is None
    assert normalize_going(None) is None


def test_track_course_normalisation():
    assert normalize_track_course('草地 - "B" 賽道') == '草地'
    assert normalize_track_course('草地') == '草地'
    assert normalize_track_course('全天候跑道') == '全天候跑道'
    assert normalize_track_course('泥地') == '全天候跑道'
    assert normalize_track_course('') is None
    assert normalize_track_course(None) is None


def test_extract_track_meta_from_results_text():
    text = ('第 6 場 (832) 第四班 - 1200米 - (60-40) 場地狀況 : 濕快地 '
            '賽道 : 全天候跑道 - "A" 賽道')
    assert extract_track_meta(text) == {'going': '濕快地', 'track_course': '全天候跑道'}

    text = '場地狀況 : 好地至快地 賽道 : 草地 - "C+3" 賽道'
    assert extract_track_meta(text) == {'going': '好地至快地', 'track_course': '草地'}

    assert extract_track_meta('') == {'going': None, 'track_course': None}