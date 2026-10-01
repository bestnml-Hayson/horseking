'use client'

import type { TrebleResult } from '@/lib/treble-engine'

interface TrebleCardProps {
  treble: TrebleResult
}

export function TrebleCard({ treble }: TrebleCardProps) {
  const { picks } = treble

  return (
    <div className="treble-inline">
      <span className="treble-inline-badge">&#x1F451; 3T</span>
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
    </div>
  )
}
