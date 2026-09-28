'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { fetchLatestRaces, fetchRaceRunners, fetchPredictions, fetchHorses } from '@/lib/supabase-client'
import type { Race, RaceRunner, ModelPrediction, Horse, RaceRow } from '@/lib/types'
import { getTopPicks, computeAIScore } from '@/lib/race-utils'
import { PacingBriefing } from './PacingBriefing'
import { TopPicksCards } from './TopPicksCards'
import { BettingStrategy } from './BettingStrategy'
import { RaceTable } from './RaceTable'
import { SkeletonTable } from './SkeletonTable'

const REFRESH_INTERVAL = 15000

export function RaceDashboard() {
  const [races, setRaces] = useState<Race[]>([])
  const [selectedRaceId, setSelectedRaceId] = useState<string | null>(null)
  const [rows, setRows] = useState<RaceRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

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

      const raceRows: RaceRow[] = runners.map(r => ({
        ...r,
        horse_name: horseMap.get(r.horse_id)?.horse_name ?? r.horse_id,
        prediction: predMap.get(r.runner_id) ?? null,
      }))

      setRows(raceRows)
      setLastUpdate(new Date())
    } catch (e: any) {
      console.error('[RaceDashboard] loadRaceData error:', e)
      setError(e.message ?? 'Failed to load race data')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function init() {
      try {
        const data = await fetchLatestRaces()
        if (cancelled) return
        setRaces(data)
        if (data.length > 0) {
          setSelectedRaceId(data[0].race_id)
        } else {
          setLoading(false)
        }
      } catch (e: any) {
        if (cancelled) return
        setError(e.message ?? 'Failed to load races')
        setLoading(false)
      }
    }
    init()
    return () => { cancelled = true }
  }, [])

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
  const topPickId = topPicks.length > 0 ? topPicks[0].runner_id : null

  const venueLabel = selectedRace?.venue === 'ST' ? '沙田' : selectedRace?.venue === 'HV' ? '跑馬地' : selectedRace?.venue ?? ''

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
          {races.map(race => (
            <button
              key={race.race_id}
              className={`race-pill ${race.race_id === selectedRaceId ? 'active' : ''}`}
              onClick={() => setSelectedRaceId(race.race_id)}
            >
              R{race.race_no}
            </button>
          ))}
          {races.length === 0 && !loading && (
            <span className="no-races-text">No races found</span>
          )}
        </div>
      </div>

      {/* Race Info Bar */}
      {selectedRace && (
        <div className="race-info-bar animate-fade-in">
          <span className="race-info-item">
            <span className="race-info-label">Distance</span>
            <span className="race-info-value">{selectedRace.distance ?? '?'}m</span>
          </span>
          <span className="race-info-sep">|</span>
          <span className="race-info-item">
            <span className="race-info-label">Class</span>
            <span className="race-info-value">{selectedRace.class_level ?? '-'}</span>
          </span>
          <span className="race-info-sep">|</span>
          <span className="race-info-item">
            <span className="race-info-label">Going</span>
            <span className="race-info-value">{selectedRace.going ?? '-'}</span>
          </span>
          <span className="race-info-sep">|</span>
          <span className="race-info-item">
            <span className="race-info-label">Runners</span>
            <span className="race-info-value">{rows.length}</span>
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

      {/* Section 2: AI Top 4 Picks */}
      <TopPicksCards picks={topPicks} />

      {/* Section 3: Betting Strategy */}
      <BettingStrategy rows={rows} />

      {/* Section 4: Full Analysis Table */}
      <div className="full-table-section animate-fade-in">
        <div className="full-table-header">
          <span className="full-table-title">
            &#x1F4CA; 全馬匹模型精算數據
          </span>
          <span className="full-table-sub">
            Sorted by P_win (model probability)
          </span>
        </div>
        <div className="full-table-body">
          {loading && rows.length === 0 ? <SkeletonTable /> : <RaceTable rows={rows} topPickId={topPickId} />}
        </div>
      </div>
    </div>
  )
}
