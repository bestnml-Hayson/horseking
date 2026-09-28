'use client'

import type { Race, RaceRow } from '@/lib/types'
import { generateRaceAnalysis, getTopPicks } from '@/lib/race-utils'

interface AIRaceAnalysisProps {
  race: Race | undefined
  rows: RaceRow[]
}

export function AIRaceAnalysis({ race, rows }: AIRaceAnalysisProps) {
  if (rows.length === 0) return null

  const topPicks = getTopPicks(rows, 4)
  const analysis = generateRaceAnalysis(rows, race, topPicks)

  const impactIcon = (impact: string) => {
    if (impact === 'positive') return '\u2705'
    if (impact === 'negative') return '\u26A0\uFE0F'
    return '\u2139\uFE0F'
  }

  return (
    <div className="ai-analysis-section animate-fade-in">
      <div className="ai-analysis-header">
        <span className="ai-analysis-badge">&#x1F9E0; AI 賽事綜合分析</span>
        <span className="ai-analysis-sublabel">Benter Quant Race Analysis</span>
      </div>

      <div className="ai-analysis-grid">
        {/* Pace Analysis */}
        <div className="ai-analysis-card pace-card">
          <div className="ai-card-icon">&#x1F3C3;</div>
          <div className="ai-card-content">
            <div className="ai-card-label">預測步速</div>
            <div className="ai-card-value">{analysis.paceLabel}</div>
            <div className="ai-card-detail">{analysis.paceDetail}</div>
          </div>
        </div>

        {/* Key Factors */}
        <div className="ai-analysis-card factors-card">
          <div className="ai-card-icon">&#x1F511;</div>
          <div className="ai-card-content">
            <div className="ai-card-label">關鍵致勝因素</div>
            <div className="ai-factors-list">
              {analysis.keyFactors.length > 0 ? (
                analysis.keyFactors.map((f, i) => (
                  <div key={i} className={`ai-factor-item factor-${f.impact}`}>
                    <span className="factor-icon">{impactIcon(f.impact)}</span>
                    <span className="factor-text">{f.text}</span>
                  </div>
                ))
              ) : (
                <div className="ai-factor-item factor-neutral">
                  <span className="factor-icon">&#x2139;&#xFE0F;</span>
                  <span className="factor-text">本場無明顯特殊因素，以實力與賠率為主</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Model Logic */}
        <div className="ai-analysis-card logic-card">
          <div className="ai-card-icon">&#x1F4CA;</div>
          <div className="ai-card-content">
            <div className="ai-card-label">Benter 模型選馬邏輯</div>
            <div className="ai-card-detail logic-text">{analysis.modelLogic}</div>
            <div className="ai-model-legend">
              <span className="legend-item">
                <span className="legend-dot dot-model" />
                P_model = 模型評分
              </span>
              <span className="legend-item">
                <span className="legend-dot dot-market" />
                P_market = 市場賠率
              </span>
              <span className="legend-item">
                <span className="legend-dot dot-final" />
                P_final = 25% + 75% 融合
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
