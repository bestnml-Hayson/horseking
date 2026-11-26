'use client'

import type { Race, RaceRow } from '@/lib/types'
import type { HorseRaceRecord, OddsDriftEntry } from '@/lib/supabase-client'
import {
  MODEL_WEIGHT,
  MARKET_WEIGHT,
  RUN_STYLE_META,
  computeBenterBreakdown,
  dominantRunStyle,
  predictPace,
  recentRunStyles,
  type RacecourseWeights,
  type RunStyle,
} from '@/lib/race-utils'

interface AIRaceAnalysisProps {
  race: Race | undefined
  rows: RaceRow[]
  horseHistory?: Map<string, HorseRaceRecord[]> | null
  oddsDrift?: Map<string, OddsDriftEntry>
}

type FactorKey = keyof RacecourseWeights
type Breakdown = ReturnType<typeof computeBenterBreakdown>

const FACTOR_LABELS: Record<FactorKey, string> = {
  form: '近況',
  draw: '檔位',
  jockeyTrainer: '騎練',
  weight: '負磅',
  courseDistance: '途程',
  restDays: '休養',
  gear: '配備',
  pace: '步速',
  classMov: '班次',
}

const FACTOR_SCORES: Record<FactorKey, (b: Breakdown) => number> = {
  form: b => b.formScore,
  draw: b => b.drawScore,
  jockeyTrainer: b => b.jockeyTrainerScore,
  weight: b => b.weightScore,
  courseDistance: b => b.courseDistanceScore,
  restDays: b => b.restDaysScore,
  gear: b => b.gearScore,
  pace: b => b.paceScore,
  classMov: b => b.classMovScore,
}

export function AIRaceAnalysis({ race, rows, horseHistory, oddsDrift }: AIRaceAnalysisProps) {
  if (rows.length === 0) return null

  const pace = predictPace(rows, horseHistory, race)

  // --- Card 1: pace scenario with named horses from 沿途走位 history ---
  const styled = rows.map(row => {
    const styles = recentRunStyles(horseHistory?.get(row.horse_id), 6)
    const dom = dominantRunStyle(styles)
    return { row, dominant: dom.style, counts: dom.counts, rated: styles.length }
  })
  const leaders = styled
    .filter(s => s.dominant === 'leader')
    .sort((a, b) => b.counts.leader - a.counts.leader)
    .slice(0, 3)
  const closers = styled
    .filter(s => s.dominant === 'closer')
    .sort((a, b) => b.counts.closer - a.counts.closer)
    .slice(0, 3)
  const ratedCount = styled.filter(s => s.dominant !== null).length

  const paceImplication = pace.label === '快步速'
    ? '前領馬互相搶口，後上馬形勢有利'
    : pace.label === '慢步速'
      ? '領放馬偏少，前領馬有機會一放到底'
      : '步速預計中等，跑法形勢較均衡'

  const styleList = (items: typeof leaders, style: RunStyle) =>
    items
      .map(s => `${s.row.horse_no} 號 ${s.row.horse_name}（近 ${s.rated} 仗 ${s.counts[style]} 次${RUN_STYLE_META[style].label}）`)
      .join('、')

  // --- Card 2: which factor separates the model's top three ---
  const contenders = [...rows]
    .sort((a, b) => (b.prediction?.raw_model_prob ?? 0) - (a.prediction?.raw_model_prob ?? 0))
    .slice(0, 3)
  const breakdowns = contenders.map(row => computeBenterBreakdown(row, race?.venue, {
    race,
    horseHistory: horseHistory ?? undefined,
    paceLabel: pace.label,
    totalRunners: rows.length,
  }))
  const factorSpreads = contenders.length >= 2
    ? (Object.keys(FACTOR_LABELS) as FactorKey[])
      .map(key => {
        const weighted = breakdowns.map((b, i) => ({
          row: contenders[i],
          score: FACTOR_SCORES[key](b),
          contribution: b.weights[key] * FACTOR_SCORES[key](b),
        }))
        const best = weighted.reduce((m, x) => (x.contribution > m.contribution ? x : m))
        const worst = weighted.reduce((m, x) => (x.contribution < m.contribution ? x : m))
        return { key, weight: breakdowns[0].weights[key], best, worst, spread: best.contribution - worst.contribution }
      })
      .sort((a, b) => b.spread - a.spread)
      .slice(0, 2)
    : []

  // --- Card 3: opening vs latest price from the tick's drift snapshots ---
  const moves = rows
    .flatMap(row => {
      const entry = oddsDrift?.get(row.runner_id)
      if (!entry || !(entry.open > 1) || !(entry.last > 1) || entry.last === entry.open) return []
      return [{ row, entry, pct: ((entry.last - entry.open) / entry.open) * 100 }]
    })
    .sort((a, b) => a.pct - b.pct)
  const steam = moves.find(m => m.pct < 0)
  const drift = [...moves].reverse().find(m => m.pct > 0)
  const tracked = rows.reduce((n, r) => n + (oddsDrift?.get(r.runner_id) ? 1 : 0), 0)
  const hasOdds = rows.some(r => r.win_odds != null && r.win_odds > 1)
  const driftEmptyText = !hasOdds
    ? '待定 — 賠率尚未開出'
    : tracked > 0
      ? `已追蹤 ${tracked} 匹，開盤至今未見明顯變動`
      : '待定 — 賠率快照收集後自動顯示落飛／回飛'

  return (
    <div className="ai-analysis-section animate-fade-in">
      <div className="ai-analysis-header">
        <span className="ai-analysis-badge">&#x1F9E0; AI 賽事綜合分析</span>
        <span className="ai-analysis-sublabel">Benter Quant Race Analysis</span>
        <span
          className="ai-analysis-info"
          title={`Benter 兩階段模型：階段一以 9 項因素（近況、檔位、騎練、負磅、途程、休養、配備、步速、班次）計算純實力 P_model；階段二以 (1/賠率)^1.3 正規化為市場機率 P_market，P_final = ${Math.round(MODEL_WEIGHT * 100)}% P_model + ${Math.round(MARKET_WEIGHT * 100)}% P_market；賠率未開出時 P_final = P_model。`}
        >
          &#x24D8;
        </span>
      </div>

      <div className="ai-analysis-grid">
        {/* Pace scenario, named */}
        <div className="ai-analysis-card pace-card">
          <div className="ai-card-icon">&#x1F3C3;</div>
          <div className="ai-card-content">
            <div className="ai-card-label">步速形勢</div>
            <div className="ai-card-value">
              {pace.label}
              {ratedCount > 0 && <span className="ai-card-value-sub"> · {ratedCount}/{rows.length} 匹有跑法往績</span>}
            </div>
            {ratedCount > 0 ? (
              <div className="ai-card-detail">
                {leaders.length > 0 && (
                  <div><span className="ai-style-tag">領放</span>{styleList(leaders, 'leader')}</div>
                )}
                {closers.length > 0 && (
                  <div><span className="ai-style-tag">後上</span>{styleList(closers, 'closer')}</div>
                )}
                <div className="ai-pace-implication">{paceImplication}</div>
              </div>
            ) : (
              <div className="ai-card-detail">{pace.detail}</div>
            )}
          </div>
        </div>

        {/* Factor spread among the model's top three */}
        <div className="ai-analysis-card factors-card">
          <div className="ai-card-icon">&#x1F511;</div>
          <div className="ai-card-content">
            <div className="ai-card-label">今場分野因素</div>
            <div className="ai-factors-list">
              {factorSpreads.length > 0 && factorSpreads[0].spread >= 2 ? (
                factorSpreads.map(f => (
                  <div key={f.key} className="ai-factor-row">
                    <span className="ai-factor-name">{FACTOR_LABELS[f.key]}</span>
                    <span className="ai-factor-weight">{Math.round(f.weight * 100)}%</span>
                    <span className="ai-factor-detail">
                      {f.best.row.horse_no} 號 {Math.round(f.best.score)} 分 vs {f.worst.row.horse_no} 號 {Math.round(f.worst.score)} 分
                    </span>
                    <span className="ai-factor-gap">+{f.spread.toFixed(1)}</span>
                  </div>
                ))
              ) : (
                <div className="ai-factor-item factor-neutral">
                  <span className="factor-icon">&#x2139;&#xFE0F;</span>
                  <span className="factor-text">首三名各項因素接近，勝負主要取決於市場定價</span>
                </div>
              )}
            </div>
            <div className="ai-card-foot">以 P_model 首三名比較 · 分野 = 權重 × 分數差距</div>
          </div>
        </div>

        {/* Odds drift */}
        <div className="ai-analysis-card drift-card">
          <div className="ai-card-icon">&#x1F4C8;</div>
          <div className="ai-card-content">
            <div className="ai-card-label">賠率走勢</div>
            {steam || drift ? (
              <div className="ai-drift-list">
                {steam && (
                  <div className="ai-drift-row">
                    <span className="ai-drift-tag down">落飛</span>
                    <span className="ai-drift-horse">{steam.row.horse_no} 號 {steam.row.horse_name}</span>
                    <span className="ai-drift-prices">{steam.entry.open.toFixed(1)} → {steam.entry.last.toFixed(1)}</span>
                    <span className="ai-drift-pct down">{steam.pct.toFixed(1)}%</span>
                  </div>
                )}
                {drift && (
                  <div className="ai-drift-row">
                    <span className="ai-drift-tag up">回飛</span>
                    <span className="ai-drift-horse">{drift.row.horse_no} 號 {drift.row.horse_name}</span>
                    <span className="ai-drift-prices">{drift.entry.open.toFixed(1)} → {drift.entry.last.toFixed(1)}</span>
                    <span className="ai-drift-pct up">+{drift.pct.toFixed(1)}%</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="ai-card-detail">{driftEmptyText}</div>
            )}
            {tracked > 0 && (
              <div className="ai-card-foot">開盤價 → 最新價 · 已追蹤 {tracked}/{rows.length} 匹</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}