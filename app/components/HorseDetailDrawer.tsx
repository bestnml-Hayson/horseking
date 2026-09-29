'use client'

import { useState, useEffect, useCallback } from 'react'
import type { HorseDetail, RaceRow } from '@/lib/types'
import { getFormColor, generateHorseComprehensiveInsight, computeBenterBreakdown } from '@/lib/race-utils'
import { FACTOR_COLORS, STAT_COLORS } from '@/lib/color-utils'

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
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Network error'
      setError(msg)
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

              {/* Benter Factor Breakdown */}
              {raceRow && (() => {
                const bd = computeBenterBreakdown(raceRow)
                const factors = [
                  {
                    label: '近況走勢分', sublabel: 'Form Score', score: bd.formScore, weight: '30%', color: FACTOR_COLORS.form,
                    subs: [
                      { label: '近 6 場平均名次', value: bd.formSub.avgFinish != null ? bd.formSub.avgFinish.toFixed(1) : '-' },
                      { label: '最佳名次', value: bd.formSub.bestFinish != null ? `第 ${bd.formSub.bestFinish} 名` : '-' },
                      { label: '上場名次', value: bd.formSub.lastRacePos != null ? `第 ${bd.formSub.lastRacePos} 名` : '-' },
                      { label: '走勢趨勢', value: bd.formSub.trendLabel },
                      { label: '走勢評分', value: bd.formSub.trendScore },
                    ],
                  },
                  {
                    label: '檔位偏差分', sublabel: 'Draw Bias', score: bd.drawScore, weight: '15%', color: FACTOR_COLORS.draw,
                    subs: [
                      { label: '檔位利弊係數', value: bd.drawSub.drawBiasCoeff.toFixed(2) },
                      { label: '場地偏差指數', value: bd.drawSub.trackBiasIndex.toFixed(2) },
                      { label: '檔位判定', value: bd.drawSub.drawAdvantage },
                    ],
                  },
                  {
                    label: '騎練組合分', sublabel: 'Jockey/Trainer', score: bd.jockeyTrainerScore, weight: '35%', color: FACTOR_COLORS.jockeyTrainer,
                    subs: [
                      { label: `騎師 ${bd.jtSub.jockeyLabel}`, value: `${bd.jtSub.jockeyWinRate.toFixed(1)}%` },
                      { label: `練馬師 ${bd.jtSub.trainerLabel}`, value: `${bd.jtSub.trainerWinRate.toFixed(1)}%` },
                      { label: '人馬默契得分', value: bd.jtSub.synergyScore },
                    ],
                  },
                  {
                    label: '途程場地分', sublabel: 'Course/Distance', score: bd.courseDistanceScore, weight: '20%', color: FACTOR_COLORS.courseDistance,
                    subs: [
                      { label: '負磅影響', value: bd.cdSub.weightEffect > 0 ? `+${bd.cdSub.weightEffect}` : `${bd.cdSub.weightEffect}` },
                      { label: '班次估算', value: bd.cdSub.classEstimate },
                      { label: '場地適應度', value: bd.cdSub.goingAdaptability },
                      { label: '場地狀況', value: bd.cdSub.goingLabel },
                    ],
                  },
                ]
                return (
                  <div className="drawer-benter-breakdown">
                    <div className="drawer-benter-header">
                      <span className="drawer-benter-icon">&#x1F9EE;</span>
                      <span className="drawer-benter-title">Benter 演算法評分拆解</span>
                    </div>
                    <div className="benter-factors-grid">
                      {factors.map(f => (
                        <div key={f.label} className="benter-factor-card">
                          <div className="bf-header">
                            <span className="bf-label">{f.label}</span>
                            <span className="bf-sublabel">{f.sublabel}</span>
                          </div>
                          <div className="bf-bar-track">
                            <div
                              className="bf-bar-fill"
                              style={{ width: `${f.score}%`, backgroundColor: f.color }}
                            />
                          </div>
                          <div className="bf-footer">
                            <span className="bf-score" style={{ color: f.color }}>{f.score}</span>
                            <span className="bf-weight">權重 {f.weight}</span>
                          </div>
                          <div className="bf-sub-metrics">
                            {f.subs.map(s => (
                              <div key={s.label} className="bf-sub-row">
                                <span className="bf-sub-label">{s.label}</span>
                                <span className="bf-sub-value" style={{ color: f.color }}>{s.value}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="benter-summary-row">
                      <div className="benter-total-card">
                        <div className="bt-label">總評分 Total Score</div>
                        <div className="bt-value">{bd.totalScore}</div>
                      </div>
                      {bd.pFinal != null && (
                        <div className="benter-total-card">
                          <div className="bt-label">Benter P_final</div>
                          <div className="bt-value" style={{ color: STAT_COLORS.wins }}>{(bd.pFinal * 100).toFixed(1)}%</div>
                        </div>
                      )}
                    </div>
                    <p className="benter-summary-text">{bd.summary}</p>
                  </div>
                )
              })()}

              {/* Career Stats Grid */}
              <div className="horse-stats-grid">
                <div className="horse-stat-card">
                  <div className="horse-stat-value">{detail.total_starts}</div>
                  <div className="horse-stat-label">總出賽</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value" style={{ color: STAT_COLORS.wins }}>{detail.total_wins}</div>
                  <div className="horse-stat-label">冠軍 (W)</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value" style={{ color: STAT_COLORS.places }}>{detail.total_places}</div>
                  <div className="horse-stat-label">亞軍 (P)</div>
                </div>
                <div className="horse-stat-card">
                  <div className="horse-stat-value" style={{ color: STAT_COLORS.shows }}>{detail.total_shows}</div>
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
                  <div className="horse-stat-value" style={{ color: STAT_COLORS.shows }}>{detail.top3_rate.toFixed(1)}%</div>
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
                              {race.track_course && (
                                <span className="track-course-tag"> {race.track_course}</span>
                              )}
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
