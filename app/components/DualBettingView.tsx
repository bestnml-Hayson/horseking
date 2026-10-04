'use client'

import type { RaceRow } from '@/lib/types'
import { isOddsPending } from '@/lib/race-utils'

interface DualBettingViewProps {
  rows: RaceRow[]
  onHorseClick?: (horseId: string, horseName: string) => void
}

interface HorseBet {
  row: RaceRow
  pModel: number
  pMarket: number
  pFinal: number
  ev: number
  odds: number
}

function getPModel(row: RaceRow): number {
  return row.prediction?.raw_model_prob ?? 0
}
function getPMarket(row: RaceRow): number {
  return row.prediction?.market_implied_prob ?? 0
}
function getPFinal(row: RaceRow): number {
  return row.prediction?.final_prob ?? 0
}
function getEV(row: RaceRow): number {
  return row.prediction?.expected_value ?? 0
}

function toHorseBet(row: RaceRow): HorseBet {
  return {
    row,
    pModel: getPModel(row),
    pMarket: getPMarket(row),
    pFinal: getPFinal(row),
    ev: getEV(row),
    odds: row.win_odds ?? 0,
  }
}

const LONGSHOT_ODDS_THRESHOLD = 12.0

export function DualBettingView({ rows, onHorseClick }: DualBettingViewProps) {
  if (rows.length === 0) return null

  const scored = rows.filter(r => getPFinal(r) > 0).map(toHorseBet)
  if (scored.length === 0) return null

  const viewA = [...scored].sort((a, b) => b.pFinal - a.pFinal).slice(0, 3)

  const viewB = scored
    .filter(h => h.odds >= LONGSHOT_ODDS_THRESHOLD && h.pModel > h.pMarket)
    .map(h => ({
      ...h,
      overlayScore: (h.pModel - h.pMarket) * 100 + Math.max(0, h.ev) * 50,
    }))
    .filter(h => h.overlayScore > 0)
    .sort((a, b) => b.overlayScore - a.overlayScore)
    .slice(0, 3)

  const oddsPending = rows.every(r => isOddsPending(r.win_odds))

  const compositeP = viewA.reduce((acc, h) => acc * h.pFinal, 1)
  const estOdds = compositeP > 0 ? (1 / compositeP) : 0

  return (
    <div className="dual-betting animate-fade-in">
      <div className="dual-betting-header">
        <span className="dual-betting-icon">&#x1F3AF;</span>
        <div>
          <div className="dual-betting-title">雙重投注策略</div>
          <div className="dual-betting-sub">View A: 穩膽最大勝率 &nbsp;|&nbsp; View B: 高賠爆冷 Overlay</div>
        </div>
      </div>

      <div className="dual-betting-grid">
        {/* View A: Max Probability */}
        <div className="dual-view view-a">
          <div className="view-label view-a-label">
            <span className="view-badge view-a-badge">&#x1F3C6; View A</span>
            <span className="view-name">最大勝率投注組合</span>
          </div>
          <div className="view-desc">P_final 最高 3 匹 · 獨贏 / 連贏 / Q</div>

          <div className="view-horses">
            {viewA.map((h, i) => (
              <div key={h.row.runner_id} className={`view-horse ${i === 0 ? 'view-horse-top' : ''}`}>
                <span className="view-rank">#{i + 1}</span>
                <button
                  className="view-horse-name"
                  onClick={() => onHorseClick?.(h.row.horse_id, h.row.horse_name)}
                >
                  #{h.row.horse_no} {h.row.horse_name}
                </button>
                <div className="view-horse-stats">
                  <span className="vh-stat">
                    <span className="vh-label">P_final</span>
                    <span className="vh-val vh-pfinal">{(h.pFinal * 100).toFixed(1)}%</span>
                  </span>
                  <span className="vh-stat">
                    <span className="vh-label">賠率</span>
                    <span className="vh-val vh-odds">{oddsPending ? '—' : h.odds.toFixed(1)}</span>
                  </span>
                  <span className="vh-stat">
                    <span className="vh-label">EV</span>
                    <span className={`vh-val ${h.ev > 0 ? 'vh-ev-pos' : 'vh-ev-neg'}`}>
                      {oddsPending ? '—' : `${h.ev > 0 ? '+' : ''}${(h.ev * 100).toFixed(1)}%`}
                    </span>
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="view-summary">
            <span className="view-summary-label">組合 P_final</span>
            <span className="view-summary-val">{(compositeP * 100).toFixed(2)}%</span>
            <span className="view-summary-sep">·</span>
            <span className="view-summary-label">估計賠率</span>
            <span className="view-summary-val">{oddsPending ? '—' : `@${estOdds.toFixed(1)}`}</span>
          </div>

          <div className="view-bet-type">
            <span className="bet-tag bet-tag-win">獨贏</span>
            <span className="bet-tag bet-tag-quinella">連贏 Q</span>
            <span className="bet-tag bet-tag-place">位置</span>
          </div>
        </div>

        {/* View B: Longshot Overlay */}
        <div className="dual-view view-b">
          <div className="view-label view-b-label">
            <span className="view-badge view-b-badge">&#x1F4A3; View B</span>
            <span className="view-name">高機會爆冷組合</span>
          </div>
          <div className="view-desc">Odds ≥ 12.0 且 P_model &gt; P_market · 市場低估</div>

          {oddsPending ? (
            <div className="view-empty">
              <span className="view-empty-icon">&#x23F3;</span>
              <span className="view-empty-text">等待即時賠率同步...</span>
              <span className="view-empty-sub">賠率更新後自動顯示爆冷價值馬</span>
            </div>
          ) : viewB.length === 0 ? (
            <div className="view-empty">
              <span className="view-empty-icon">&#x1F50D;</span>
              <span className="view-empty-text">本場無爆冷價值馬</span>
              <span className="view-empty-sub">無馬匹符合 Odds ≥ 12.0 且 P_model &gt; P_market</span>
            </div>
          ) : (
            <>
              <div className="view-horses">
                {viewB.map((h, i) => (
                  <div key={h.row.runner_id} className="view-horse view-horse-longshot">
                    <span className="view-rank">#{i + 1}</span>
                    <button
                      className="view-horse-name"
                      onClick={() => onHorseClick?.(h.row.horse_id, h.row.horse_name)}
                    >
                      #{h.row.horse_no} {h.row.horse_name}
                    </button>
                    <div className="view-horse-stats">
                      <span className="vh-stat">
                        <span className="vh-label">賠率</span>
                        <span className="vh-val vh-odds-high">{h.odds.toFixed(1)}</span>
                      </span>
                      <span className="vh-stat">
                        <span className="vh-label">P_model</span>
                        <span className="vh-val vh-pmodel">{(h.pModel * 100).toFixed(1)}%</span>
                      </span>
                      <span className="vh-stat">
                        <span className="vh-label">P_market</span>
                        <span className="vh-val vh-pmarket">{(h.pMarket * 100).toFixed(1)}%</span>
                      </span>
                      <span className="vh-stat">
                        <span className="vh-label">Edge</span>
                        <span className="vh-val vh-edge">+{((h.pModel - h.pMarket) * 100).toFixed(1)}%</span>
                      </span>
                    </div>
                    {h.ev > 0 && (
                      <div className="longshot-ev-alert">
                        &#x2705; 正 EV {`+${(h.ev * 100).toFixed(1)}%`} — 小注博爆冷
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="view-bet-type">
                <span className="bet-tag bet-tag-longshot">爆冷獨贏</span>
                <span className="bet-tag bet-tag-place">冷腳位置</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
