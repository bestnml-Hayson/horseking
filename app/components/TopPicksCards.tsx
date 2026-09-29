'use client'

import type { RaceRow } from '@/lib/types'
import {
  generateHorseInsight,
  fmtOdds,
  fmtEV,
  fmtKelly,
  getFormColor,
  isOddsPending,
  parseFormHistory,
} from '@/lib/race-utils'
import { PICK_ACCENT_COLORS, MUTED_TEXT_COLOR } from '@/lib/color-utils'

interface TopPicksCardsProps {
  picks: RaceRow[]
  totalRunners?: number
  paceLabel?: string
  onHorseClick?: (horseId: string, horseName: string) => void
}

const PICK_LABELS = ['1號膽', '2號膽', '3號膽', '4號膽']
const RANK_CLASSES = ['rank-gold', 'rank-silver', 'rank-bronze', 'rank-sky']

function fmtPct(p: number | null): string {
  if (p == null) return '-'
  return (p * 100).toFixed(1) + '%'
}

export function TopPicksCards({ picks, totalRunners, paceLabel, onHorseClick }: TopPicksCardsProps) {
  if (picks.length === 0) {
    return (
      <div className="picks-empty">
        暫無 AI 精選數據
      </div>
    )
  }

  return (
    <div className="picks-section animate-fade-in">
      <div className="picks-header">
        <span className="picks-badge">&#x1F3AF; AI 精選 4 膽</span>
        <span className="picks-sublabel">AI Top 4 Picks</span>
      </div>

      <div className="picks-grid">
        {picks.map((row, idx) => {
          const pred = row.prediction
          const pModel = pred?.raw_model_prob ?? null
          const pMarket = pred?.market_implied_prob ?? null
          const pFinal = pred?.final_prob ?? null
          const ev = pred?.expected_value ?? null
          const kelly = pred?.kelly_fraction ?? null
          const oddsPending = isOddsPending(row.win_odds)
          const formPositions = parseFormHistory(row.form_history)
          const odds = fmtOdds(row.win_odds)
          const color = PICK_ACCENT_COLORS[idx]

          return (
            <div
              key={row.runner_id}
              className="pick-card"
              style={{
                '--pick-color': color,
                animationDelay: `${idx * 80}ms`,
              } as React.CSSProperties}
            >
              <div className="pick-card-top">
                <div className={`pick-rank ${RANK_CLASSES[idx]}`}>
                  {PICK_LABELS[idx]}
                </div>
                <div className="pick-horse-no">
                  #{row.horse_no}
                </div>
              </div>

              <button
                className="pick-horse-name horse-name-link"
                onClick={() => onHorseClick?.(row.horse_id, row.horse_name)}
                title="點擊查看馬匹詳情"
              >
                {row.horse_name}
              </button>

              <div className="pick-benter-stats">
                <div className="benter-stat-row">
                  <span className="benter-label">P_model</span>
                  <span className="benter-value model-val">{fmtPct(pModel)}</span>
                </div>
                <div className="benter-stat-row">
                  <span className="benter-label">P_market</span>
                  <span className="benter-value market-val">{oddsPending ? '待定' : fmtPct(pMarket)}</span>
                </div>
                <div className="benter-stat-row highlight">
                  <span className="benter-label">P_final</span>
                  <span className="benter-value final-val">{fmtPct(pFinal)}</span>
                </div>
                <div className="benter-stat-row">
                  <span className="benter-label">EV</span>
                  <span className={`benter-value ${ev !== null && ev > 0 ? 'ev-pos' : 'ev-neg'}`}>
                    {fmtEV(ev)}
                  </span>
                </div>
                <div className="benter-stat-row">
                  <span className="benter-label">Kelly</span>
                  <span className="benter-value kelly-val">{fmtKelly(kelly)}</span>
                </div>
              </div>

              <div className="pick-stats-mini">
                <div className="pick-stat">
                  <div className="pick-stat-label">賠率</div>
                  <div className={`pick-stat-value ${isOddsPending(row.win_odds) ? 'odds-pending' : 'odds-value'}`}>
                    {isOddsPending(row.win_odds) ? '待定' : odds}
                  </div>
                </div>
              </div>

              <div className="pick-form">
                <div className="pick-form-label">近六場走勢</div>
                <div className="pick-form-chart">
                  {formPositions.length > 0 ? (
                    formPositions.map((pos, fi) => (
                      <span
                        key={fi}
                        className="form-position"
                        style={{ color: getFormColor(pos) }}
                      >
                        {pos}
                      </span>
                    ))
                  ) : (
                    <span className="form-position" style={{ color: MUTED_TEXT_COLOR }}>暫無數據</span>
                  )}
                </div>
              </div>

              <div className="pick-ai-insight">
                {generateHorseInsight(row, idx, totalRunners ?? picks.length, paceLabel)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
