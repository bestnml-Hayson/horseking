'use client'

import type { TrebleResult } from '@/lib/treble-engine'

interface TrebleCardProps {
  treble: TrebleResult
}

export function TrebleCard({ treble }: TrebleCardProps) {
  const { picks, combinations } = treble

  return (
    <div className="treble-inline">
      <div className="treble-inline-header">
        <span className="treble-inline-badge">&#x1F451; 3T 建議</span>
        <span className="treble-inline-sub">R5 + R6 + R7</span>
      </div>

      <div className="treble-inline-picks">
        {picks.map(({ raceNo, picks: racePicks }) => (
          <div key={raceNo} className="treble-inline-race">
            <span className="treble-inline-raceno">R{raceNo}</span>
            {racePicks.map((pick, i) => (
              <span key={pick.row.runner_id} className={`treble-inline-horse ${i === 0 ? 'treble-inline-top' : ''}`}>
                #{pick.row.horse_no} {pick.row.horse_name}
                <span className="treble-inline-p">{(pick.pFinal * 100).toFixed(1)}%</span>
              </span>
            ))}
          </div>
        ))}
      </div>

      {combinations.length > 0 && (
        <div className="treble-inline-combos">
          {combinations.slice(0, 3).map((combo, ci) => (
            <div key={ci} className="treble-inline-combo">
              <span className="treble-inline-rank">#{ci + 1}</span>
              <div className="treble-inline-legs">
                {combo.legs.map((leg, li) => (
                  <span key={li} className="treble-inline-leg">
                    R{leg.raceNo} #{leg.row.horse_no} {leg.row.horse_name}
                  </span>
                ))}
              </div>
              <span className="treble-inline-odds">P {(combo.pComposite * 100).toFixed(3)}% ~{combo.estimatedOdds.toFixed(0)}x</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
