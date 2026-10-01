'use client'

import type { RaceRow } from '@/lib/types'
import { runBettingEngine } from '@/lib/betting-engine'
import type { OverlayHorse, WinBet, QCombination, DarkHorse, TrioCombination, QuartetCombination } from '@/lib/betting-engine'
import { fmtOdds, fmtEV, fmtKelly } from '@/lib/race-utils'

interface BettingStrategyProps {
  rows: RaceRow[]
  bankroll?: number
}

function OverlayCard({ overlays }: { overlays: OverlayHorse[] }) {
  if (overlays.length === 0) return null
  return (
    <div className="betting-card overlay-card">
      <div className="betting-card-title">
        <span className="betting-icon">&#x1F525;</span>
        Overlay 冷門價值馬
        <span className="betting-card-sub">P_model / P_market &ge; 1.3</span>
      </div>
      <div className="betting-card-body">
        {overlays.map(({ row, ratio, label }) => (
          <div key={row.runner_id} className="overlay-row">
            <span className="overlay-no">#{row.horse_no}</span>
            <span className="overlay-name">{row.horse_name}</span>
            <span className="overlay-ratio">{ratio.toFixed(2)}x</span>
            <span className="overlay-label">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function UnderlayCard({ underlays }: { underlays: { row: RaceRow; ratio: number }[] }) {
  if (underlays.length === 0) return null
  return (
    <div className="betting-card underlay-card">
      <div className="betting-card-title">
        <span className="betting-icon">&#x26A0;&#xFE0F;</span>
        Underlay 過熱馬
        <span className="betting-card-sub">P_market / P_model &ge; 1.5</span>
      </div>
      <div className="betting-card-body">
        {underlays.map(({ row, ratio }) => (
          <div key={row.runner_id} className="underlay-row">
            <span className="underlay-no">#{row.horse_no}</span>
            <span className="underlay-name">{row.horse_name}</span>
            <span className="underlay-ratio">{ratio.toFixed(2)}x</span>
            <span className="underlay-label">市場過熱，避免投注</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function WinPlaceCard({ bets, hasValue }: { bets: WinBet[]; hasValue: boolean }) {
  return (
    <div className="betting-card win-card">
      <div className="betting-card-title">
        <span className="betting-icon">&#x1F3AF;</span>
        獨贏 / 位置 (WIN / PLACE)
      </div>
      <div className="betting-card-body">
        {!hasValue ? (
          <div className="betting-no-value">
            獨贏彩池無顯著價值，建議改下連贏 / 位置 Q
          </div>
        ) : (
          bets.map(({ row, ev, kelly, units, betType }) => (
            <div key={row.runner_id} className="win-bet-row">
              <div className="win-bet-horse">
                <span className="win-bet-no">#{row.horse_no}</span>
                <span className="win-bet-name">{row.horse_name}</span>
                <span className="win-bet-type">{betType}</span>
              </div>
              <div className="win-bet-details">
                <span className="win-bet-odds">賠率 {fmtOdds(row.win_odds)}</span>
                <span className="win-bet-ev">EV {fmtEV(ev)}</span>
                <span className="win-bet-kelly">Kelly {fmtKelly(kelly)}</span>
              </div>
              <div className="win-bet-amount">
                {units} 注 &times; $10 = <strong>HKD {units * 10}</strong>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function QCard({ combos }: { combos: QCombination[] }) {
  if (combos.length === 0) {
    return (
      <div className="betting-card q-card">
        <div className="betting-card-title">
          <span className="betting-icon">&#x1F40E;</span>
          連贏 Q / 位置 Q (QP)
        </div>
        <div className="betting-card-body">
          <div className="betting-no-value">數據不足，無法計算連贏組合</div>
        </div>
      </div>
    )
  }

  return (
    <div className="betting-card q-card">
      <div className="betting-card-title">
        <span className="betting-icon">&#x1F40E;</span>
        連贏 Q / 位置 Q (QP)
        <span className="betting-card-sub">P_ij = P_final_i &times; P_final_j &times; 1.05</span>
      </div>
      <div className="betting-card-body">
        {combos.map((combo, ci) => (
          <div key={ci} className="q-combo">
            <div className="q-anchor">
              <span className="q-anchor-label">馬膽</span>
              <span className="q-anchor-no">#{combo.anchor.horse_no}</span>
              <span className="q-anchor-name">{combo.anchor.horse_name}</span>
              <span className="q-anchor-prob">
                P_final {(getPFinal(combo.anchor) * 100).toFixed(1)}%
              </span>
              <span className={`q-anchor-ev ${combo.anchorEV > 0 ? 'ev-positive' : 'ev-negative'}`}>
                EV {fmtEV(combo.anchorEV)}
              </span>
            </div>
            <div className="q-legs">
              <span className="q-legs-label">腳</span>
              {combo.legs.map(({ row, pPair }) => (
                <div key={row.runner_id} className="q-leg">
                  <span className="q-leg-no">#{row.horse_no}</span>
                  <span className="q-leg-name">{row.horse_name}</span>
                  <span className="q-leg-prob">
                    P_pair {(pPair * 100).toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
            <div className="q-cost">
              {combo.legs.length} 注 &times; $10 = <strong>HKD {combo.totalCost}</strong>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function getPFinal(row: RaceRow): number {
  return row.prediction?.final_prob ?? 0
}

function DarkHorseCard({ darkHorses }: { darkHorses: DarkHorse[] }) {
  if (darkHorses.length === 0) return null
  return (
    <div className="betting-card dark-horse-card">
      <div className="betting-card-title">
        <span className="betting-icon">&#x1F4A5;</span>
        爆冷馬 Dark Horses
        <span className="betting-card-sub">模型排名 &le;5 市場排名 &gt;5</span>
      </div>
      <div className="betting-card-body">
        {darkHorses.map(({ row, modelRank, marketRank, ev, odds }) => (
          <div key={row.runner_id} className="dark-horse-row">
            <div className="dark-horse-horse">
              <span className="dark-horse-no">#{row.horse_no}</span>
              <span className="dark-horse-name">{row.horse_name}</span>
            </div>
            <div className="dark-horse-stats">
              <span className="dark-horse-odds">{odds.toFixed(0)}x</span>
              <span className="dark-horse-ev ev-positive">EV {fmtEV(ev)}</span>
            </div>
            <div className="dark-horse-ranks">
              <span className="rank-badge model-rank">模型 #{modelRank}</span>
              <span className="rank-badge market-rank">市場 #{marketRank}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function TrioCard({ trio }: { trio: TrioCombination | null }) {
  if (!trio) return null
  return (
    <div className="betting-card trio-card">
      <div className="betting-card-title">
        <span className="betting-icon">&#x1F3C6;</span>
        三重彩 Tierce
        <span className="betting-card-sub">首三名順序</span>
      </div>
      <div className="betting-card-body">
        <div className="trio-combo">
          {trio.horses.map((h, i) => (
            <div key={h.runner_id} className="trio-horse">
              <span className="trio-position">{i === 0 ? '冠' : i === 1 ? '亞' : '季'}</span>
              <span className="trio-no">#{h.horse_no}</span>
              <span className="trio-name">{h.horse_name}</span>
              <span className="trio-prob">P {(getPFinal(h) * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>
        <div className="trio-summary">
          <span>P_trio: {(trio.pTrio * 100).toFixed(2)}%</span>
          <span>估計賠率: ~{trio.estimatedOdds.toFixed(0)}x</span>
          <span>1 注 &times; $10 = <strong>HKD 10</strong></span>
        </div>
      </div>
    </div>
  )
}

function QuartetCard({ quartet }: { quartet: QuartetCombination | null }) {
  if (!quartet) return null
  return (
    <div className="betting-card quartet-card">
      <div className="betting-card-title">
        <span className="betting-icon">&#x1F3C5;</span>
        四連環 Quartet
        <span className="betting-card-sub">首四名任意順序</span>
      </div>
      <div className="betting-card-body">
        <div className="quartet-combo">
          {quartet.horses.map((h) => (
            <div key={h.runner_id} className="quartet-horse">
              <span className="quartet-no">#{h.horse_no}</span>
              <span className="quartet-name">{h.horse_name}</span>
              <span className="quartet-prob">{(getPFinal(h) * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>
        <div className="quartet-summary">
          <span>P_quartet: {(quartet.pQuartet * 100).toFixed(3)}%</span>
          <span>估計賠率: ~{quartet.estimatedOdds.toFixed(0)}x</span>
          <span>4 注 &times; $10 = <strong>HKD 40</strong></span>
        </div>
      </div>
    </div>
  )
}

function SummaryBar({ totalBet, overlays, underlays }: { totalBet: number; overlays: OverlayHorse[]; underlays: { row: RaceRow; ratio: number }[] }) {
  return (
    <div className="betting-summary">
      <div className="betting-summary-item">
        <span className="betting-summary-label">總建議注碼</span>
        <span className="betting-summary-value">HKD {totalBet}</span>
      </div>
      <div className="betting-summary-item">
        <span className="betting-summary-label">Overlay 冷門</span>
        <span className="betting-summary-value overlay-count">{overlays.length} 匹</span>
      </div>
      <div className="betting-summary-item">
        <span className="betting-summary-label">Underlay 過熱</span>
        <span className="betting-summary-value underlay-count">{underlays.length} 匹</span>
      </div>
    </div>
  )
}

export function BettingStrategy({ rows }: BettingStrategyProps) {
  const engine = runBettingEngine(rows)

  const hasAnyData = engine.winPoolValue || engine.qCombos.length > 0 || engine.overlays.length > 0 || engine.darkHorses.length > 0

  if (!hasAnyData) {
    return (
      <div className="betting-section animate-fade-in">
        <div className="betting-header">
          <span className="betting-badge">&#x1F4B0; 最佳實戰投注策略</span>
          <span className="betting-sublabel">Quant Betting Recommendations</span>
        </div>
        <div className="betting-empty">
          暫無投注策略數據（賠率尚未同步或無正 EV 馬匹）
        </div>
      </div>
    )
  }

  return (
    <div className="betting-section animate-fade-in">
      <div className="betting-header">
        <span className="betting-badge">&#x1F4B0; 最佳實戰投注策略</span>
        <span className="betting-sublabel">Benter Quant Betting Engine</span>
      </div>

      <SummaryBar
        totalBet={engine.totalRecommendedBet}
        overlays={engine.overlays}
        underlays={engine.underlays}
      />

      <div className="betting-grid">
        <OverlayCard overlays={engine.overlays} />
        <UnderlayCard underlays={engine.underlays} />
        <WinPlaceCard bets={engine.winBets} hasValue={engine.winPoolValue} />
        <QCard combos={engine.qCombos} />
        <DarkHorseCard darkHorses={engine.darkHorses} />
        <TrioCard trio={engine.trio} />
        <QuartetCard quartet={engine.quartet} />
      </div>
    </div>
  )
}
