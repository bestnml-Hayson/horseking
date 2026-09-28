'use client'

import { useState, useEffect, useCallback } from 'react'
import type { HorseDetail, RaceRow } from '@/lib/types'
import { getFormColor, generateHorseComprehensiveInsight } from '@/lib/race-utils'

interface HorseDetailDrawerProps {
  horseId: string | null
  horseName: string
  raceRow?: RaceRow | null
  onClose: () => void
}

const VENUE_LABEL: Record<string, string> = { ST: '沙田', HV: '跑馬地' }

function fmtTime(seconds: number | null): string {
  if (seconds == null) return '-'
  const min = Math.floor(seconds / 60)
  const sec = (seconds % 60).toFixed(2)
  return min > 0 ? `${min}:${sec.padStart(5, '0')}` : `${sec}s`
}

export function HorseDetailDrawer({ horseId, horseName, raceRow, onClose }: HorseDetailDrawerProps) {
  const [detail, setDetail] = useState<HorseDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchDetail = useCallback(async () => {
    if (!horseId) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/horse/${encodeURIComponent(horseId)}`)
      if (!res.ok) throw new Error('Failed to fetch horse detail')
      const data = await res.json()
      if (data.ok) {
        setDetail(data)
      } else {
        setError(data.error ?? 'Unknown error')
      }
    } catch (e: any) {
      setError(e.message ?? 'Network error')
    } finally {
      setLoading(false)
    }
  }, [horseId])

  useEffect(() => {
    if (horseId) {
      fetchDetail()
    } else {
      setDetail(null)
    }
  }, [horseId, fetchDetail])

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEsc)
    return () => document.removeEventListener('keydown', handleEsc)
  }, [onClose])

  if (!horseId) return null

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-panel drawer-panel-wide" onClick={e => e.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <h2 className="drawer-title">{horseName}</h2>
            {detail?.country && <span className="drawer-country">{detail.country}</span>}
          </div>
          <button className="drawer-close" onClick={onClose}>&times;</button>
        </div>

        <div className="drawer-body">
          {loading && (
            <div className="drawer-loading">
              <div className="drawer-spinner" />
              <span>載入馬匹資料中...</span>
            </div>
          )}

          {error && (
            <div className="drawer-error">
              <span className="drawer-error-icon">&#x26A0;</span>
              <span>{error}</span>
            </div>
          )}

          {detail && !loading && (
            <>
              {/* AI Comprehensive Insight */}
              <div className="drawer-ai-insight">
                <div className="drawer-ai-insight-header">
                  <span className="drawer-ai-insight-icon">&#x1F9E0;</span>
                  <span className="drawer-ai-insight-title">AI 賽事前瞻綜合短評</span>
                </div>
                <p className="drawer-ai-insight-text">
                  {generateHorseComprehensiveInsight(
                    {
                      horse_name: detail.horse_name,
                      total_starts: detail.total_starts,
                      total_wins: detail.total_wins,
                      win_rate: detail.win_rate,
                      top3_rate: detail.top3_rate,
                      recent_form: detail.recent_form,
                      venue_stats: detail.venue_stats,
                      best_distance: detail.best_distance,
                      jockey_partners: detail.jockey_partners,
                      avg_odds: detail.avg_odds,
                    },
                    raceRow
                  )}
                </p>
              </div>

              {/* Career Stats Grid */}
              <div className="horse-stats-grid">
                <div className="horse-stat-card">
                  <div className="horse-stat-value">{detail.total_starts}</div>
                  <div className="horse-stat-label">總出賽</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value" style={{ color: '#10b981' }}>{detail.total_wins}</div>
                  <div className="horse-stat-label">冠軍 (W)</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value" style={{ color: '#3b82f6' }}>{detail.total_places}</div>
                  <div className="horse-stat-label">亞軍 (P)</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value" style={{ color: '#f59e0b' }}>{detail.total_shows}</div>
                  <div className="horse-stat-label">季軍 (S)</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value">{detail.total_fourth}</div>
                  <div className="horse-stat-label">第四</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value">{detail.win_rate.toFixed(1)}%</div>
                  <div className="horse-stat-label">勝出率</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value" style={{ color: '#f59e0b' }}>{detail.top3_rate.toFixed(1)}%</div>
                  <div className="horse-stat-label">前三率</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value">{detail.avg_odds > 0 ? detail.avg_odds.toFixed(1) : '-'}</div>
                  <div className="horse-stat-label">平均賠率</div>
                </div>
              </div>

              {/* Recent Form */}
              {detail.recent_form.length > 0 && (
                <div className="drawer-section">
                  <h3 className="drawer-section-title">近 6 場往績</h3>
                  <div className="form-badges-row">
                    {detail.recent_form.map((pos, i) => (
                      <span
                        key={i}
                        className="form-badge-large"
                        style={{
                          backgroundColor: getFormColor(pos) + '20',
                          color: getFormColor(pos),
                          borderColor: getFormColor(pos) + '40',
                        }}
                      >
                        {pos}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Venue Stats */}
              {detail.venue_stats.length > 0 && (
                <div className="drawer-section">
                  <h3 className="drawer-section-title">場地戰績</h3>
                  <div className="venue-stats-row">
                    {detail.venue_stats.map(vs => (
                      <div key={vs.venue} className="venue-stat-card">
                        <div className="venue-stat-name">{VENUE_LABEL[vs.venue] ?? vs.venue}</div>
                        <div className="venue-stat-detail">
                          {vs.starts} 場 / {vs.wins} 勝
                        </div>
                        <div className="venue-stat-rates">
                          勝率 <strong>{vs.win_rate.toFixed(1)}%</strong>
                          {' | '}
                          前三 <strong>{vs.top3_rate.toFixed(1)}%</strong>
                        </div>
                      </div>
                    ))}
                  </div>
                  {detail.best_distance && (
                    <div className="best-distance-tag">
                      最佳路程: <strong>{detail.best_distance}</strong>
                    </div>
                  )}
                </div>
              )}

              {/* Jockey Partners */}
              {detail.jockey_partners.length > 0 && (
                <div className="drawer-section">
                  <h3 className="drawer-section-title">主要騎師組合</h3>
                  <div className="jockey-partners-grid">
                    {detail.jockey_partners.map((jp, i) => (
                      <div key={i} className="jockey-partner-card">
                        <div className="jp-name">{jp.name}</div>
                        <div className="jp-stats">
                          {jp.rides} 次策騎 / {jp.wins} 勝
                          <span className="jp-wr"> ({jp.rides > 0 ? (jp.wins / jp.rides * 100).toFixed(1) : 0}%)</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Detailed Race History */}
              {detail.race_history.length > 0 && (
                <div className="drawer-section">
                  <h3 className="drawer-section-title">近 10 場詳細賽績</h3>
                  <div className="race-history-table-wrap">
                    <table className="race-history-table race-history-table-detailed">
                      <thead>
                        <tr>
                          <th>日期</th>
                          <th>場地</th>
                          <th>路程</th>
                          <th>場地狀況</th>
                          <th>名次</th>
                          <th>騎師</th>
                          <th>檔位</th>
                          <th>負磅</th>
                          <th>賠率</th>
                          <th>時間</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.race_history.map((race, idx) => (
                          <tr key={idx}>
                            <td>{race.race_date ?? '-'}</td>
                            <td>
                              <span className={`venue-tag venue-${(race.venue ?? '').toLowerCase()}`}>
                                {race.venue ? (VENUE_LABEL[race.venue] ?? race.venue) : '-'}
                              </span>
                            </td>
                            <td>{race.distance ? `${race.distance}m` : '-'}</td>
                            <td>{race.going ?? '-'}</td>
                            <td>
                              <span
                                className="finish-badge"
                                style={{
                                  backgroundColor: race.finish_position != null ? getFormColor(race.finish_position) + '20' : 'transparent',
                                  color: race.finish_position != null ? getFormColor(race.finish_position) : '#94a3b8',
                                }}
                              >
                                {race.finish_position ?? '-'}
                              </span>
                            </td>
                            <td>{race.jockey ?? '-'}</td>
                            <td>{race.draw ?? '-'}</td>
                            <td>{race.weight_carried ? `${race.weight_carried} lbs` : '-'}</td>
                            <td className="tabular-nums">{race.win_odds ? race.win_odds.toFixed(1) : '-'}</td>
                            <td className="tabular-nums">{fmtTime(race.finish_time)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {detail.race_history.length === 0 && !error && (
                <div className="drawer-empty">
                  <div className="drawer-empty-icon">&#x1F4CB;</div>
                  <div>暫無此馬匹的歷史賽績紀錄</div>
                  <div className="drawer-empty-sub">No race history available</div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
