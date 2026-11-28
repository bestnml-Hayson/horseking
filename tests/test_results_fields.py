from results_fields import (
    parse_finish_position,
    parse_finish_time,
    parse_margin,
)


def test_finish_time_formats():
    assert parse_finish_time('1:09.45') == 69.45
    assert parse_finish_time('1.09.45') == 69.45
    assert parse_finish_time('0:56.78') == 56.78
    assert parse_finish_time('1：09.45') == 69.45
    assert parse_finish_time('69.49') == 69.49
    assert parse_finish_time(' 70 ') == 70.0


def test_finish_time_rejects_out_of_range_and_garbage():
    assert parse_finish_time(None) is None
    assert parse_finish_time('') is None
    assert parse_finish_time('abc') is None
    assert parse_finish_time('15.00') is None      # faster than any 1000m
    assert parse_finish_time('400') is None        # slower than any 2400m
    assert parse_finish_time('-') is None


def test_margin_tokens_english_and_chinese():
    assert parse_margin('N') == 0.05
    assert parse_margin('SH') == 0.1
    assert parse_margin('HD') == 0.2
    assert parse_margin('NK') == 0.3
    assert parse_margin('ML') == 10.0
    assert parse_margin('鼻位') == 0.05
    assert parse_margin('短頭') == 0.1
    assert parse_margin('頭位') == 0.2
    assert parse_margin('頸位') == 0.3
    assert parse_margin('多位') == 10.0
    assert parse_margin('大敗') == 10.0


def test_margin_numeric_and_fractions():
    assert parse_margin('1') == 1.0
    assert parse_margin('1.5') == 1.5
    assert parse_margin('1/2') == 0.5
    assert parse_margin('1-1/2') == 1.5
    assert parse_margin('1-1/4') == 1.25
    assert parse_margin('1 1/2') == 1.5
    assert parse_margin('0') == 0.0


def test_margin_winner_dash_and_invalid():
    assert parse_margin('-', finish_position=1) == 0.0
    assert parse_margin('---', finish_position=1) == 0.0
    assert parse_margin('-', finish_position=2) is None
    assert parse_margin(None) is None
    assert parse_margin('') is None
    assert parse_margin('x') is None
    assert parse_margin('31') == 31.0         # tail-enders can exceed 30L
    assert parse_margin('100') is None        # beyond any plausible margin
    assert parse_margin('1/0') is None


def test_finish_position():
    assert parse_finish_position('1') == 1
    assert parse_finish_position(' 12 ') == 12
    assert parse_finish_position('3 DH') == 3
    assert parse_finish_position('0') is None
    assert parse_finish_position('WV') is None
    assert parse_finish_position(None) is None