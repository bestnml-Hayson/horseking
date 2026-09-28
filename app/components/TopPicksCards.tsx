'use client'

import type { RaceRow } from '@/lib/types'
import {
  computeAIScore,
  generateFormHistory,
  generateExpertAnalysis,
  fmtOdds,
  getFormColor,
} from '@/lib/race-utils'

interface TopPicksCardsProps {
  picks: RaceRow[]
}

const PICK_LABELS = ['1號膽', '2號膽', '3號膽', '4號膽']
const PICK_COLORS = ['#f59e0b', '#3b82f6', '#10b981', '#8b5cf6']

export function TopPicksCards({ picks }: TopPicksCardsProps) {
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
          const score = computeAIScore(row)
          const form = generateFormHistory(row)
          const analysis = generateExpertAnalysis(row, idx + 1)
          const odds = fmtOdds(row.win_odds)
          const color = PICK_COLORS[idx]
          const formPositions = form.split('-').map(Number)

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
                <div className="pick-rank" style={{ background: color }}>
                  {PICK_LABELS[idx]}
                </div>
                <div className="pick-horse-no">
                  #{row.horse_no}
                </div>
              </div>

              <div className="pick-horse-name">
                {row.horse_name}
              </div>

              <div className="pick-stats">
                <div className="pick-stat">
                  <div className="pick-stat-label">AI 評分</div>
                  <div className="pick-stat-value" style={{ color }}>
                    {score}
                  </div>
                </div>
                <div className="pick-stat">
                  <div className="pick-stat-label">獨贏賠率</div>
                  <div className="pick-stat-value odds-value">
                    {odds}
                  </div>
                </div>
              </div>

              <div className="pick-form">
                <div className="pick-form-label">近五場走勢</div>
                <div className="pick-form-chart">
                  {formPositions.map((pos, fi) => (
                    <span
                      key={fi}
                      className="form-position"
                      style={{ color: getFormColor(pos) }}
                    >
                      {pos}
                    </span>
                  ))}
                </div>
              </div>

              <div className="pick-analysis">
                {analysis}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
