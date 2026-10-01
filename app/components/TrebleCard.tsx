'use client'

import type { TrebleResult } from '@/lib/treble-engine'
import { fmtEV } from '@/lib/race-utils'

interface TrebleCardProps {
  treble: TrebleResult
}

function getPFinal(row: { prediction: { final_prob: number | null } | null }): number {
  return row.prediction?.final_prob ?? 0
}

export function TrebleCard({ treble }: TrebleCardProps) {
  const { racePicks, combinations } = treble
  if (racePicks.length < 3) return null

  return (
    <div className="treble-section animate-fade-in">
      <div className="treble-header">
        <span className="treble-badge">&#x1F451; Benter 3T 建議</span>
        <span className="treble-sublabel">Treble Recommendations</span>
      </div>

      <div className="treble-race-picks">
        {racePicks.map(({ race, picks }) => (
          <div key={race.race_id} className="treble-race-col">
            <div className="treble-race-label">R{race.race_no}</div>
            {picks.map((pick, i) => (
              <div key={pick.row.runner_id} className={`treble-pick ${i === 0 ? 'treble-pick-top' : ''}`}>
                <span className="treble-pick-no">#{pick.row.horse_no}</span>
                <span className="treble-pick-name">{pick.row.horse_name}</span>
                <div className="treble-pick-stats">
                  <span className="treble-pick-prob">{(pick.pFinal * 100).toFixed(1)}%</span>
                  {pick.ev > 0 && <span className="treble-pick-ev">EV{fmtEV(pick.ev)}</span>}
                  {pick.odds > 0 && <span className="treble-pick-odds">{pick.odds.toFixed(0)}x</span>}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>

      {combinations.length > 0 && (
        <div className="treble-combos">
          <div className="treble-combos-title">&#x1F3AF; 最佳 3T 組合</div>
          {combinations.slice(0, 5).map((combo, ci) => (
            <div key={ci} className="treble-combo-row">
              <span className="treble-combo-rank">#{ci + 1}</span>
              <div className="treble-combo-legs">
                {combo.legs.map((leg, li) => (
                  <span key={li} className="treble-combo-leg">
                    <span className="treble-combo-leg-race">R{leg.raceNo}</span>
                    <span className="treble-combo-leg-horse">#{leg.row.horse_no} {leg.row.horse_name}</span>
                    <span className="treble-combo-leg-prob">{(leg.pFinal * 100).toFixed(0)}%</span>
                  </span>
                ))}
              </div>
              <div className="treble-combo-meta">
                <span className="treble-combo-p">P {(combo.pComposite * 100).toFixed(3)}%</span>
                <span className="treble-combo-odds">~{combo.estimatedOdds.toFixed(0)}x</span>
              </div>
            </div>
          ))}
          <div className="treble-cost-note">
            每組合 1 注 &times; $10 = <strong>HKD 10</strong> · 5 組合合計 <strong>HKD 50</strong>
          </div>
        </div>
      )}
    </div>
  )
}
