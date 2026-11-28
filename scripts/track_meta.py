#!/usr/bin/env python3
"""Normalise going / track_course values from HKJC pages.

A results page states one going value per race (`場地狀況 : 好地`) and the
surface (`賽道 : 草地 - "B" 賽道`). The racecard can list both surfaces of a
mixed meeting, so normalisation picks a single canonical token and refuses
ambiguous multi-value blobs instead of guessing a surface.
"""
import re

# HKJC wording is 好地至快地 / 好地至黏地 (not 好至...); keep both as input.
GOING_TOKENS = (
    '好地至黏快地', '好地至快地', '好地至黏地', '好地至軟地',
    '濕快地', '濕慢地', '大爛地',
    '好地', '快地', '慢地', '軟地', '黏地', '爛地', '封地',
)
GOING_ALIASES = {
    '好至黏快地': '好地至黏快地',
    '好至快地': '好地至快地',
    '好至黏地': '好地至黏地',
    '好至軟地': '好地至軟地',
}
GOING_EN = {
    'GOOD': '好地',
    'GOOD TO FIRM': '好地至快地',
    'FIRM': '快地',
    'YIELDING': '黏地',
    'GOOD TO YIELDING': '好地至黏地',
    'SOFT': '軟地',
    'WET FAST': '濕快地',
    'WET SLOW': '濕慢地',
    'HEAVY': '大爛地',
    'SEALED': '封地',
}
TRACK_COURSE_TOKENS = ('全天候跑道', '草地')


def normalize_going(value):
    """'好地至快地' -> same; 'Good' -> '好地'; ambiguous/unknown -> None."""
    if value is None:
        return None
    text = str(value).strip().replace('　', ' ')
    if not text:
        return None
    en = GOING_EN.get(text.upper())
    if en:
        return en
    if text in GOING_ALIASES:
        return GOING_ALIASES[text]
    if text in GOING_TOKENS:
        return text

    # Mask each chosen token so sub-tokens (快地 inside 好地至快地) never
    # count twice. Two genuinely different goings -> ambiguous, return None.
    remaining = text
    tokens = []
    while True:
        best = None
        for token in sorted(GOING_TOKENS + tuple(GOING_ALIASES), key=len, reverse=True):
            index = remaining.find(token)
            if index >= 0 and (best is None or index < best[0]
                               or (index == best[0] and len(token) > len(best[1]))):
                best = (index, token)
        if best is None:
            break
        index, token = best
        tokens.append(GOING_ALIASES.get(token, token))
        remaining = remaining[:index] + ' ' * len(token) + remaining[index + len(token):]
    if len(tokens) == 1:
        return tokens[0]
    return None


def normalize_track_course(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if '全天候' in text or '泥' in text:
        return '全天候跑道'
    if '草地' in text:
        return '草地'
    return None


def extract_track_meta(text):
    """Pull going and track_course out of a results/racecard page text."""
    if not text:
        return {'going': None, 'track_course': None}
    going = None
    match = re.search(r'場地狀況\s*[:：]\s*([^\s<]+)', text)
    if match:
        going = normalize_going(match.group(1))
    course = None
    match = re.search(r'賽道\s*[:：]\s*(全天候跑道|草地|泥地)', text)
    if match:
        course = normalize_track_course(match.group(1))
    return {'going': going, 'track_course': course}