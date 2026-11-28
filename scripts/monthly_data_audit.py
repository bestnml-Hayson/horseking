#!/usr/bin/env python3
"""Monthly collection audit (Line 1 monitoring, read-only).

Checks, once a month:
  * the X/50 complete-snapshot gate and partial/missing distribution,
  * the fallback JSON size (raw + gzip) against compression thresholds,
  * availability_gate shadow trigger counts (sparse vs covered) and draw_v2
    identity drift,
  * the DDL/escalation clock: after three months without the odds_snapshots
    table, the report states the IPv4-staging vs third-party-storage choice.

It never writes predictions or flags; it only writes a markdown audit file and
prints it. Update RISKS.md from its output.
"""
import gzip
import json
import os
import sys
from datetime import date, datetime
from statistics import mean
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase
import odds_snapshots as O
import shadow_predictions as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTION_START = date(2026, 11, 28)
FALLBACK_WARN_BYTES = 512 * 1024
FALLBACK_CRIT_BYTES = 2 * 1024 * 1024
MIGRATION_PATH = os.path.join(ROOT, 'migrations', 'add_odds_snapshots.sql')


def months_since(start, today):
    months = (today.year - start.year) * 12 + today.month - start.month
    if today.day < start.day:
        months -= 1
    return max(0, months)


def summarize_shadow(state):
    """availability_gate trigger counts plus draw_v2 identity drift."""
    races = (state or {}).get('races') or {}
    sparse = covered = 0
    sparse_coverages = []
    draw_max = 0.0
    aware_diffs = []
    for record in races.values():
        shadow = record.get('shadow') or {}
        gate_meta = (shadow.get('availability_gate') or {}).get('meta') or {}
        if gate_meta.get('gate') == 'sparse':
            sparse += 1
            sparse_coverages.append(float(gate_meta.get('coverage') or 0.0))
        elif gate_meta.get('gate') == 'covered':
            covered += 1
        live = record.get('live') or {}
        draw = (shadow.get('draw_v2') or {}).get('runners') or {}
        for rid, row in draw.items():
            if rid in live:
                draw_max = max(draw_max, abs(
                    float(row.get('p_final', 0)) - float(live[rid].get('p_final', 0))))
        aware = (shadow.get('avail_aware') or {}).get('runners') or {}
        for rid, row in aware.items():
            if rid in live:
                aware_diffs.append(abs(
                    float(row.get('p_final', 0)) - float(live[rid].get('p_final', 0))))
    return {
        'races': len(races),
        'gate_sparse': sparse,
        'gate_covered': covered,
        'sparse_coverages': sparse_coverages,
        'draw_identity_max_diff': draw_max,
        'avail_aware_mean_abs_diff': mean(aware_diffs) if aware_diffs else None,
        'no_variance': bool(races) and sparse == 0,
        'all_sparse_unpriced': bool(sparse_coverages) and all(c == 0 for c in sparse_coverages),
    }


def fallback_sizes(state):
    raw = json.dumps(state or {}, ensure_ascii=False).encode('utf-8')
    return {'raw_bytes': len(raw), 'gzip_bytes': len(gzip.compress(raw)) if raw else 0}


def compression_advice(raw_bytes):
    if raw_bytes >= FALLBACK_CRIT_BYTES:
        return ('超過 2 MB：立即 gzip 歸檔並只保留 index，同時啟動 escalation 二選一。')
    if raw_bytes >= FALLBACK_WARN_BYTES:
        return '超過 512 KB：安排壓縮／歸檔，唔可以無限期靠 JSON。'
    return '低於 512 KB：可繼續，按月重檢。'


def escalation_status(table_ready, months):
    if table_ready:
        return 'DB 表可用：維持正常收集，fallback 只作後備。'
    if months >= 3:
        return ('已滿 3 個月仍未套用 migration：提出二選一——'
                '(a) 換可連 DB 的 staging IPv4 環境收集並定期 sync，'
                '或 (b) 第三方 storage 寫快照、pipeline_status 只存 index。')
    return f'fallback 收集第 {months + 1} 個月（未滿 3 個月）：繼續觀察，按月重檢。'


def _latest_report(supabase, report_id):
    try:
        resp = supabase.table('pipeline_status').select('status_json') \
            .eq('id', report_id).execute()
        rows = resp.data or []
        return (rows[0].get('status_json') or {}) if rows else None
    except Exception:
        return None


def build_audit(supabase, today=None):
    today = today or datetime.now(HKT).date()
    progress = O.snapshot_progress(supabase)
    table_ready = O._table_ready(supabase)
    state = None if table_ready else O._load_state(supabase)
    shadow_state = S._load_state(supabase)
    months = months_since(COLLECTION_START, today)
    return {
        'generated': today.isoformat(),
        'progress': progress,
        'table_ready': table_ready,
        'fallback': fallback_sizes(state) if state is not None else None,
        'shadow': summarize_shadow(shadow_state),
        'migration_present': os.path.exists(MIGRATION_PATH),
        'months_elapsed': months,
        'escalation': escalation_status(table_ready, months),
        'daily_report': _latest_report(supabase, 'odds_snapshot_report'),
        'weekly_report': _latest_report(supabase, 'odds_snapshot_weekly_report'),
    }


def _kb(value):
    return 'n/a' if value is None else f'{value / 1024:.1f} KB'


def render_monthly_markdown(audit):
    p = audit['progress']
    missing = ', '.join(f'{k}: {v}' for k, v in sorted(p['missing_reason_counts'].items()))
    shadow = audit['shadow']
    lines = [
        f'# 數據收集月度審計（{audit["generated"]}）',
        '',
        '唯讀報表：不寫入任何預測、flag 或預設。',
        '',
        '## 1. 收集進度',
        '',
        f'- complete_pre_race_races = **{p["complete_pre_race_races"]}/{p["target"]}**；'
        f'partial = {p["partial_races"]}；總追蹤 = {p["total_races"]}。',
        f'- 儲存：`{p["store"]}`；migration 檔存在：'
        f'{"是" if audit["migration_present"] else "否"}；DB 表可用：'
        f'{"是" if audit["table_ready"] else "否"}。',
        f'- missing_reason 分佈：{missing or "無"}。',
        '',
        '## 2. Fallback 體積',
        '',
    ]
    if audit['fallback'] is None:
        lines.append('- 使用 DB 表，無 fallback JSON。')
    else:
        raw = audit['fallback']['raw_bytes']
        lines += [
            f'- 原始：{_kb(raw)}；gzip 後：{_kb(audit["fallback"]["gzip_bytes"])}。',
            f'- 處置：{compression_advice(raw)}',
        ]
    lines += [
        '',
        '## 3. availability_gate / draw_v2 shadow 審計',
        '',
        f'- shadow 賽事：{shadow["races"]}；gate sparse：{shadow["gate_sparse"]}；'
        f'covered：{shadow["gate_covered"]}。',
        f'- draw_v2 identity 最大差異：{shadow["draw_identity_max_diff"]:.5f}'
        '（預期 0；draw_v2 本身已是 live 預設，shadow 只作身份檢查）。',
    ]
    aware = shadow['avail_aware_mean_abs_diff']
    lines.append(
        f'- avail_aware 平均 |Δp_final|：{"n/a" if aware is None else f"{aware:.5f}"}'
        '（未採納，只累積證據）。')
    if shadow['no_variance']:
        lines.append('- **shadow 無變異：歷史 SP 覆蓋仍≈100%，等真實缺賠率場次。**')
    elif shadow['all_sparse_unpriced']:
        lines.append(
            f'- sparse 觸發 {shadow["gate_sparse"]} 場，全部 coverage=0（賠率未開）——'
            '屬「未開價」而唔係「近開跑缺賠率」，未有可評分樣本；'
            '維持 shadow，等真實缺賠率場次。')
    else:
        covs = shadow['sparse_coverages']
        lines.append(
            f'- sparse 觸發 {shadow["gate_sparse"]} 場，coverage '
            f'{min(covs):.2f}–{max(covs):.2f}；待賽果與樣本足夠後按 '
            'PREREGISTERED_AB.md 檢驗。')
    lines += [
        '',
        '## 4. 觸發條件與 escalation',
        '',
        f'- 收集開始：{COLLECTION_START.isoformat()}；已過 {audit["months_elapsed"]} 個月。',
        f'- {audit["escalation"]}',
        '- 50 場門檻未達前：時間加權融合、α 時間加權 A/B、drift 特徵一律不准開。',
        '',
        '## 5. RISKS.md 更新清單',
        '',
        f'- R5（樣本不足）：改為 complete = {p["complete_pre_race_races"]}/{p["target"]}，'
        f'partial = {p["partial_races"]}。',
        '- R2（shadow 無變異）：' + (
            '維持「shadow 無變異，等真實缺賠率場次」。' if shadow['no_variance']
            else ('sparse 全部為未開價（coverage=0）場次，仍未可評分。'
                  if shadow['all_sparse_unpriced']
                  else '出現 coverage>0 的 sparse 樣本，更新計數。')),
        '- R4（fallback 體積）：更新 raw/gzip 大小與處置。',
        '- R3（DDL 未套用）：更新 table_ready 與 escalation 狀態。',
        '',
        audit['escalation'],
        '',
    ]
    return '\n'.join(lines)


def main():
    supabase = get_supabase()
    audit = build_audit(supabase)
    markdown = render_monthly_markdown(audit)
    month = audit['generated'][:7]
    out = os.path.join(ROOT, 'reports', f'monthly_data_audit_{month}.md')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(markdown)
    print(markdown)
    print(f'[MonthlyAudit] -> {out}')


if __name__ == '__main__':
    main()