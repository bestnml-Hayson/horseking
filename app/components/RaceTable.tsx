'use client'

import type { RaceRow } from '@/lib/types'
import { computeAIScore, fmtOdds, fmtEV, fmtKelly, parseFormHistory, getFormColor } from '@/lib/race-utils'

const VALUE_THRESHOLD = 0.15

interface RaceTableProps {
  rows: RaceRow[]
  topPickId: string | null
  onHorseClick?: (horseId: string, horseName: string) => void
}

export function RaceTable({ rows, topPickId, onHorseClick }: RaceTableProps) {
  if (rows.length === 0) {
    return (
      <div className="table-empty">
        <div className="table-empty-icon">&#x1F4CA;</div>
        <div className="table-empty-text">暫無此場次數據</div>
        <div className="table-empty-sub">No runners data for this race</div>
      </div>
    )
  }

  const sorted = [...rows].sort((a, b) => {
    const pa = a.prediction?.final_prob ?? 0
    const pb = b.prediction?.final_prob ?? 0
    return pb - pa
  })

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th style={{ width: 44 }}>No.</th>
          <th>馬名</th>
          <th style={{ width: 180 }}>近 6 場往績</th>
          <th>騎師 / 練馬師</th>
          <th style={{ textAlign: 'center', width: 52 }}>檔位</th>
          <th style={{ textAlign: 'right', width: 72 }}>賠率</th>
          <th style={{ textAlign: 'right', width: 80 }}>P_win</th>
          <th style={{ textAlign: 'right', width: 80 }}>EV</th>
          <th style={{ textAlign: 'right', width: 80 }}>Kelly%</th>
          <th style={{ width: 120 }}>標籤</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((row, idx) => {
          const ev = row.prediction?.expected_value ?? null
          const isValue = ev !== null && ev > VALUE_THRESHOLD
          const pFinal = row.prediction?.final_prob ?? null
          const kelly = row.prediction?.kelly_fraction ?? null
          const isTopPick = row.runner_id === topPickId
          const isValueBet = isValue && kelly !== null && kelly > 0
          const aiScore = computeAIScore(row)
          const formPositions = parseFormHistory(row.form_history)

          let evClass = 'ev-negative'
          if (ev !== null && ev > 0 && ev <= VALUE_THRESHOLD) evClass = 'ev-neutral'
          if (ev !== null && ev > VALUE_THRESHOLD) evClass = 'ev-positive'

          return (
            <tr
              key={row.runner_id}
              className={isValueBet ? 'value-row' : ''}
              style={{ animationDelay: `${idx * 25}ms` }}
            >
              <td className="horse-no-cell">
                <span className="horse-no-badge">{row.horse_no}</span>
              </td>
              <td>
                <div className="horse-name-cell">
                  <span
                    className="horse-name horse-name-clickable"
                    onClick={() => onHorseClick?.(row.horse_id, row.horse_name)}
                    title="點擊查看馬匹詳情"
                  >
                    {row.horse_name}
                  </span>
                  <span className="horse-ai-score" style={{
                    color: aiScore >= 70 ? '#10b981' : aiScore >= 50 ? '#f59e0b' : '#64748b'
                  }}>
                    {aiScore}
                  </span>
                </div>
              </td>
              <td>
                <div className="form-badges-cell">
                  {formPositions.length > 0 ? (
                    formPositions.map((pos, i) => (
                      <span
                        key={i}
                        className="form-badge"
                        style={{
                          backgroundColor: getFormColor(pos) + '20',
                          color: getFormColor(pos),
                          borderColor: getFormColor(pos) + '40',
                        }}
                      >
                        {pos}
                      </span>
                    ))
                  ) : (
                    <span className="form-na">-</span>
                  )}
                </div>
              </td>
              <td className="jt-cell">
                <div className="jockey-name">{row.jockey ?? '-'}</div>
                <div className="trainer-name">{row.trainer ?? '-'}</div>
              </td>
              <td style={{ textAlign: 'center' }} className="tabular-nums draw-cell">
                {row.draw ?? '-'}
              </td>
              <td style={{ textAlign: 'right' }} className="tabular-nums">
                <span className="badge badge-odds">
                  {fmtOdds(row.win_odds)}
                </span>
              </td>
              <td style={{ textAlign: 'right' }} className="tabular-nums">
                <span className="badge badge-prob">
                  {pFinal !== null ? (pFinal * 100).toFixed(1) + '%' : '-'}
                </span>
              </td>
              <td style={{ textAlign: 'right' }} className={`tabular-nums ${evClass}`}>
                {fmtEV(ev)}
              </td>
              <td style={{ textAlign: 'right' }} className="tabular-nums">
                <span className="kelly-display" style={{
                  color: kelly !== null && kelly > 0 ? '#10b981' : '#64748b',
                  fontWeight: kelly !== null && kelly > 0 ? 700 : 400,
                }}>
                  {fmtKelly(kelly)}
                </span>
              </td>
              <td>
                <div className="tag-group">
                  {isTopPick && (
                    <span className="badge badge-ai-pick">AI 首選</span>
                  )}
                  {isValueBet && (
                    <span className="badge badge-value">VALUE</span>
                  )}
                  {!isTopPick && !isValueBet && pFinal !== null && pFinal < 0.05 && (
                    <span className="badge badge-cold">冷門</span>
                  )}
                </div>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
