'use client'

import type { Race, RaceRow } from '@/lib/types'
import { predictPace, getGoingInfo } from '@/lib/race-utils'

interface PacingBriefingProps {
  race: Race | undefined
  rows: RaceRow[]
}

export function PacingBriefing({ race, rows }: PacingBriefingProps) {
  const pace = predictPace(rows)
  const going = getGoingInfo(race)

  return (
    <div className="pacing-briefing animate-fade-in">
      <div className="pacing-briefing-header">
        <span className="pacing-badge">
          &#x1F3C7; 賽事步速與形勢預判
        </span>
        <span className="pacing-sublabel">
          Pacing & Scenario Briefing
        </span>
      </div>

      <div className="pacing-grid">
        <div className="pacing-item">
          <div className="pacing-item-label">步速預測</div>
          <div className="pacing-item-value pace-label">{pace.label}</div>
          <div className="pacing-item-detail">{pace.detail}</div>
        </div>

        <div className="pacing-divider" />

        <div className="pacing-item">
          <div className="pacing-item-label">場地狀況</div>
          <div className="pacing-item-value going-label">{going.label}</div>
          <div className="pacing-item-detail">{going.bias}</div>
        </div>

        <div className="pacing-divider" />

        <div className="pacing-item">
          <div className="pacing-item-label">途程 / 班次</div>
          <div className="pacing-item-value distance-label">
            {race?.distance ? `${race.distance}m` : '-'}
          </div>
          <div className="pacing-item-detail">
            {race?.class_level ?? '-'}
          </div>
        </div>
      </div>
    </div>
  )
}
