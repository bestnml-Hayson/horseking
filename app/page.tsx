'use client'

import { useState } from 'react'
import { RaceDashboard } from './components/RaceDashboard'
import { AIPerformance } from './components/AIPerformance'

type Tab = 'dashboard' | 'analysis'

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard')

  return (
    <main className="app-root">
      <header className="app-header">
        <div className="app-header-left">
          <h1 className="app-title">
            <span className="app-title-icon">&#x1F3C7;</span>
            賽馬 AI Live
          </h1>
          <span className="app-version">QUANT ENGINE v3.0</span>
        </div>
        <div className="app-header-sub">
          Benter 量化分析 Dashboard &mdash; Softmax Multinomial Logit + Market Odds Fusion + 1/4 Kelly Criterion
        </div>
      </header>

      <nav className="app-tabs">
        <button
          className={`app-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
        >
          <span className="tab-icon">&#x1F3C7;</span>
          賽事分析
        </button>
        <button
          className={`app-tab ${activeTab === 'analysis' ? 'active' : ''}`}
          onClick={() => setActiveTab('analysis')}
        >
          <span className="tab-icon">&#x1F4CA;</span>
          AI 復盤
        </button>
      </nav>

      {activeTab === 'dashboard' && <RaceDashboard />}
      {activeTab === 'analysis' && <AIPerformance />}
    </main>
  )
}
