'use client'

import type { RaceRow } from '@/lib/types'

const VALUE_THRESHOLD = 0.15

export function RaceTable({ rows, topPickId }: { rows: RaceRow[], topPickId: string | null }) {
  if (rows.length === 0) {
    return (
      <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
        No runners data for this race
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
          <th style={{ width: 48 }}>No.</th>
          <th>Horse</th>
          <th>Jockey</th>
          <th>Trainer</th>
          <th style={{ textAlign: 'right', width: 56 }}>Wt</th>
          <th style={{ textAlign: 'right', width: 56 }}>Draw</th>
          <th style={{ textAlign: 'right', width: 72 }}>Odds</th>
          <th style={{ textAlign: 'right', width: 80 }}>P_final</th>
          <th style={{ textAlign: 'right', width: 80 }}>EV</th>
          <th style={{ textAlign: 'right', width: 80 }}>Kelly%</th>
          <th style={{ width: 140 }}>Tag</th>
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

          let evClass = 'ev-negative'
          if (ev !== null && ev > 0 && ev <= VALUE_THRESHOLD) evClass = 'ev-neutral'
          if (ev !== null && ev > VALUE_THRESHOLD) evClass = 'ev-positive'

          return (
            <tr
              key={row.runner_id}
              className={isValueBet ? 'value-row' : ''}
              style={{
                animationDelay: `${idx * 30}ms`,
              }}
            >
              <td style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{row.horse_no}</td>
              <td>
                <span className="horse-name">{row.horse_name}</span>
              </td>
              <td style={{ color: 'var(--text-secondary)' }}>{row.jockey ?? '-'}</td>
              <td style={{ color: 'var(--text-secondary)' }}>{row.trainer ?? '-'}</td>
              <td style={{ textAlign: 'right', color: 'var(--text-secondary)' }} className="tabular-nums">
                {row.actual_weight ?? '-'}
              </td>
              <td style={{ textAlign: 'right', color: 'var(--text-secondary)' }} className="tabular-nums">
                {row.draw ?? '-'}
              </td>
              <td style={{ textAlign: 'right' }} className="tabular-nums">
                <span className="badge badge-odds">
                  {row.win_odds ? row.win_odds.toFixed(1) : '-'}
                </span>
              </td>
              <td style={{ textAlign: 'right' }} className="tabular-nums">
                <span className="badge badge-prob">
                  {pFinal !== null ? (pFinal * 100).toFixed(1) + '%' : '-'}
                </span>
              </td>
              <td style={{ textAlign: 'right' }} className={`tabular-nums ${evClass}`}>
                {ev !== null ? (ev > 0 ? '+' : '') + (ev * 100).toFixed(1) + '%' : '-'}
              </td>
              <td style={{ textAlign: 'right' }} className="tabular-nums">
                <span style={{ color: kelly !== null && kelly > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                  {kelly !== null && kelly > 0 ? (kelly * 100).toFixed(2) + '%' : '-'}
                </span>
              </td>
              <td>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {isTopPick && (
                    <span className="badge badge-ai-pick">AI &#x9996;&#x9078;</span>
                  )}
                  {isValueBet && (
                    <span className="badge badge-value">VALUE &#x5C0A;&#x4EAB;&#x50F9;&#x503C;</span>
                  )}
                  {!isTopPick && !isValueBet && pFinal !== null && pFinal < 0.05 && (
                    <span className="badge badge-cold">&#x51B7;&#x9580;</span>
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
