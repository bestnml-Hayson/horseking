'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { HorseDetailDrawer } from './HorseDetailDrawer'
import type { ComparisonRow, Race, RaceResult, AIPerformanceRecord } from '@/lib/types'

interface PerfSummary {
  win_rate: number
  top3_rate: number
  avg_roi: number
  total_bets: number
  total_returns: number
  top1_hits: number
  top3_total_hits: number
}

interface PerfRecord {
  race_id: string
  analysis_date: string
  top1_pick_runner_id: string
  top1_pick_finish_pos: number
  top1_hit: boolean
  top3_hit_count: number
  total_bets: number
  total_returns: number
  roi_percent: number
  pace_analysis: string
  draw_bias: string
  market_move: string
}

interface KeyFactor {
  type: string
  description: string
  impact: string
}

interface RaceDetail {
  ok: boolean
  race_id: string
  race_info: Race | null
  results: RaceResult[] | null
  performance: AIPerformanceRecord
  comparison: ComparisonRow[]
  key_factors: KeyFactor[]
  top3_picks: unknown[]
}

export function AIPerformance() {
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<PerfSummary | null>(null)
  const [records, setRecords] = useState<PerfRecord[]>([])
  const [selectedRaceId, setSelectedRaceId] = useState<string | null>(null)
  const [raceDetail, setRaceDetail] = useState<RaceDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [availableDates, setAvailableDates] = useState<string[]>([])
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [tableMissing, setTableMissing] = useState(false)
  const [drawerHorseId, setDrawerHorseId] = useState<string | null>(null)
  const [drawerHorseName, setDrawerHorseName] = useState('')

  const datesFetchedRef = useRef(false)
  const summaryFetchedRef = useRef<string | null>(null)
  const detailFetchedRef = useRef<string | null>(null)

  const fetchDates = useCallback(async () => {
    if (datesFetchedRef.current) return
    datesFetchedRef.current = true
    try {
      const res = await fetch('/api/performance/dates')
      const json = await res.json()
      if (json.ok && json.dates?.length > 0) {
        setAvailableDates(json.dates)
        setSelectedDate(json.dates[0])
      }
    } catch (e: unknown) {
      console.error('Failed to fetch dates:', e)
    }
  }, [])

  const fetchSummary = useCallback(async (date: string) => {
    if (summaryFetchedRef.current === date) return
    summaryFetchedRef.current = date
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/performance?date=${date}`)
      const json = await res.json()
      if (json.ok) {
        setSummary(json.summary)
        setRecords(json.records ?? [])
        setTableMissing(!!json.table_missing)
        setRaceDetail(null)
        detailFetchedRef.current = null
        if (json.records?.length > 0) {
          setSelectedRaceId(json.records[0].race_id)
        } else {
          setSelectedRaceId(null)
        }
      } else {
        setError(json.error ?? 'Failed to load performance data')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Network error'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchRaceDetail = useCallback(async (raceId: string) => {
    if (detailFetchedRef.current === raceId) return
    detailFetchedRef.current = raceId
    setDetailLoading(true)
    try {
      const res = await fetch(`/api/performance/${raceId}`)
      const json = await res.json()
      if (json.ok) {
        setRaceDetail(json)
      } else {
        setRaceDetail(null)
      }
    } catch {
      setRaceDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDates()
  }, [fetchDates])

  useEffect(() => {
    if (selectedDate) {
      fetchSummary(selectedDate)
    }
  }, [selectedDate, fetchSummary])

  useEffect(() => {
    if (selectedRaceId) {
      fetchRaceDetail(selectedRaceId)
    }
  }, [selectedRaceId, fetchRaceDetail])

  const allRaceIds = Array.from(new Set(records.map(r => r.race_id)))

  return (
    <div className="ai-perf-root">
      {/* KPI Header with compact date selector */}
      <div className="perf-kpi-section animate-fade-in">
        <div className="perf-section-header">
          <div className="perf-header-left">
            <span className="perf-badge ai-badge">AI</span>
            <span className="perf-badge-label">歷史預測準確度</span>
            <span className="perf-sublabel">Post-Race Performance Analysis</span>
          </div>
          {availableDates.length > 0 && (
            <div className="perf-date-select-wrap">
              <label className="perf-date-select-label">&#x1F4C5;</label>
              <select
                className="perf-date-select"
                value={selectedDate ?? ''}
                onChange={(e) => setSelectedDate(e.target.value)}
              >
                {availableDates.map(date => (
                  <option key={date} value={date}>{date}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {loading ? (
          <div className="perf-kpi-loading">載入中...</div>
        ) : tableMissing ? (
          <div className="perf-empty">
            <div className="perf-empty-icon">&#x1F4CA;</div>
            <div>尚未建立分析數據表</div>
            <div className="perf-empty-sub">
              請先在 Supabase SQL Editor 執行 migrations/add_race_results_and_ai_performance.sql
            </div>
          </div>
        ) : !summary || (summary.top1_hits === 0 && summary.top3_total_hits === 0 && records.length === 0) ? (
          <div className="perf-empty">
            <div className="perf-empty-icon">&#x1F4CA;</div>
            <div>暫無歷史分析數據</div>
            <div className="perf-empty-sub">完成賽事後執行 post_race_analyzer.py 即可生成數據</div>
          </div>
        ) : (
          <div className="perf-kpi-grid">
            <KPICard
              label="獨贏命中率"
              value={`${summary.win_rate.toFixed(1)}%`}
              sub={`${summary.top1_hits} / ${records.length} 場`}
              color={summary.win_rate > 0 ? 'green' : 'red'}
              icon="&#x1F3AF;"
            />
            <KPICard
              label="前三命中率"
              value={`${summary.top3_rate.toFixed(1)}%`}
              sub={`${summary.top3_total_hits} / ${records.length * 3} 匹`}
              color={summary.top3_rate > 0 ? 'green' : 'red'}
              icon="&#x1F3C6;"
            />
            <KPICard
              label="平均 ROI"
              value={`${summary.avg_roi >= 0 ? '+' : ''}${summary.avg_roi.toFixed(1)}%`}
              sub={`總投注 $${summary.total_bets.toLocaleString()}`}
              color={summary.avg_roi >= 0 ? 'green' : 'red'}
              icon="&#x1F4B0;"
            />
            <KPICard
              label="總回報"
              value={`$${summary.total_returns.toLocaleString()}`}
              sub={`淨${summary.total_returns - summary.total_bets >= 0 ? '+' : ''}$${(summary.total_returns - summary.total_bets).toLocaleString()}`}
              color={summary.total_returns >= summary.total_bets ? 'green' : 'red'}
              icon="&#x1F4B5;"
            />
          </div>
        )}
      </div>

      {/* Race Selector + Detail */}
      {records.length > 0 && (
        <div className="perf-detail-section animate-fade-in">
          <div className="perf-race-selector">
            <span className="perf-selector-label">選擇賽事:</span>
            <div className="perf-race-pills">
              {allRaceIds.map(raceId => {
                const rec = records.find(r => r.race_id === raceId)
                const raceNo = raceId.split('-').pop()?.replace(/^0+/, '') ?? '?'
                return (
                  <button
                    key={raceId}
                    className={`perf-race-pill ${raceId === selectedRaceId ? 'active' : ''} ${rec?.top1_hit ? 'hit' : ''}`}
                    onClick={() => setSelectedRaceId(raceId)}
                  >
                    R{raceNo}
                    {rec?.top1_hit && <span className="pill-hit">&#x2713;</span>}
                  </button>
                )
              })}
            </div>
          </div>

          {detailLoading ? (
            <div className="perf-detail-loading">載入賽事詳情...</div>
          ) : raceDetail ? (
            <>
              {/* Factor Analysis */}
              {raceDetail.key_factors.length > 0 && (
                <div className="perf-factors">
                  <div className="perf-factors-title">&#x1F50D; 致勝因素分析</div>
                  <div className="perf-factors-grid">
                    {raceDetail.key_factors.map((factor, idx) => (
                      <FactorCard key={idx} factor={factor} />
                    ))}
                  </div>
                  {(raceDetail.performance.pace_analysis || raceDetail.performance.draw_bias || raceDetail.performance.market_move) && (
                    <div className="perf-factor-summary">
                      {raceDetail.performance.draw_bias && (
                        <div className="factor-summary-item">
                          <span className="factor-icon">&#x1F3CF;</span>
                          <span>{raceDetail.performance.draw_bias}</span>
                        </div>
                      )}
                      {raceDetail.performance.market_move && (
                        <div className="factor-summary-item">
                          <span className="factor-icon">&#x1F4C8;</span>
                          <span>{raceDetail.performance.market_move}</span>
                        </div>
                      )}
                      {raceDetail.performance.pace_analysis && (
                        <div className="factor-summary-item">
                          <span className="factor-icon">&#x1F3C3;</span>
                          <span>{raceDetail.performance.pace_analysis}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Comparison Table */}
              <div className="perf-comparison">
                <div className="perf-comparison-header">
                  <span className="perf-comparison-title">&#x1F4CB; AI 預測 vs 實際結果</span>
                  <span className="perf-comparison-sub">
                    命中: <span className="hit-count">{raceDetail.performance.top3_hit_count}/3</span>
                    {' | '}ROI: <span className={raceDetail.performance.roi_percent >= 0 ? 'roi-positive' : 'roi-negative'}>
                      {raceDetail.performance.roi_percent >= 0 ? '+' : ''}{raceDetail.performance.roi_percent.toFixed(1)}%
                    </span>
                  </span>
                </div>
                <div className="perf-table-wrap">
                  <table className="data-table perf-table">
                    <thead>
                      <tr>
                        <th>名次</th>
                        <th>馬號</th>
                        <th>馬匹名稱</th>
                        <th>騎師/練馬師</th>
                        <th>獨贏賠率</th>
                        <th>AI 預測勝率%</th>
                        <th>AI 預測排名</th>
                        <th>命中狀態</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...raceDetail.comparison].sort((a, b) => {
                        const pa = a.finish_position ?? 999
                        const pb = b.finish_position ?? 999
                        return pa - pb
                      }).map((row) => (
                        <ComparisonRow key={row.runner_id} row={row} onHorseClick={(id, name) => { setDrawerHorseId(id); setDrawerHorseName(name) }} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="perf-empty">
              <div>無法載入賽事詳情</div>
            </div>
          )}
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      <HorseDetailDrawer
        horseId={drawerHorseId}
        horseName={drawerHorseName}
        onClose={() => setDrawerHorseId(null)}
      />
    </div>
  )
}

function KPICard({ label, value, sub, color, icon }: {
  label: string; value: string; sub: string; color: 'green' | 'red'; icon: string
}) {
  const colorClass = color === 'green' ? 'kpi-green' : 'kpi-red'
  return (
    <div className={`perf-kpi-card ${colorClass}`}>
      <div className="kpi-icon" dangerouslySetInnerHTML={{ __html: icon }} />
      <div className="kpi-body">
        <div className="kpi-label">{label}</div>
        <div className="kpi-value">{value}</div>
        <div className="kpi-sub">{sub}</div>
      </div>
    </div>
  )
}

function FactorCard({ factor }: { factor: KeyFactor }) {
  const impactClass = factor.impact.includes('good') || factor.impact === 'positive' || factor.impact === 'expected'
    ? 'factor-good'
    : factor.impact.includes('bad') || factor.impact === 'upset'
    ? 'factor-bad'
    : factor.impact === 'remarkable'
    ? 'factor-remarkable'
    : 'factor-neutral'

  const typeLabel: Record<string, string> = {
    draw_bias: '檔位',
    upset: '冷門',
    favorite_wins: '熱門',
    pace: '步速',
    ai_accuracy: 'AI 準確',
    ai_miss: 'AI 落空',
  }

  return (
    <div className={`perf-factor-card ${impactClass}`}>
      <div className="factor-type">{typeLabel[factor.type] ?? factor.type}</div>
      <div className="factor-desc">{factor.description}</div>
    </div>
  )
}

function ComparisonRow({ row, onHorseClick }: { row: ComparisonRow; onHorseClick: (horseId: string, horseName: string) => void }) {
  const isTopPick = row.rank <= 3
  const hit = row.is_top3_pick && row.finished_in_top3
  const winner = row.is_winner

  let rowClass = ''
  if (winner) rowClass = 'row-winner'
  else if (hit) rowClass = 'row-hit'
  else if (row.is_top3_pick && !row.finished_in_top3) rowClass = 'row-miss'

  return (
    <tr className={rowClass}>
      <td>
        <span className={`finish-pos ${row.finish_position != null && row.finish_position <= 3 ? 'finish-top3' : ''}`}>
          {row.finish_position ?? '-'}
        </span>
      </td>
      <td>
        <span className="horse-no-badge">{row.horse_no}</span>
      </td>
      <td className="horse-name-cell">
        <button
          className="horse-name horse-name-link"
          onClick={() => onHorseClick(row.horse_id, row.horse_name)}
          title={`查看 ${row.horse_name} 詳情`}
        >
          {row.horse_name}
        </button>
      </td>
      <td className="jockey-trainer-cell">
        <div className="jt-badge-row">
          <span className="jt-badge jt-jockey-badge">{row.jockey ?? '-'}</span>
          <span className="jt-badge jt-trainer-badge">{row.trainer ?? '-'}</span>
        </div>
      </td>
      <td>
        <span className="odds-cell">{row.win_odds ? `${row.win_odds.toFixed(1)}` : '-'}</span>
      </td>
      <td>
        <span className="badge badge-prob">
          {row.predicted_prob != null ? `${(row.predicted_prob * 100).toFixed(1)}%` : '-'}
        </span>
      </td>
      <td>
        <span className={`ai-rank rank-${row.rank}`}>
          {row.rank}
          {row.rank <= 3 && <span className="rank-star">&#x2605;</span>}
        </span>
      </td>
      <td>
        {row.is_winner ? (
          <span className="result-badge result-win">&#x1F3C6; 冠軍</span>
        ) : row.is_top3_pick && row.finished_in_top3 ? (
          <span className="result-badge result-hit">&#x2713; 命中</span>
        ) : row.is_top3_pick && !row.finished_in_top3 ? (
          <span className="result-badge result-miss">&#x2717; 落空</span>
        ) : row.finished_in_top3 ? (
          <span className="result-badge result-surprise">&#x26A0; 黑馬</span>
        ) : (
          <span className="result-badge result-na">-</span>
        )}
      </td>
    </tr>
  )
}
