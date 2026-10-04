'use client'

import { useState, useEffect } from 'react'

interface PipelineRace {
  race_id: string
  race_no: number
  is_finished: boolean
  runner_count: number
  has_odds: boolean
  has_predictions: boolean
  has_final_prob: boolean
  has_results: boolean
  has_review: boolean
  stage: string
  review: { top1_hit: boolean; roi_percent: number } | null
}

interface PipelineControlProps {
  date: string
}

const STAGE_LABELS: Record<string, { label: string; color: string; icon: string }> = {
  stage0_no_data: { label: '未有數據', color: '#666', icon: '○' },
  stage1_pre_race: { label: 'Stage 1: 基本資料', color: '#2196F3', icon: '①' },
  stage2_need_fusion: { label: 'Stage 2: 需更新賠率', color: '#FF9800', icon: '②' },
  stage2_ready: { label: 'Stage 2: 就緒', color: '#4CAF50', icon: '✓' },
  stage3_need_review: { label: 'Stage 3: 待覆盤', color: '#9C27B0', icon: '③' },
  stage3_complete: { label: '完成', color: '#4CAF50', icon: '★' },
}

export function PipelineControl({ date }: PipelineControlProps) {
  const [races, setRaces] = useState<PipelineRace[]>([])
  const [loading, setLoading] = useState(true)
  const [reviewing, setReviewing] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const fetchStatus = async () => {
    setLoading(true)
    try {
      const res = await fetch(`/api/pipeline/status?date=${date}`)
      const data = await res.json()
      if (data.ok) {
        setRaces(data.races ?? [])
      }
    } catch (e) {
      console.error('[PipelineControl] fetch failed:', e)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchStatus()
  }, [date])

  const runAIReview = async () => {
    const needsReview = races.filter(r => r.stage === 'stage3_need_review')
    if (needsReview.length === 0) return

    setReviewing(true)
    try {
      const res = await fetch('/api/pipeline/ai-review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ race_ids: needsReview.map(r => r.race_id) }),
      })
      const data = await res.json()
      if (data.ok) {
        await fetchStatus()
      }
    } catch (e) {
      console.error('[PipelineControl] AI review failed:', e)
    }
    setReviewing(false)
  }

  if (loading) {
    return (
      <div style={{
        padding: '8px 12px',
        background: '#1a1a2e',
        borderRadius: 6,
        fontSize: 12,
        color: '#888',
      }}>
        Pipeline 載入中...
      </div>
    )
  }

  if (races.length === 0) return null

  const needsReview = races.filter(r => r.stage === 'stage3_need_review')
  const completedCount = races.filter(r => r.stage === 'stage3_complete').length
  const readyCount = races.filter(r => r.stage === 'stage2_ready' || r.stage === 'stage2_need_fusion').length

  return (
    <div style={{
      background: '#1a1a2e',
      borderRadius: 8,
      padding: '10px 14px',
      marginBottom: 12,
      border: '1px solid #2a2a4a',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        cursor: 'pointer',
      }} onClick={() => setExpanded(!expanded)}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#e0e0e0' }}>
            Pipeline
          </span>
          <span style={{ fontSize: 11, color: '#888' }}>
            {completedCount}/{races.length} 完成
            {readyCount > 0 && ` · ${readyCount} 就緒`}
            {needsReview.length > 0 && ` · ${needsReview.length} 待覆盤`}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {needsReview.length > 0 && (
            <button
              onClick={(e) => { e.stopPropagation(); runAIReview() }}
              disabled={reviewing}
              style={{
                padding: '3px 10px',
                fontSize: 11,
                background: reviewing ? '#555' : '#9C27B0',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                cursor: reviewing ? 'wait' : 'pointer',
              }}
            >
              {reviewing ? '執行中...' : '執行 AI 覆盤'}
            </button>
          )}
          <span style={{ fontSize: 10, color: '#666' }}>
            {expanded ? '▲' : '▼'}
          </span>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {races.map(race => {
            const stageInfo = STAGE_LABELS[race.stage] ?? STAGE_LABELS.stage0_no_data
            return (
              <div
                key={race.race_id}
                title={`${stageInfo.label}${race.review ? ` · Top1 ${race.review.top1_hit ? '命中' : '未中'} · ROI ${race.review.roi_percent.toFixed(0)}%` : ''}`}
                style={{
                  padding: '2px 8px',
                  fontSize: 11,
                  borderRadius: 4,
                  background: `${stageInfo.color}22`,
                  border: `1px solid ${stageInfo.color}44`,
                  color: stageInfo.color,
                  whiteSpace: 'nowrap',
                }}
              >
                {stageInfo.icon} R{race.race_no}
              </div>
            )
          })}
        </div>
      )}

      {expanded && needsReview.length > 0 && (
        <div style={{
          marginTop: 8,
          padding: '6px 10px',
          background: '#0d0d1a',
          borderRadius: 4,
          fontSize: 11,
          color: '#888',
        }}>
          <div style={{ marginBottom: 4, color: '#aaa' }}>CLI 指令：</div>
          <code style={{ color: '#4CAF50', fontSize: 10 }}>
            python scripts/odds_injection.py --date {date} --venue ST
          </code>
          <br />
          <code style={{ color: '#FF9800', fontSize: 10 }}>
            python scripts/post_race_import.py --date {date} --venue ST
          </code>
        </div>
      )}
    </div>
  )
}
