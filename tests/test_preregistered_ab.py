import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, 'docs', 'PREREGISTERED_AB.md')


def _text():
    with open(DOC, encoding='utf-8') as fh:
        return fh.read()


def test_preregistered_ab_exists_with_four_abs_in_priority_order():
    text = _text()
    headers = [
        '## 1. α 時間加權',
        '## 2. timing 融合',
        '## 3. odds_drift',
        '## 4. availability_gate',
    ]
    positions = [text.index(header) for header in headers]
    assert positions == sorted(positions)
    assert '已預先註冊，未執行' in text


def test_thresholds_and_sample_rules_are_frozen():
    text = _text()
    for phrase in (
            'honest_v586',
            'ΔNLL < 0',
            'CI **全負**',
            '≥4/5',
            '≥30 場',
            '≥300 runners',
            '50 場只夠整體結論',
            '不結論',
            '不得中途加指標或改門檻',
            '不得用 SP 補數當 pre-race 快照',
    ):
        assert phrase in text, phrase
    for metric in ('Top1', 'Top3', 'EV ROI'):
        assert metric in text


def test_governance_docs_exist():
    for name in ('FLAGS.md', 'RISKS.md',
                 os.path.join('reports', 'honest_vs_current_v586.md'),
                 os.path.join('docs', 'MONITORING.md')):
        assert os.path.exists(os.path.join(ROOT, name)), name