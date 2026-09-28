'use client'

import { useState, useEffect, useCallback } from 'react'
import type { HorseDetail } from '@/lib/types'
import { getFormColor } from '@/lib/race-utils'

interface HorseDetailDrawerProps {
  horseId: string | null
  horseName: string
  onClose: () => void
}

export function HorseDetailDrawer({ horseId, horseName, onClose }: HorseDetailDrawerProps) {
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
      <div className="drawer-panel" onClick={e => e.stopPropagation()}>
        <div className="drawer-header">
          <h2 className="drawer-title">{horseName}</h2>
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
              <div className="horse-stats-grid">
                <div className="horse-stat-card">
                  <div className="horse-stat-value">{detail.total_starts}</div>
                  <div className="horse-stat-label">總出賽次數</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value" style={{ color: '#10b981' }}>{detail.total_wins}</div>
                  <div className="horse-stat-label">冠軍次數</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value">{detail.win_rate.toFixed(1)}%</div>
                  <div className="horse-stat-label">勝出率</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value" style={{ color: '#f59e0b' }}>{detail.top3_rate.toFixed(1)}%</div>
                  <div className="horse-stat-label">前三率</div>
                </div>
              </div>

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

              {detail.race_history.length > 0 && (
                <div className="drawer-section">
                  <h3 className="drawer-section-title">完整賽績紀錄</h3>
                  <div className="race-history-table-wrap">
                    <table className="race-history-table">
                      <thead>
                        <tr>
                          <th>日期</th>
                          <th>場地</th>
                          <th>路程</th>
                          <th>名次</th>
                          <th>騎師</th>
                          <th>賠率</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.race_history.map((race, idx) => (
                          <tr key={idx}>
                            <td>{race.race_date ?? '-'}</td>
                            <td>
                              <span className={`venue-tag venue-${(race.venue ?? '').toLowerCase()}`}>
                                {race.venue === 'ST' ? '沙田' : race.venue === 'HV' ? '跑馬地' : race.venue ?? '-'}
                              </span>
                            </td>
                            <td>{race.distance ? `${race.distance}m` : '-'}</td>
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
                            <td className="tabular-nums">{race.win_odds ? race.win_odds.toFixed(1) : '-'}</td>
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
