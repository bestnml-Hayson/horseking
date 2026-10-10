'use client'

import type { RaceRow } from '@/lib/types'
import { runBettingEngine, DEFAULT_BANKROLL } from '@/lib/betting-engine'
import type { BettingEngineResult, WinBet, QCombination, DarkHorse, OverlayHorse, UnderlayHorse } from '@/lib/betting-engine'
import { fmtOdds, fmtEV } from '@/lib/race-utils'

interface BettingStrategyProps {
  rows: RaceRow[]
  bankroll?: number
}

function getPFinal(row: RaceRow): number {
  return row.prediction?.final_prob ?? 0
}

function HorseBadge({ row, amount, kellyPct, ev, betType }: { row: RaceRow; amount: number; kellyPct: number; ev: number; betType: string }) {
  return (
    <div className="tier-horse-row">
      <div className="tier-horse-info">
        <span className="tier-horse-no">#{row.horse_no}</span>
        <span className="tier-horse-name">{row.horse_name}</span>
        <span className="tier-bet-type">{betType}</span>
      </div>
      <div className="tier-horse-stats">
        <span className="tier-stat">P {(getPFinal(row) * 100).toFixed(1)}%</span>
        <span className="tier-stat">賠率 {fmtOdds(row.win_odds)}</span>
        <span className={`tier-stat ${ev > 0 ? 'ev-pos' : 'ev-neg'}`}>EV {fmtEV(ev)}</span>
      </div>
      <div className="tier-horse-amount">
        <span className="tier-amount-val">HKD ${amount}</span>
        <span className="tier-amount-pct">({kellyPct.toFixed(2)}%)</span>
      </div>
    </div>
  )
}

function QPRow({ combo, amount }: { combo: QCombination; amount: number }) {
  const perLeg = Math.round(amount / Math.max(1, combo.legs.length))
  return (
    <div className="tier-qp-row">
      <div className="tier-qp-anchor">
        <span className="tier-qp-label">膽</span>
        <span className="tier-qp-no">#{combo.anchor.horse_no}</span>
        <span className="tier-qp-name">{combo.anchor.horse_name}</span>
        <span className="tier-qp-prob">P {(getPFinal(combo.anchor) * 100).toFixed(1)}%</span>
      </div>
      <div className="tier-qp-legs">
        {combo.legs.map(({ row, pPair }) => (
          <div key={row.runner_id} className="tier-qp-leg">
            <span className="tier-qp-leg-label">腳</span>
            <span className="tier-qp-no">#{row.horse_no}</span>
            <span className="tier-qp-name">{row.horse_name}</span>
            <span className="tier-qp-prob">P_pair {(pPair * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
      <div className="tier-qp-cost">
        <span className="tier-amount-val">HKD ${amount}</span>
        <span className="tier-amount-pct">({combo.legs.length} 注 × ${perLeg})</span>
      </div>
    </div>
  )
}

function CoreTier({ bets, qCombos, amount }: { bets: WinBet[]; qCombos: QCombination[]; amount: number }) {
  const hasContent = bets.length > 0 || qCombos.length > 0
  if (!hasContent) return null

  return (
    <div className="tier-section tier-core">
      <div className="tier-header">
        <div className="tier-header-left">
          <span className="tier-icon">&#x1F6E1;&#xFE0F;</span>
          <div>
            <div className="tier-title">主線穩健組合</div>
            <div className="tier-subtitle">Core Bets &mdash; 勝率最高獨贏/位置 + 雙膽 QP</div>
          </div>
        </div>
        <div className="tier-header-right">
          <span className="tier-alloc-badge">60% 資金</span>
          <span className="tier-amount-total">HKD ${amount}</span>
        </div>
      </div>
      <div className="tier-body">
        {bets.map(b => (
          <HorseBadge key={b.row.runner_id} row={b.row} amount={b.amount} kellyPct={b.kellyPct} ev={b.ev} betType={b.betType} />
        ))}
        {qCombos.map((c, i) => (
          <QPRow key={i} combo={c} amount={c.totalCost} />
        ))}
      </div>
    </div>
  )
}

function ValueTier({ bets, qCombos, amount }: { bets: WinBet[]; qCombos: QCombination[]; amount: number }) {
  const hasContent = bets.length > 0 || qCombos.length > 0
  if (!hasContent) return null

  return (
    <div className="tier-section tier-value">
      <div className="tier-header">
        <div className="tier-header-left">
          <span className="tier-icon">&#x1F4B9;</span>
          <div>
            <div className="tier-title">高價值對衝組合</div>
            <div className="tier-subtitle">Value Overlay &mdash; 正期望值位置 + Q/QP 腳馬</div>
          </div>
        </div>
        <div className="tier-header-right">
          <span className="tier-alloc-badge tier-alloc-value">30% 資金</span>
          <span className="tier-amount-total">HKD ${amount}</span>
        </div>
      </div>
      <div className="tier-body">
        {bets.map(b => (
          <HorseBadge key={b.row.runner_id} row={b.row} amount={b.amount} kellyPct={b.kellyPct} ev={b.ev} betType={b.betType} />
        ))}
        {qCombos.map((c, i) => (
          <QPRow key={i} combo={c} amount={c.totalCost} />
        ))}
      </div>
    </div>
  )
}

function LongshotTier({ darkHorses, trio, quartet, amount }: { darkHorses: DarkHorse[]; trio: BettingEngineResult['trio']; quartet: BettingEngineResult['quartet']; amount: number }) {
  const hasContent = darkHorses.length > 0 || trio || quartet
  if (!hasContent) return null

  return (
    <div className="tier-section tier-longshot">
      <div className="tier-header">
        <div className="tier-header-left">
          <span className="tier-icon">&#x1F4A3;</span>
          <div>
            <div className="tier-title">高彩金爆冷組合</div>
            <div className="tier-subtitle">Longshot &mdash; 冷熱配 3T / 4連環 / 爆冷獨贏</div>
          </div>
        </div>
        <div className="tier-header-right">
          <span className="tier-alloc-badge tier-alloc-longshot">10% 資金</span>
          <span className="tier-amount-total">HKD ${amount}</span>
        </div>
      </div>
      <div className="tier-body">
        {darkHorses.map(d => (
          <div key={d.row.runner_id} className="tier-horse-row tier-dark-row">
            <div className="tier-horse-info">
              <span className="tier-horse-no">#{d.row.horse_no}</span>
              <span className="tier-horse-name">{d.row.horse_name}</span>
              <span className="tier-dark-badge">爆冷</span>
            </div>
            <div className="tier-horse-stats">
              <span className="tier-stat">賠率 {d.odds.toFixed(0)}x</span>
              <span className="tier-stat ev-pos">EV {fmtEV(d.ev)}</span>
              <span className="tier-stat">模型 #{d.modelRank}</span>
              <span className="tier-stat">市場 #{d.marketRank}</span>
            </div>
            <div className="tier-horse-amount">
              <span className="tier-amount-val">HKD $10</span>
              <span className="tier-amount-pct">小注博冷</span>
            </div>
          </div>
        ))}
        {trio && (
          <div className="tier-trio-row">
            <div className="tier-trio-label">&#x1F3C6; 三重彩</div>
            <div className="tier-trio-horses">
              {trio.horses.map((h, i) => (
                <span key={h.runner_id} className="tier-trio-horse">
                  {i === 0 ? '冠' : i === 1 ? '亞' : '季'} #{h.horse_no} {h.horse_name}
                </span>
              ))}
            </div>
            <div className="tier-trio-stats">
              <span>P {(trio.pTrio * 100).toFixed(2)}%</span>
              <span>賠率 ~{trio.estimatedOdds.toFixed(0)}x</span>
              <span className="tier-amount-val">HKD $10</span>
            </div>
          </div>
        )}
        {quartet && (
          <div className="tier-quartet-row">
            <div className="tier-quartet-label">&#x1F3C5; 四連環</div>
            <div className="tier-quartet-horses">
              {quartet.horses.map(h => (
                <span key={h.runner_id} className="tier-quartet-horse">
                  #{h.horse_no} {h.horse_name}
                </span>
              ))}
            </div>
            <div className="tier-quartet-stats">
              <span>P {(quartet.pQuartet * 100).toFixed(3)}%</span>
              <span>賠率 ~{quartet.estimatedOdds.toFixed(0)}x</span>
              <span className="tier-amount-val">HKD $40</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function OverlayUnderlayBar({ overlays, underlays }: { overlays: OverlayHorse[]; underlays: UnderlayHorse[] }) {
  if (overlays.length === 0 && underlays.length === 0) return null

  return (
    <div className="ou-bar">
      {overlays.length > 0 && (
        <div className="ou-section ou-overlay">
          <span className="ou-icon">&#x1F525;</span>
          <span className="ou-title">Overlay 價值馬</span>
          <span className="ou-count">{overlays.length} 匹</span>
          <div className="ou-horses">
            {overlays.map(o => (
              <span key={o.row.runner_id} className="ou-horse">
                #{o.row.horse_no} {o.row.horse_name} <span className="ou-ratio">{o.ratio.toFixed(2)}x</span>
              </span>
            ))}
          </div>
        </div>
      )}
      {underlays.length > 0 && (
        <div className="ou-section ou-underlay">
          <span className="ou-icon">&#x26A0;&#xFE0F;</span>
          <span className="ou-title">Underlay 過熱馬</span>
          <span className="ou-count">{underlays.length} 匹</span>
          <div className="ou-horses">
            {underlays.map(u => (
              <span key={u.row.runner_id} className="ou-horse">
                #{u.row.horse_no} {u.row.horse_name} <span className="ou-ratio">{u.ratio.toFixed(2)}x</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function BettingStrategy({ rows, bankroll = DEFAULT_BANKROLL }: BettingStrategyProps) {
  const engine = runBettingEngine(rows, bankroll)

  const hasAnyData = engine.winPoolValue || engine.qCombos.length > 0 || engine.overlays.length > 0 || engine.darkHorses.length > 0

  if (!hasAnyData) {
    return (
      <div className="betting-section animate-fade-in">
        <div className="betting-header">
          <span className="betting-badge">&#x1F4B0; 量化投注建議</span>
          <span className="betting-sublabel">Bankroll-Managed Betting Engine</span>
        </div>
        <div className="betting-empty">
          暫無投注策略數據（賠率尚未同步或無正 EV 馬匹）
        </div>
      </div>
    )
  }

  const { allocation } = engine

  return (
    <div className="betting-section animate-fade-in">
      <div className="betting-header">
        <span className="betting-badge">&#x1F4B0; 量化投注建議</span>
        <span className="betting-sublabel">Bankroll-Managed Betting Engine</span>
      </div>

      <div className="betting-banner">
        <div className="banner-item banner-total">
          <span className="banner-label">本場建議總投注額</span>
          <span className="banner-value">HKD ${engine.totalRecommendedBet}</span>
          <span className="banner-pct">（佔總資金 {engine.totalPct.toFixed(1)}%）</span>
        </div>
        <div className="banner-item banner-ev">
          <span className="banner-label">本場預期 EV</span>
          <span className={`banner-value ${engine.expectedEV > 0 ? 'ev-pos' : 'ev-neg'}`}>
            {engine.expectedEV > 0 ? '+' : ''}{(engine.expectedEV * 100).toFixed(1)}%
          </span>
        </div>
        <div className="banner-item banner-bankroll">
          <span className="banner-label">基準資金池</span>
          <span className="banner-value">HKD ${bankroll.toLocaleString()}</span>
        </div>
      </div>

      <OverlayUnderlayBar overlays={engine.overlays} underlays={engine.underlays} />

      <div className="tier-container">
        <CoreTier bets={allocation.core.bets} qCombos={allocation.core.qCombos} amount={allocation.core.amount} />
        <ValueTier bets={engine.winBets.filter(b => b.betType === 'PLACE')} qCombos={allocation.value.qCombos} amount={allocation.value.amount} />
        <LongshotTier darkHorses={allocation.longshot.darkHorses} trio={allocation.longshot.trio} quartet={allocation.longshot.quartet} amount={allocation.longshot.amount} />
      </div>
    </div>
  )
}
