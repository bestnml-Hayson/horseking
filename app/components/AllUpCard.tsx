'use client'

import { useState } from 'react'
import type { AllUpResult, AllUpStrategy } from '@/lib/allup-engine'

interface AllUpCardProps {
  result: AllUpResult
}

const riskColors: Record<string, string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  high: '#ef4444',
}

const riskLabels: Record<string, string> = {
  low: '低風險',
  medium: '中風險',
  high: '高風險',
}

const betTypeIcons: Record<string, string> = {
  'qp': '位置Q',
  'win': '獨贏',
  'q': '連贏Q',
}

function StrategyPanel({ strategy }: { strategy: AllUpStrategy }) {
  const riskColor = riskColors[strategy.riskLevel] || '#888'

  return (
    <div className={`allup-strategy allup-risk-${strategy.riskLevel}`}>
      <div className="allup-strat-header">
        <div className="allup-strat-title-row">
          <span className="allup-strat-name">{strategy.name}</span>
          <span className="allup-risk-badge" style={{ background: riskColor }}>
            {riskLabels[strategy.riskLevel]}
          </span>
        </div>
        <div className="allup-strat-desc">{strategy.description}</div>
        <div className="allup-bet-type-tag">{strategy.betType}</div>
      </div>

      <div className="allup-legs">
        {strategy.legs.map((leg, idx) => (
          <div key={leg.raceNo} className="allup-leg-wrapper">
            {idx > 0 && <div className="allup-cross">x</div>}
            <div className="allup-leg">
              <div className="allup-leg-header">
                <span className="allup-leg-race">R{leg.raceNo}</span>
                <span className="allup-leg-type">{betTypeIcons[leg.legType] || leg.legType}</span>
                <span className="allup-leg-prob">{(leg.legProb * 100).toFixed(1)}%</span>
              </div>
              <div className="allup-leg-horses">
                {leg.horses.map(h => (
                  <div key={h.horseNo} className={`allup-horse ${h.isFavorite ? 'allup-horse-fav' : 'allup-horse-cold'}`}>
                    <span className="allup-horse-no">#{h.horseNo}</span>
                    <span className="allup-horse-name">{h.horseName}</span>
                    <div className="allup-horse-stats">
                      <span className="allup-stat">
                        <span className="allup-stat-label">P</span>
                        <span className="allup-stat-val">{(h.pFinal * 100).toFixed(1)}%</span>
                      </span>
                      <span className="allup-stat">
                        <span className="allup-stat-label">賠</span>
                        <span className={`allup-stat-val ${h.odds >= 12 ? 'allup-odds-high' : ''}`}>{h.odds.toFixed(1)}</span>
                      </span>
                      {h.ev > 0 && (
                        <span className="allup-stat">
                          <span className="allup-stat-label">EV</span>
                          <span className="allup-stat-val allup-ev-pos">+{(h.ev * 100).toFixed(1)}%</span>
                        </span>
                      )}
                    </div>
                    {h.isFavorite && <span className="allup-role-tag allup-role-fav">膽</span>}
                    {!h.isFavorite && leg.legType === 'q' && <span className="allup-role-tag allup-role-cold">腳</span>}
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="allup-summary">
        <div className="allup-summary-item">
          <span className="allup-summary-label">涵蓋率</span>
          <span className="allup-summary-val">{(strategy.compositeProb * 100).toFixed(2)}%</span>
        </div>
        <div className="allup-summary-item">
          <span className="allup-summary-label">預估賠率</span>
          <span className="allup-summary-val allup-odds-big">{strategy.estimatedOdds.toFixed(1)}</span>
        </div>
        <div className="allup-summary-item">
          <span className="allup-summary-label">Kelly (1/4)</span>
          <span className="allup-summary-val">{(strategy.kellyFraction * 100).toFixed(2)}%</span>
        </div>
        <div className="allup-summary-item">
          <span className="allup-summary-label">建議注碼</span>
          <span className="allup-summary-val">${strategy.suggestedStake.toFixed(1)}</span>
        </div>
      </div>
    </div>
  )
}

export function AllUpCard({ result }: AllUpCardProps) {
  const [activeTab, setActiveTab] = useState(0)

  if (!result.strategies || result.strategies.length === 0) return null

  const active = result.strategies[activeTab]

  return (
    <div className="allup-card animate-fade-in">
      <div className="allup-header">
        <span className="allup-icon">&#x1F680;</span>
        <div>
          <div className="allup-title">AI 智選過關建議</div>
          <div className="allup-sub">All Up Optimization Engine &middot; {result.strategies.length} 種策略</div>
        </div>
      </div>

      <div className="allup-tabs">
        {result.strategies.map((s, i) => (
          <button
            key={s.id}
            className={`allup-tab ${i === activeTab ? 'allup-tab-active' : ''}`}
            onClick={() => setActiveTab(i)}
          >
            <span className="allup-tab-name">{s.nameShort}</span>
            <span className="allup-tab-risk" style={{ background: riskColors[s.riskLevel] }}>
              {riskLabels[s.riskLevel]}
            </span>
          </button>
        ))}
      </div>

      {active && <StrategyPanel strategy={active} />}
    </div>
  )
}
