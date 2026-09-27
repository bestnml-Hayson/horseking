'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { fetchLatestRaces, fetchRaceRunners, fetchPredictions, fetchHorses } from '@/lib/supabase-client'
import type { Race, RaceRunner, ModelPrediction, Horse, RaceRow } from '@/lib/types'
import { RaceTable } from './RaceTable'
import { SkeletonTable } from './SkeletonTable'

const REFRESH_INTERVAL = 15000
const VALUE_THRESHOLD = 0.15

interface StatCardProps {
  label: string
  value: string
  sub?: string
  color?: 'blue' | 'green' | 'amber' | 'purple'
  icon: string
}

function StatCard({ label, value, sub, color = 'blue', icon }: StatCardProps) {
  return (
    <div className={`stat-card ${color} animate-fade-in`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
            {label}
          </div>
          <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
            {value}
          </div>
          {sub && (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
              {sub}
            </div>
          )}
        </div>
        <div style={{ fontSize: 24, opacity: 0.6 }}>{icon}</div>
      </div>
    </div>
  )
}

function computeKPIs(rows: RaceRow[]) {
  const withPred = rows.filter(r => r.prediction?.final_prob != null)
  if (withPred.length === 0) return { winRate: 0, top3Rate: 0, valueBets: 0, bestEV: 0 }

  const sorted = [...withPred].sort((a, b) => (b.prediction!.final_prob! - a.prediction!.final_prob!))
  const topPick = sorted[0]
  const top3 = sorted.slice(0, 3)

  const winRate = topPick ? topPick.prediction!.final_prob! * 100 : 0
  const top3Rate = top3.reduce((sum, r) => sum + (r.prediction!.final_prob! * 100), 0)
  const valueBets = withPred.filter(r => {
    const ev = r.prediction!.expected_value!
    const kelly = r.prediction!.kelly_fraction
    return ev > VALUE_THRESHOLD && kelly != null && kelly > 0
  }).length
  const bestEV = Math.max(...withPred.map(r => r.prediction!.expected_value!)) * 100

  return { winRate, top3Rate, valueBets, bestEV }
}

function generateBriefing(rows: RaceRow[], race: Race | undefined): string {
  if (rows.length === 0) return ''
  const withPred = rows.filter(r => r.prediction?.final_prob != null)
  if (withPred.length === 0) return 'Benter 模型尚未完成此場分析。'

  const sorted = [...withPred].sort((a, b) => b.prediction!.final_prob! - a.prediction!.final_prob!)
  const topPick = sorted[0]
  const valueBets = sorted.filter(r => {
    const ev = r.prediction!.expected_value!
    const kelly = r.prediction!.kelly_fraction
    return ev > VALUE_THRESHOLD && kelly != null && kelly > 0
  })

  const bestValue = valueBets.length > 0 ? valueBets[0] : null
  const longshot = sorted.filter(r => r.prediction!.final_prob! < 0.05).sort((a, b) => b.prediction!.expected_value! - a.prediction!.expected_value!)[0]

  let briefing = `AI 首選：${topPick.horse_name}（${(topPick.prediction!.final_prob! * 100).toFixed(1)}% 勝率模型評分最高）`

  if (bestValue) {
    briefing += `。最佳價值投注：${bestValue.horse_name}（EV +${(bestValue.prediction!.expected_value! * 100).toFixed(1)}%，Kelly 正期望）`
  }

  if (longshot && longshot.runner_id !== topPick.runner_id) {
    briefing += `。冷門警示：${longshot.horse_name} 模型評分僅 ${(longshot.prediction!.final_prob! * 100).toFixed(1)}%，但 EV 異常偏高，留意市場異動。`
  }

  return briefing
}

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
  const kpis = useMemo(() => computeKPIs(rows), [rows])
  const briefing = useMemo(() => generateBriefing(rows, selectedRace), [rows, selectedRace])

  const topPickHorse = useMemo(() => {
    const withPred = rows.filter(r => r.prediction?.final_prob != null)
    if (withPred.length === 0) return null
    return withPred.sort((a, b) => b.prediction!.final_prob! - a.prediction!.final_prob!)[0]
  }, [rows])

  const venueLabel = selectedRace?.venue === 'ST' ? '沙田' : selectedRace?.venue === 'HV' ? '跑馬地' : selectedRace?.venue ?? ''

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Race Selector Header */}
      <div className="animate-fade-in" style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-primary)',
        borderRadius: 16,
        padding: '16px 24px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              fontSize: 14,
              fontWeight: 700,
              color: 'var(--text-primary)',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}>
              <span style={{ fontSize: 18 }}>&#x1F3C7;</span>
              {venueLabel} {selectedRace?.race_date}
            </div>
            <span className="status-dot live" title="Live sync active" />
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              {lastUpdate ? `Updated ${lastUpdate.toLocaleTimeString('zh-HK')}` : 'Connecting...'}
            </span>
          </div>
          <button
            onClick={() => selectedRaceId && loadRaceData(selectedRaceId)}
            disabled={loading}
            style={{
              padding: '6px 14px',
              borderRadius: 8,
              border: '1px solid var(--border-secondary)',
              background: 'var(--bg-elevated)',
              color: 'var(--text-secondary)',
              cursor: loading ? 'wait' : 'pointer',
              fontSize: 12,
              fontWeight: 600,
              transition: 'all 0.2s',
            }}
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
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
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>No races found</span>
          )}
        </div>
      </div>

      {/* Race Info Bar */}
      {selectedRace && (
        <div className="animate-fade-in" style={{
          display: 'flex',
          gap: 16,
          fontSize: 13,
          color: 'var(--text-secondary)',
          flexWrap: 'wrap',
        }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: 'var(--text-muted)' }}>Distance:</span>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedRace.distance ?? '?'}m</span>
          </span>
          <span style={{ color: 'var(--border-secondary)' }}>|</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: 'var(--text-muted)' }}>Class:</span>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedRace.class_level ?? '-'}</span>
          </span>
          <span style={{ color: 'var(--border-secondary)' }}>|</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: 'var(--text-muted)' }}>Going:</span>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedRace.going ?? '-'}</span>
          </span>
          <span style={{ color: 'var(--border-secondary)' }}>|</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: 'var(--text-muted)' }}>Runners:</span>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{rows.length}</span>
          </span>
        </div>
      )}

      {/* AI KPI Stat Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: 16,
      }}>
        <StatCard
          label="AI Win Rate"
          value={`${kpis.winRate.toFixed(1)}%`}
          sub={topPickHorse ? `Top Pick: ${topPickHorse.horse_name}` : 'No data'}
          color="blue"
          icon="&#x1F3AF;"
        />
        <StatCard
          label="Top-3 Probability"
          value={`${kpis.top3Rate.toFixed(1)}%`}
          sub="Combined Q-place model"
          color="purple"
          icon="&#x1F4CA;"
        />
        <StatCard
          label="Value Bets"
          value={`${kpis.valueBets}`}
          sub={`Best EV: +${kpis.bestEV.toFixed(1)}%`}
          color="green"
          icon="&#x1F4B0;"
        />
        <StatCard
          label="Races Analyzed"
          value={`${races.length}`}
          sub={`${venueLabel} ${selectedRace?.race_date ?? ''}`}
          color="amber"
          icon="&#x1F9E0;"
        />
      </div>

      {/* AI Decision Briefing */}
      {briefing && (
        <div className="briefing-card animate-fade-in">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '4px 10px',
              borderRadius: 9999,
              background: 'rgba(59, 130, 246, 0.12)',
              color: '#93c5fd',
              fontSize: 11,
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}>
              AI Decision Briefing
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              R{selectedRace?.race_no} / {rows.length} runners
            </span>
          </div>
          <p style={{
            fontSize: 14,
            lineHeight: 1.7,
            color: 'var(--text-secondary)',
            margin: 0,
          }}>
            {briefing}
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          padding: 16,
          borderRadius: 12,
          background: 'rgba(239, 68, 68, 0.08)',
          border: '1px solid rgba(239, 68, 68, 0.2)',
          color: '#fca5a5',
          fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {/* Data Table */}
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-primary)',
        borderRadius: 16,
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--border-primary)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
            Full Analysis
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Sorted by P_final (model probability)
          </span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          {loading && rows.length === 0 ? <SkeletonTable /> : <RaceTable rows={rows} topPickId={topPickHorse?.runner_id ?? null} />}
        </div>
      </div>
    </div>
  )
}
