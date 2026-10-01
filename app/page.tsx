'use client'

import { useState, useEffect } from 'react'
import { RaceDashboard } from './components/RaceDashboard'
import { AIPerformance } from './components/AIPerformance'
import { TrebleCard } from './components/TrebleCard'
import { fetchLatestRaces, fetchAllRaceData } from '@/lib/supabase-client'
import { generateTreble, type TrebleResult } from '@/lib/treble-engine'
import type { Race } from '@/lib/types'

type Tab = 'dashboard' | 'analysis'

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard')
  const [trebleData, setTrebleData] = useState<TrebleResult | null>(null)
  const [races, setRaces] = useState<Race[]>([])

  useEffect(() => {
    let cancelled = false
    async function loadTreble() {
      try {
        const raceList = await fetchLatestRaces()
        if (cancelled) return
        setRaces(raceList)
        if (raceList.length < 3) return
        const allData = await fetchAllRaceData(raceList)
        if (cancelled) return
        const result = generateTreble(allData, raceList)
        if (cancelled) return
        setTrebleData(result)
      } catch (e) {
        console.error('[Home] treble fetch error:', e)
      }
    }
    loadTreble()
    return () => { cancelled = true }
  }, [])

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
        {trebleData && <TrebleCard treble={trebleData} />}
      </nav>

      {activeTab === 'dashboard' && <RaceDashboard races={races} />}
      {activeTab === 'analysis' && <AIPerformance />}
    </main>
  )
}
