'use client'

import type { LongshotResult } from '@/lib/longshot-engine'

interface LongshotCardProps {
  result: LongshotResult
  onHorseClick?: (horseId: string, horseName: string) => void
}

export function LongshotCard({ result, onHorseClick }: LongshotCardProps) {
  const { longshots, hotColdCombos } = result

  if (longshots.length === 0) return null

  return (
    <div className="longshot-section animate-fade-in">
      <div className="longshot-header">
        <span className="longshot-icon">&#x1F4A3;</span>
        <div>
          <div className="longshot-title">高概率爆冷組合</div>
          <div className="longshot-sub">Longshot Overlay Strategy · Odds ≥ 12.0 且 P_model &gt; P_market</div>
        </div>
      </div>

      <div className="longshot-picks">
        <div className="longshot-label">&#x1F525; 超值冷門馬</div>
        {longshots.map((pick, i) => (
          <div key={pick.row.runner_id} className="longshot-pick-card">
            <div className="longshot-pick-rank">#{i + 1}</div>
            <div className="longshot-pick-body">
              <button
                className="longshot-pick-name"
                onClick={() => onHorseClick?.(pick.row.horse_id, pick.row.horse_name)}
              >
                #{pick.row.horse_no} {pick.row.horse_name}
              </button>
              <div className="longshot-pick-stats">
                <span className="ls-stat">
                  <span className="ls-stat-label">賠率</span>
                  <span className="ls-stat-val ls-odds">{pick.odds.toFixed(1)}</span>
                </span>
                <span className="ls-stat">
                  <span className="ls-stat-label">P_model</span>
                  <span className="ls-stat-val">{(pick.pModel * 100).toFixed(1)}%</span>
                </span>
                <span className="ls-stat">
                  <span className="ls-stat-label">P_market</span>
                  <span className="ls-stat-val ls-market">{(pick.pMarket * 100).toFixed(1)}%</span>
                </span>
                <span className="ls-stat">
                  <span className="ls-stat-label">EV</span>
                  <span className={`ls-stat-val ${pick.ev > 0 ? 'ls-ev-pos' : 'ls-ev-neg'}`}>
                    {pick.ev > 0 ? '+' : ''}{(pick.ev * 100).toFixed(1)}%
                  </span>
                </span>
              </div>
              {pick.ev > 0 && (
                <div className="longshot-pick-alert">
                  &#x2705; 正期望值 — 小注博爆冷獨贏/位置 (Kelly Low Risk)
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {hotColdCombos.length > 0 && (
        <div className="longshot-combo">
          <div className="longshot-label">&#x1F40E; 冷熱配組合 (位置 Q)</div>
          {hotColdCombos.map((combo, i) => (
            <div key={i} className="longshot-combo-row">
              <span className="combo-anchor">
                <span className="combo-tag hot">熱膽</span>
                <button
                  className="combo-horse"
                  onClick={() => onHorseClick?.(combo.anchor.row.horse_id, combo.anchor.row.horse_name)}
                >
                  #{combo.anchor.row.horse_no} {combo.anchor.row.horse_name}
                </button>
                <span className="combo-p">{(combo.anchor.pFinal * 100).toFixed(1)}%</span>
              </span>
              <span className="combo-arrow">→</span>
              {combo.longshots.map(ls => (
                <span key={ls.row.runner_id} className="combo-leg">
                  <span className="combo-tag cold">冷腳</span>
                  <button
                    className="combo-horse"
                    onClick={() => onHorseClick?.(ls.row.horse_id, ls.row.horse_name)}
                  >
                    #{ls.row.horse_no} {ls.row.horse_name}
                  </button>
                  <span className="combo-odds">@{ls.odds.toFixed(1)}</span>
                </span>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
