'use client'

import { useState, useEffect } from 'react'
import { RaceDashboard } from './components/RaceDashboard'
import { AIPerformance } from './components/AIPerformance'
import { TrebleCard } from './components/TrebleCard'
import { PipelineControl } from './components/PipelineControl'
import { fetchLatestRaces, fetchAllRaceData } from '@/lib/supabase-client'
import { generateTreble, type TrebleResult } from '@/lib/treble-engine'
import { generateAllUp, type AllUpResult } from '@/lib/allup-engine'
import type { Race, RaceRow } from '@/lib/types'

type Tab = 'dashboard' | 'analysis'

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard')
  const [trebleData, setTrebleData] = useState<TrebleResult | null>(null)
  const [allUpData, setAllUpData] = useState<AllUpResult | null>(null)
  const [allRaceData, setAllRaceData] = useState<Map<string, RaceRow[]>>(new Map())
  const [races, setRaces] = useState<Race[]>([])

  useEffect(() => {
    let cancelled = false
    async function loadData() {
      try {
        const raceList = await fetchLatestRaces()
        if (cancelled) return
        setRaces(raceList)
        if (raceList.length < 3) return
        const allData = await fetchAllRaceData(raceList)
        if (cancelled) return
        setAllRaceData(allData)
        const treble = generateTreble(allData, raceList)
        if (cancelled) return
        setTrebleData(treble)
        const allUp = generateAllUp(allData, raceList)
        if (cancelled) return
        setAllUpData(allUp)
      } catch (e) {
        console.error('[Home] data fetch error:', e)
      }
    }
    loadData()
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

      {races.length > 0 && (
        <PipelineControl date={races[0].race_date} />
      )}

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

      {activeTab === 'dashboard' && <RaceDashboard races={races} allUpData={allUpData} allRaceData={allRaceData} />}
      {activeTab === 'analysis' && <AIPerformance />}
    </main>
  )
}
