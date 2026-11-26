"""Run-style classification from HKJC 沿途走位 — mirror of lib/race-utils.ts.

race_runners.sectional_times stores the results-page running positions as
"場頭數|4 4 4 1"; the field-size prefix is needed to read the early call as a
ratio. HKJC publishes no per-horse sectional times for this instance, so the
column had no other use.
"""
import re
from typing import Dict, List, Optional, Tuple

STYLE_LABELS = {'leader': '領放', 'stalker': '跟前', 'closer': '後上'}


def parse_positions(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    return [int(n) for n in re.findall(r'\d{1,2}', str(raw)) if 1 <= int(n) <= 30]


def parse_running_positions(raw: Optional[str]) -> Tuple[List[int], Optional[int]]:
    if not raw:
        return [], None
    text = str(raw)
    field_size = None
    if '|' in text:
        head, _, body = text.partition('|')
        try:
            field_size = int(head) or None
        except ValueError:
            field_size = None
    else:
        body = text
    return parse_positions(body), field_size


def encode_running_positions(field_size: Optional[int], raw: Optional[str]) -> Optional[str]:
    positions = parse_positions(raw)
    if len(positions) < 2:
        return None
    prefix = str(int(field_size)) if field_size and field_size > 0 else ''
    return f"{prefix}|{' '.join(str(p) for p in positions)}"


def classify_run_style(positions: List[int], field_size: Optional[int] = None) -> Optional[str]:
    """First call decides leader vs pack; ground made decides closer vs stalker."""
    if len(positions) < 2:
        return None
    field = field_size if field_size and field_size > 1 else max(12, max(positions))
    first, last = positions[0], positions[-1]
    rel = first / max(field, 2)
    gained = first - last
    if rel <= 0.34:
        return 'leader'
    if rel >= 0.5 and (gained >= 2 or (last <= 3 and gained >= 1)):
        return 'closer'
    return 'stalker'


def recent_run_styles(history: Optional[List[Dict]], limit: int = 6) -> List[Dict]:
    """history is newest-first, as returned by _fetch_horse_history."""
    out: List[Dict] = []
    for h in history or []:
        if len(out) >= limit:
            break
        positions, field = parse_running_positions(
            h.get('running_positions') or h.get('sectional_times')
        )
        style = classify_run_style(positions, field)
        if not style:
            continue
        out.append({
            'race_date': h.get('race_date', ''),
            'positions': positions,
            'field_size': field,
            'style': style,
        })
    return out


def dominant_run_style(styles: List[Dict]) -> Tuple[Optional[str], Dict[str, int]]:
    counts = {'leader': 0, 'stalker': 0, 'closer': 0}
    for s in styles:
        counts[s['style']] += 1
    if len(styles) < 2:
        return None, counts
    ranked = sorted(counts, key=lambda k: -counts[k])
    if counts[ranked[0]] == counts[ranked[1]]:
        return None, counts
    return ranked[0], counts