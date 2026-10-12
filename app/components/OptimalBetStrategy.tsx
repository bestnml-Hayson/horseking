'use client'

import { useState, useEffect } from 'react'
import type { RaceRow, Race } from '@/lib/types'
import { calculateMultiPoolEV, type MultiPoolResult, type SingleRaceStrategy, type AllUpStrategy } from '@/lib/multi-pool-engine'

interface OptimalBetStrategyProps {
  rows: RaceRow[]
  raceData: Map<string, RaceRow[]>
  races: Race[]
  currentRace: Race
}

export function OptimalBetStrategy({ rows, raceData, races, currentRace }: OptimalBetStrategyProps) {
  const [result, setResult] = useState<MultiPoolResult | null>(null)
  const [activeTab, setActiveTab] = useState<'single' | 'high-reward' | 'allup'>('single')

  useEffect(() => {
    if (rows.length > 0 && raceData.size > 0) {
      const multiPoolResult = calculateMultiPoolEV(rows, raceData, races, currentRace)
      setResult(multiPoolResult)
    }
  }, [rows, raceData, races, currentRace])

  if (!result) {
    return (
      <div className="optimal-bet-strategy">
        <div className="obs-header">
          <span className="obs-badge">🎯 AI 最得益投注建議</span>
          <span className="obs-sublabel">Optimal Bet Strategy</span>
        </div>
        <div className="obs-loading">計算全彩池期望值...</div>
      </div>
    )
  }

  const { bestSingleStrategy, highRewardStrategy, bestAllUpStrategy } = result

  return (
    <div className="optimal-bet-strategy">
      <div className="obs-header">
        <span className="obs-badge">🎯 AI 最得益投注建議</span>
        <span className="obs-sublabel">Multi-Pool Value Maximizer</span>
      </div>

      {/* Tab Navigation */}
      <div className="obs-tabs">
        <button
          className={`obs-tab ${activeTab === 'single' ? 'active' : ''}`}
          onClick={() => setActiveTab('single')}
        >
          🏆 最佳單場策略
        </button>
        <button
          className={`obs-tab ${activeTab === 'high-reward' ? 'active' : ''}`}
          onClick={() => setActiveTab('high-reward')}
        >
          🚀 高倍爆發策略
        </button>
        <button
          className={`obs-tab ${activeTab === 'allup' ? 'active' : ''}`}
          onClick={() => setActiveTab('allup')}
          disabled={!bestAllUpStrategy}
        >
          🔗 跨場智選過關
        </button>
      </div>

      {/* Content */}
      <div className="obs-content">
        {activeTab === 'single' && bestSingleStrategy && (
          <SingleStrategyCard strategy={bestSingleStrategy} />
        )}

        {activeTab === 'high-reward' && highRewardStrategy && (
          <HighRewardCard strategy={highRewardStrategy} />
        )}

        {activeTab === 'allup' && bestAllUpStrategy && (
          <AllUpCard strategy={bestAllUpStrategy} />
        )}

        {activeTab === 'single' && !bestSingleStrategy && (
          <div className="obs-empty">
            本場無高期望值單場策略，建議觀望或考慮過關
          </div>
        )}

        {activeTab === 'high-reward' && !highRewardStrategy && (
          <div className="obs-empty">
            本場無高回報爆發機會
          </div>
        )}

        {activeTab === 'allup' && !bestAllUpStrategy && (
          <div className="obs-empty">
            跨場過關數據不足
          </div>
        )}
      </div>

      {/* Pool EV Summary */}
      <div className="obs-pool-summary">
        <div className="obs-summary-title">全彩池期望值分析</div>
        <div className="obs-pool-grid">
          {result.allPoolEVs
            .filter(ev => ev.recommended)
            .sort((a, b) => b.ev - a.ev)
            .slice(0, 6)
            .map((ev, idx) => (
              <div key={idx} className="obs-pool-item">
                <span className="obs-pool-name">{ev.poolName}</span>
                <span className="obs-pool-ev">EV +{(ev.ev * 100).toFixed(1)}%</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Sub-Components
// ============================================================================

function SingleStrategyCard({ strategy }: { strategy: SingleRaceStrategy }) {
  return (
    <div className="obs-strategy-card obs-single-card">
      <div className="obs-card-header">
        <span className="obs-strategy-type">🏆 最佳單場策略</span>
        <span className="obs-pool-badge">{strategy.poolName}</span>
      </div>

      <div className="obs-strategy-body">
        <div className="obs-metric-row">
          <div className="obs-metric">
            <span className="obs-metric-label">預期 EV</span>
            <span className="obs-metric-value positive">+{(strategy.ev * 100).toFixed(1)}%</span>
          </div>
          <div className="obs-metric">
            <span className="obs-metric-label">勝率</span>
            <span className="obs-metric-value">{(strategy.probability * 100).toFixed(1)}%</span>
          </div>
          <div className="obs-metric">
            <span className="obs-metric-label">估計賠率</span>
            <span className="obs-metric-value">{strategy.estimatedOdds.toFixed(1)}x</span>
          </div>
          <div className="obs-metric">
            <span className="obs-metric-label">建議注碼</span>
            <span className="obs-metric-value">HKD ${strategy.cost}</span>
          </div>
        </div>

        <div className="obs-horses">
          {strategy.horses.map((horse, idx) => (
            <div key={idx} className="obs-horse">
              <span className="obs-horse-role">{horse.role}</span>
              <span className="obs-horse-no">#{horse.horseNo}</span>
              <span className="obs-horse-name">{horse.horseName}</span>
            </div>
          ))}
        </div>

        <div className="obs-recommendation">
          {strategy.recommendation}
        </div>
      </div>
    </div>
  )
}

function HighRewardCard({ strategy }: { strategy: SingleRaceStrategy }) {
  return (
    <div className="obs-strategy-card obs-high-reward-card">
      <div className="obs-card-header">
        <span className="obs-strategy-type">🚀 高倍爆發策略</span>
        <span className="obs-pool-badge high-reward">{strategy.poolName}</span>
      </div>

      <div className="obs-strategy-body">
        <div className="obs-metric-row">
          <div className="obs-metric">
            <span className="obs-metric-label">預期 EV</span>
            <span className="obs-metric-value positive">+{(strategy.ev * 100).toFixed(1)}%</span>
          </div>
          <div className="obs-metric">
            <span className="obs-metric-label">勝率</span>
            <span className="obs-metric-value">{(strategy.probability * 100).toFixed(2)}%</span>
          </div>
          <div className="obs-metric">
            <span className="obs-metric-label">估計賠率</span>
            <span className="obs-metric-value high-odds">{strategy.estimatedOdds.toFixed(0)}x</span>
          </div>
          <div className="obs-metric">
            <span className="obs-metric-label">建議注碼</span>
            <span className="obs-metric-value">HKD ${strategy.cost}</span>
          </div>
        </div>

        <div className="obs-horses">
          {strategy.horses.map((horse, idx) => (
            <div key={idx} className="obs-horse">
              <span className="obs-horse-role">{horse.role}</span>
              <span className="obs-horse-no">#{horse.horseNo}</span>
              <span className="obs-horse-name">{horse.horseName}</span>
            </div>
          ))}
        </div>

        <div className="obs-recommendation">
          {strategy.recommendation}
        </div>
      </div>
    </div>
  )
}

function AllUpCard({ strategy }: { strategy: AllUpStrategy }) {
  return (
    <div className="obs-strategy-card obs-allup-card">
      <div className="obs-card-header">
        <span className="obs-strategy-type"> 跨場智選過關</span>
        <span className="obs-pool-badge allup">{strategy.recommendation}</span>
      </div>

      <div className="obs-strategy-body">
        <div className="obs-metric-row">
          <div className="obs-metric">
            <span className="obs-metric-label">組合 EV</span>
            <span className="obs-metric-value positive">+{(strategy.ev * 100).toFixed(1)}%</span>
          </div>
          <div className="obs-metric">
            <span className="obs-metric-label">組合勝率</span>
            <span className="obs-metric-value">{(strategy.combinedProbability * 100).toFixed(2)}%</span>
          </div>
          <div className="obs-metric">
            <span className="obs-metric-label">估計賠率</span>
            <span className="obs-metric-value high-odds">{strategy.estimatedOdds.toFixed(1)}x</span>
          </div>
          <div className="obs-metric">
            <span className="obs-metric-label">建議注碼</span>
            <span className="obs-metric-value">HKD ${strategy.cost}</span>
          </div>
        </div>

        <div className="obs-allup-legs">
          {strategy.legs.map((leg, idx) => (
            <div key={idx} className="obs-allup-leg">
              <span className="obs-leg-race">R{leg.raceNo}</span>
              <span className="obs-leg-type">{leg.betType === 'WIN' ? '獨贏' : '位置'}</span>
              <span className="obs-leg-horse">#{leg.horseNo} {leg.horseName}</span>
              <span className="obs-leg-prob">{(leg.pFinal * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
