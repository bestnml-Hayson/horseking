'use client'

import type { RaceRow } from '@/lib/types'
import {
  getBestWinBet,
  getQCombination,
  getTrioCombination,
  computeAIScore,
  fmtOdds,
  fmtKelly,
  fmtEV,
} from '@/lib/race-utils'

interface BettingStrategyProps {
  rows: RaceRow[]
  bankroll?: number
}

const DEFAULT_BANKROLL = 10000

export function BettingStrategy({ rows, bankroll = DEFAULT_BANKROLL }: BettingStrategyProps) {
  const bestWin = getBestWinBet(rows)
  const qCombo = getQCombination(rows)
  const trioCombo = getTrioCombination(rows)

  const hasData = bestWin || qCombo || trioCombo

  if (!hasData) {
    return (
      <div className="betting-empty">
        暫無投注策略數據（需要 EV &gt; 0.15 的馬匹）
      </div>
    )
  }

  return (
    <div className="betting-section animate-fade-in">
      <div className="betting-header">
        <span className="betting-badge">&#x1F4B0; 最佳實戰投注策略</span>
        <span className="betting-sublabel">Quant Betting Recommendations</span>
      </div>

      <div className="betting-grid">
        {/* WIN / PLACE */}
        <div className="betting-card win-card">
          <div className="betting-card-title">
            <span className="betting-icon">&#x1F3AF;</span>
            獨贏 (WIN) / 位置 (PLACE)
          </div>
          {bestWin ? (
            <div className="betting-card-body">
              <div className="bet-horse">
                <span className="bet-horse-no">#{bestWin.horse_no}</span>
                <span className="bet-horse-name">{bestWin.horse_name}</span>
              </div>
              <div className="bet-details">
                <div className="bet-detail-row">
                  <span className="bet-detail-label">賠率</span>
                  <span className="bet-detail-value">{fmtOdds(bestWin.win_odds)}</span>
                </div>
                <div className="bet-detail-row">
                  <span className="bet-detail-label">EV</span>
                  <span className="bet-detail-value ev-positive">{fmtEV(bestWin.prediction?.expected_value ?? null)}</span>
                </div>
                <div className="bet-detail-row">
                  <span className="bet-detail-label">Kelly%</span>
                  <span className="bet-detail-value kelly-value">{fmtKelly(bestWin.prediction?.kelly_fraction ?? null)}</span>
                </div>
              </div>
              <div className="bet-amount">
                建議注碼: <strong>HKD {Math.round((bestWin.prediction?.kelly_fraction ?? 0) * bankroll)}</strong>
              </div>
            </div>
          ) : (
            <div className="betting-card-empty">暫無正 EV 馬匹</div>
          )}
        </div>

        {/* Q / QP */}
        <div className="betting-card q-card">
          <div className="betting-card-title">
            <span className="betting-icon">&#x1F40E;</span>
            連贏 (Q) / 位置 Q (QP)
          </div>
          {qCombo ? (
            <div className="betting-card-body">
              <div className="bet-combo">
                <span className="bet-anchor">
                  #{qCombo.anchor.horse_no} {qCombo.anchor.horse_name}
                </span>
                <span className="bet-drag">膽拖</span>
                <div className="bet-legs">
                  {qCombo.legs.map(h => (
                    <span key={h.runner_id} className="bet-leg">
                      #{h.horse_no} {h.horse_name}
                    </span>
                  ))}
                </div>
              </div>
              <div className="bet-combo-note">
                一膽三腳 · 共 {qCombo.legs.length} 注
              </div>
            </div>
          ) : (
            <div className="betting-card-empty">數據不足</div>
          )}
        </div>

        {/* Trio */}
        <div className="betting-card trio-card">
          <div className="betting-card-title">
            <span className="betting-icon">&#x1F3C6;</span>
            單T (Trio) / 三重彩
          </div>
          {trioCombo ? (
            <div className="betting-card-body">
              <div className="trio-horses">
                {trioCombo.map((h, i) => (
                  <div key={h.runner_id} className="trio-horse">
                    <span className="trio-rank">#{i + 1}</span>
                    <span className="trio-no">#{h.horse_no}</span>
                    <span className="trio-name">{h.horse_name}</span>
                    <span className="trio-score">
                      AI {computeAIScore(h)}
                    </span>
                  </div>
                ))}
              </div>
              <div className="bet-combo-note">
                Top 4 精算組合 · 最高勝率
              </div>
            </div>
          ) : (
            <div className="betting-card-empty">數據不足</div>
          )}
        </div>
      </div>
    </div>
  )
}
