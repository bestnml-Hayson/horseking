#!/usr/bin/env python3
"""Normalise HKJC results fields shared by every importer.

finish_time is stored as seconds (float) in race_runners; margin is stored as
lengths (float). Anything outside the sanity windows returns None instead of a
guess, so a bad scrape never becomes a fake time.
"""
import re

FINISH_TIME_MIN = 30.0   # 1000m races run ~55s; anything faster is a parse error
FINISH_TIME_MAX = 300.0  # 2400m races run ~150s; allow slow going
MARGIN_MAX = 99.0        # tail-enders can be 30L+; above this is a parse error
MARGIN_OUTLIER = 30.0    # stored but flagged in the quality report (tail-enders)
MARGIN_TOKENS = {
    'N': 0.05,   # nose
    'SH': 0.1,   # short head
    'HD': 0.2,   # head
    'NK': 0.3,   # neck
    'ML': 10.0,  # many lengths (lower bound convention)
    '鼻位': 0.05,
    '短頭': 0.1,
    '頭位': 0.2,
    '頸位': 0.3,
    '多位': 10.0,
    '大敗': 10.0,
}


def parse_finish_time(value):
    """'1:09.45', '1.09.45', '0:56.78', '69.45' -> seconds; invalid -> None."""
    if value is None:
        return None
    text = str(value).strip().replace('：', ':')
    if not text:
        return None
    try:
        if re.fullmatch(r'\d{1,2}[:.]\d{1,2}[:.]\d{1,2}', text):
            # HKJC sometimes prints 1.39.85 with dots as separators.
            minutes, seconds, hundredths = re.split(r'[:.]', text)
            total = int(minutes) * 60 + int(seconds) + int(hundredths) / 100
        elif ':' in text:
            minutes, seconds = text.split(':', 1)
            total = int(minutes) * 60 + float(seconds)
        else:
            total = float(text)
    except (TypeError, ValueError):
        return None
    if not FINISH_TIME_MIN <= total <= FINISH_TIME_MAX:
        return None
    return round(total, 2)


def parse_margin(value, finish_position=None):
    """'1-1/2', '1/2', 'SH', 'ML', '-' -> lengths; invalid -> None."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in ('', '---', '-', '—', '–'):
        return 0.0 if finish_position == 1 else None
    if text in MARGIN_TOKENS:
        return MARGIN_TOKENS[text]
    fraction = re.fullmatch(r'(\d+)[-\s]+(\d+)/(\d+)', text)
    if fraction:
        whole, numerator, denominator = (int(x) for x in fraction.groups())
        if denominator == 0:
            return None
        total = whole + numerator / denominator
    else:
        fraction = re.fullmatch(r'(\d+)/(\d+)', text)
        if fraction:
            numerator, denominator = (int(x) for x in fraction.groups())
            if denominator == 0:
                return None
            total = numerator / denominator
        else:
            try:
                total = float(text)
            except (TypeError, ValueError):
                return None
    if not 0 <= total <= MARGIN_MAX:
        return None
    return round(total, 2)


def parse_finish_position(value):
    if value is None:
        return None
    match = re.match(r'\s*(\d+)', str(value))
    if not match:
        return None
    position = int(match.group(1))
    return position or None