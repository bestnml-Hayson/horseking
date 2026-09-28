'use client'

import type { RaceRow } from '@/lib/types'
import { fmtOdds, fmtEV, fmtKelly, parseFormHistory, getFormColor } from '@/lib/race-utils'

const VALUE_THRESHOLD = 0.15

interface RaceTableProps {
  rows: RaceRow[]
  topPickId: string | null
  onHorseClick?: (horseId: string, horseName: string) => void
}

function fmtProb(p: number | null): string {
  if (p == null) return '-'
  return (p * 100).toFixed(1) + '%'
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
    <div className="race-table-scroll">
      <table className="data-table benter-table">
        <thead>
          <tr>
            <th style={{ width: 44 }}>No.</th>
            <th>馬名</th>
            <th style={{ width: 160 }}>近 6 場往績</th>
            <th>騎師 / 練馬師</th>
            <th style={{ textAlign: 'center', width: 48 }}>檔</th>
            <th style={{ textAlign: 'right', width: 64 }}>賠率</th>
            <th className="th-model" style={{ textAlign: 'right', width: 72 }}>P_model</th>
            <th className="th-market" style={{ textAlign: 'right', width: 72 }}>P_market</th>
            <th className="th-final" style={{ textAlign: 'right', width: 72 }}>P_final</th>
            <th style={{ textAlign: 'right', width: 72 }}>EV</th>
            <th style={{ textAlign: 'right', width: 72 }}>Kelly%</th>
            <th style={{ width: 110 }}>標籤</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, idx) => {
            const pred = row.prediction
            const pModel = pred?.raw_model_prob ?? null
            const pMarket = pred?.market_implied_prob ?? null
            const pFinal = pred?.final_prob ?? null
            const ev = pred?.expected_value ?? null
            const kelly = pred?.kelly_fraction ?? null
            const isValue = ev !== null && ev > VALUE_THRESHOLD
            const isTopPick = row.runner_id === topPickId
            const isValueBet = isValue && kelly !== null && kelly > 0
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
                <td style={{ textAlign: 'right' }} className="tabular-nums prob-model-cell">
                  <span className="prob-pill prob-model">{fmtProb(pModel)}</span>
                </td>
                <td style={{ textAlign: 'right' }} className="tabular-nums prob-market-cell">
                  <span className="prob-pill prob-market">{fmtProb(pMarket)}</span>
                </td>
                <td style={{ textAlign: 'right' }} className="tabular-nums prob-final-cell">
                  <span className="badge badge-prob badge-final">
                    {fmtProb(pFinal)}
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
    </div>
  )
}
