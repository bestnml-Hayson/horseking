'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { fetchRaceRunners, fetchPredictions, fetchHorses, fetchRecentForm } from '@/lib/supabase-client'
import type { Race, RaceRunner, ModelPrediction, Horse, RaceRow } from '@/lib/types'
import { getTopPicks, estimateRaceTime, predictPace, isOddsPending, computeClientPredictions, recomputePFusion } from '@/lib/race-utils'
import { PacingBriefing } from './PacingBriefing'
import { AIRaceAnalysis } from './AIRaceAnalysis'
import { TopPicksCards } from './TopPicksCards'
import { BettingStrategy } from './BettingStrategy'
import { RaceTable } from './RaceTable'
import { SkeletonTable } from './SkeletonTable'
import { HorseDetailDrawer } from './HorseDetailDrawer'
import { LongshotCard } from './LongshotCard'
import { generateLongshotStrategy } from '@/lib/longshot-engine'

const REFRESH_INTERVAL = 15000

interface RaceDashboardProps {
  races: Race[]
}

export function RaceDashboard({ races }: RaceDashboardProps) {
  const [selectedRaceId, setSelectedRaceId] = useState<string | null>(null)
  const [rows, setRows] = useState<RaceRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [drawerHorseId, setDrawerHorseId] = useState<string | null>(null)
  const [drawerHorseName, setDrawerHorseName] = useState<string>('')
  const [drawerRaceRow, setDrawerRaceRow] = useState<RaceRow | null>(null)

  const loadRaceData = useCallback(async (raceId: string) => {
    setLoading(true)
    setError(null)
    try {
      const [runners, predictions] = await Promise.all([
        fetchRaceRunners(raceId),
        fetchPredictions(raceId),
      ])

      const horseMap = new Map<string, Horse>()
      if (runners.length > 0) {
        const horseIds = Array.from(new Set(runners.map(r => r.horse_id)))
        const fetchedHorses = await fetchHorses(horseIds)
        fetchedHorses.forEach(h => horseMap.set(h.horse_id, h))
      }

      const predMap = new Map<string, ModelPrediction>()
      predictions.forEach(p => predMap.set(p.runner_id, p))

      let raceRows: RaceRow[] = runners.map(r => ({
        ...r,
        horse_name: horseMap.get(r.horse_id)?.horse_name ?? r.horse_id,
        prediction: predMap.get(r.runner_id) ?? null,
      }))

      // Fetch recent form from race_results to populate form_history
      const horseIds = Array.from(new Set(runners.map(r => r.horse_id)))
      const formMap = await fetchRecentForm(horseIds)
      raceRows = raceRows.map(r => {
        const formFromResults = formMap.get(r.horse_id)
        if (formFromResults) {
          return { ...r, form_history: formFromResults }
        }
        return r
      })

      const noPredictions = predictions.length === 0
      const allMarketNull = !noPredictions && predictions.every(p => p.market_implied_prob == null)

      if ((noPredictions || allMarketNull) && raceRows.length > 0) {
        console.log('[RaceDashboard] Predictions missing or incomplete, computing client-side fallback')
        raceRows = computeClientPredictions(raceRows)
      } else if (raceRows.length > 0) {
        raceRows = recomputePFusion(raceRows)
      }

      setRows(raceRows)
      setLastUpdate(new Date())
    } catch (e: unknown) {
      console.error('[RaceDashboard] loadRaceData error:', e)
      const msg = e instanceof Error ? e.message : 'Failed to load race data'
      setError(msg)
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (races.length > 0 && !selectedRaceId) {
      setSelectedRaceId(races[0].race_id)
    }
    if (races.length === 0) {
      setLoading(false)
    }
  }, [races, selectedRaceId])

  useEffect(() => {
    if (selectedRaceId) {
      loadRaceData(selectedRaceId)
    }
  }, [selectedRaceId, loadRaceData])

  useEffect(() => {
    const timer = setInterval(() => {
      if (selectedRaceId) {
        loadRaceData(selectedRaceId)
      }
    }, REFRESH_INTERVAL)
    return () => clearInterval(timer)
  }, [selectedRaceId, loadRaceData])

  const selectedRace = races.find(r => r.race_id === selectedRaceId)
  const topPicks = useMemo(() => getTopPicks(rows, 4), [rows])
  const topPickId = useMemo(() => {
    if (topPicks.length === 0) return null
    const best = topPicks[0]
    const ev = best.prediction?.expected_value ?? 0
    return ev > 0 ? best.runner_id : null
  }, [topPicks])
  const hasPositiveEV = useMemo(() => rows.some(r => (r.prediction?.expected_value ?? 0) > 0), [rows])
  const longshotResult = useMemo(() => generateLongshotStrategy(rows), [rows])
  const paceInfo = useMemo(() => predictPace(rows), [rows])

  const handleHorseClick = useCallback((horseId: string, horseName: string) => {
    setDrawerHorseId(horseId)
    setDrawerHorseName(horseName)
    const match = rows.find(r => r.horse_id === horseId)
    setDrawerRaceRow(match ?? null)
  }, [rows])

  const handleCloseDrawer = useCallback(() => {
    setDrawerHorseId(null)
    setDrawerHorseName('')
    setDrawerRaceRow(null)
  }, [])

  const venueLabel = selectedRace?.venue === 'ST' ? '沙田' : selectedRace?.venue === 'HV' ? '跑馬地' : selectedRace?.venue ?? ''
  const surfaceLabel = '草地'

  const oddsReady = rows.length > 0 ? rows.filter(r => !isOddsPending(r.win_odds)).length : 0
  const oddsTotal = rows.length
  const oddsAllReady = oddsTotal > 0 && oddsReady === oddsTotal

  const selectedRaceTime = selectedRace?.race_time ?? estimateRaceTime(selectedRace?.venue, selectedRace?.race_no ?? 1, selectedRace?.race_date)

  return (
    <div className="dashboard-root">
      {/* Race Selector Header */}
      <div className="race-selector animate-fade-in">
        <div className="race-selector-top">
          <div className="race-selector-title">
            <span className="race-icon">&#x1F3C7;</span>
            <span>{venueLabel} {selectedRace?.race_date ?? ''}</span>
            <span className="status-dot live" title="Live" />
            <span className="race-selector-time">
              {lastUpdate ? `Updated ${lastUpdate.toLocaleTimeString('zh-HK')}` : 'Connecting...'}
            </span>
          </div>
          <button
            onClick={() => selectedRaceId && loadRaceData(selectedRaceId)}
            disabled={loading}
            className="refresh-btn"
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>

        <div className="race-pills">
          {races.map(race => {
            const raceTime = race.race_time ?? estimateRaceTime(race.venue, race.race_no, race.race_date)
            return (
              <button
                key={race.race_id}
                className={`race-pill ${race.race_id === selectedRaceId ? 'active' : ''}`}
                onClick={() => setSelectedRaceId(race.race_id)}
              >
                <span className="pill-race-no">R{race.race_no}</span>
                <span className="pill-race-time">{raceTime}</span>
              </button>
            )
          })}
          {races.length === 0 && !loading && (
            <span className="no-races-text">No races found</span>
          )}
        </div>
      </div>

      {/* Race Info Bar */}
      {selectedRace && (
        <div className="race-info-bar animate-fade-in">
          <span className="race-info-item race-time-highlight">
            <span className="race-info-label">&#x23F0; 開跑時間</span>
            <span className="race-info-value race-time-value">{selectedRaceTime}</span>
          </span>
          <span className="race-info-sep">|</span>
          <span className="race-info-item">
            <span className="race-info-label">場地</span>
            <span className="race-info-value">{venueLabel} {surfaceLabel}</span>
          </span>
          <span className="race-info-sep">|</span>
          <span className="race-info-item">
            <span className="race-info-label">路程</span>
            <span className="race-info-value">{selectedRace.distance ?? '?'}m</span>
          </span>
          <span className="race-info-sep">|</span>
          <span className="race-info-item">
            <span className="race-info-label">班次</span>
            <span className="race-info-value">{selectedRace.class_level ?? '-'}</span>
          </span>
          <span className="race-info-sep">|</span>
          <span className="race-info-item">
            <span className="race-info-label">場地狀況</span>
            <span className="race-info-value">{selectedRace.going ?? '-'}</span>
          </span>
          <span className="race-info-sep">|</span>
          <span className="race-info-item">
            <span className="race-info-label">出賽馬匹</span>
            <span className="race-info-value">{rows.length} 匹</span>
          </span>
          <span className="race-info-sep">|</span>
          <span className="race-info-item">
            <span className="race-info-label">即時賠率</span>
            <span className={`race-info-value ${oddsAllReady ? 'odds-status-ready' : 'odds-status-pending'}`}>
              {oddsAllReady ? '✓ 已同步' : `${oddsReady}/${oddsTotal} 已同步`}
            </span>
          </span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {/* Section 1: Pacing Briefing */}
      <PacingBriefing race={selectedRace} rows={rows} />

      {/* Section 2: AI Race Analysis (NEW) */}
      <AIRaceAnalysis race={selectedRace} rows={rows} />

      {/* Section 3: AI Top 4 Picks */}
      <TopPicksCards picks={topPicks} totalRunners={rows.length} paceLabel={paceInfo.label} onHorseClick={handleHorseClick} />

      {/* Section 4: Betting Strategy */}
      <BettingStrategy rows={rows} />

      {/* Section 4b: Longshot Overlay Strategy */}
      {longshotResult && <LongshotCard result={longshotResult} onHorseClick={handleHorseClick} />}

      {/* Section 5: Full Analysis Table */}
      <div className="full-table-section animate-fade-in">
        <div className="full-table-header">
          <span className="full-table-title">
            &#x1F4CA; 全馬匹 Benter 模型精算數據
          </span>
          <span className="full-table-sub">
            P_model (模型評分) × P_market (市場賠率) → P_final (50% 線性融合) · Sorted by P_final
          </span>
        </div>
        <div className="full-table-body">
          {loading && rows.length === 0 ? <SkeletonTable /> : <RaceTable rows={rows} topPickId={topPickId} hasPositiveEV={hasPositiveEV} onHorseClick={handleHorseClick} />}
        </div>
      </div>

      <HorseDetailDrawer
        horseId={drawerHorseId}
        horseName={drawerHorseName}
        raceRow={drawerRaceRow}
        onClose={handleCloseDrawer}
      />
    </div>
  )
}
