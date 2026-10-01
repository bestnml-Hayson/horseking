'use client'

import type { RaceRow } from '@/lib/types'
import { fmtOdds, fmtEV, fmtKelly, parseFormHistory, getFormColor, generateHorseInsight, isOddsPending } from '@/lib/race-utils'
import { getKellyColor } from '@/lib/color-utils'

const VALUE_THRESHOLD = 0.15

interface RaceTableProps {
  rows: RaceRow[]
  topPickId: string | null
  hasPositiveEV?: boolean
  onHorseClick?: (horseId: string, horseName: string) => void
}

function fmtProb(p: number | null): string {
  if (p == null) return '-'
  return (p * 100).toFixed(1) + '%'
}

export function RaceTable({ rows, topPickId, hasPositiveEV = true, onHorseClick }: RaceTableProps) {
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
      {!hasPositiveEV && (
        <div className="no-ev-warning">
          本場無正期望值馬匹，建議觀望
        </div>
      )}
      <table className="data-table benter-table">
        <thead>
          <tr>
            <th style={{ width: 44 }}>No.</th>
            <th>馬名</th>
            <th style={{ width: 160 }}>近 6 場往績</th>
            <th>騎師 / 練馬師</th>
            <th style={{ textAlign: 'center', width: 48 }}>檔</th>
            <th style={{ textAlign: 'center', width: 56 }}>配備</th>
            <th style={{ textAlign: 'center', width: 48 }}>休養</th>
            <th style={{ textAlign: 'right', width: 64 }}>賠率</th>
            <th className="th-model" style={{ textAlign: 'right', width: 72 }}>P_model</th>
            <th className="th-market" style={{ textAlign: 'right', width: 72 }}>P_market</th>
            <th className="th-final" style={{ textAlign: 'right', width: 72 }}>P_final</th>
            <th style={{ textAlign: 'right', width: 72 }}>EV</th>
            <th style={{ textAlign: 'right', width: 72 }}>Kelly%</th>
            <th style={{ width: 110 }}>標籤</th>
            <th style={{ minWidth: 220 }}>AI 評語</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, idx) => {
            const pred = row.prediction
            const oddsPending = isOddsPending(row.win_odds)
            const pModel = pred?.raw_model_prob ?? null
            const pMarket = pred?.market_implied_prob ?? null
            const pFinal = pred?.final_prob ?? null
            const ev = oddsPending ? null : (pred?.expected_value ?? null)
            const kelly = oddsPending ? null : (pred?.kelly_fraction ?? null)
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
                    <button
                      className="horse-name horse-name-link"
                      onClick={() => onHorseClick?.(row.horse_id, row.horse_name)}
                      title="點擊查看馬匹詳情"
                    >
                      {row.horse_name}
                    </button>
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
                  <div className="jt-badge-row">
                    <span className="jt-badge jt-jockey-badge">{row.jockey ?? '-'}</span>
                    <span className="jt-badge jt-trainer-badge">{row.trainer ?? '-'}</span>
                  </div>
                </td>
                <td style={{ textAlign: 'center' }} className="tabular-nums draw-cell">
                  {row.draw ?? '-'}
                </td>
                <td style={{ textAlign: 'center' }} className="tabular-nums">
                  {row.gear ? (
                    <span className="badge" style={{
                      backgroundColor: row.gear.includes('1') ? '#f59e0b20' : '#6b728020',
                      color: row.gear.includes('1') ? '#f59e0b' : '#9ca3af',
                      borderColor: row.gear.includes('1') ? '#f59e0b40' : '#6b728040',
                      fontSize: '0.75rem',
                      padding: '2px 6px',
                    }}>
                      {row.gear}
                    </span>
                  ) : '-'}
                </td>
                <td style={{ textAlign: 'center' }} className="tabular-nums">
                  {row.rest_days != null ? (
                    <span style={{
                      color: row.rest_days >= 90 ? '#ef4444' : row.rest_days >= 60 ? '#f59e0b' : '#9ca3af',
                      fontWeight: row.rest_days >= 60 ? 600 : 400,
                    }}>
                      {row.rest_days}天
                    </span>
                  ) : '-'}
                </td>
                <td style={{ textAlign: 'right' }} className="tabular-nums">
                  <span className={`badge ${isOddsPending(row.win_odds) ? 'badge-odds-pending' : 'badge-odds'}`}>
                    {isOddsPending(row.win_odds) ? '待定' : fmtOdds(row.win_odds)}
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
                    color: getKellyColor(kelly),
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
                <td className="ai-insight-cell">
                  {generateHorseInsight(row, idx + 1, rows.length)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
