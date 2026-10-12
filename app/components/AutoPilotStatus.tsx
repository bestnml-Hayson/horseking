'use client'
import { useEffect, useState } from 'react'

interface PipelineStatus {
  ok: boolean
  status: 'healthy' | 'error' | 'unknown'
  last_run: string | null
  discovered?: number
  scraped?: number
  archived?: number
  errors?: string[]
  elapsed_seconds?: number
  message?: string
}

export function AutoPilotStatus() {
  const [data, setData] = useState<PipelineStatus | null>(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    fetch('/api/pipeline-status', { cache: 'no-store' })
      .then(r => r.json())
      .then(setData)
      .catch(() => setData(null))
  }, [])

  const statusColor = data?.status === 'healthy' ? '#3fb950'
    : data?.status === 'error' ? '#f85149'
    : '#d29922'

  const statusLabel = data?.status === 'healthy' ? '自動化巡檢正常'
    : data?.status === 'error' ? '巡檢有錯誤'
    : '待首次巡檢'

  const lastRun = data?.last_run
    ? new Date(data.last_run).toLocaleString('zh-HK', { timeZone: 'Asia/Hong_Kong', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <div className="auto-pilot-status" onClick={() => setExpanded(!expanded)}>
      <span className="aps-dot" style={{ background: statusColor }} />
      <span className="aps-label">{statusLabel}</span>
      {lastRun && <span className="aps-time">上次: {lastRun}</span>}
      {expanded && data && (
        <div className="aps-detail">
          {data.discovered != null && <span>發現 {data.discovered} 個賽日</span>}
          {data.scraped != null && data.scraped > 0 && <span>新抓取 {data.scraped} 個</span>}
          {data.archived != null && data.archived > 0 && <span>歸檔 {data.archived} 場</span>}
          {data.errors && data.errors.length > 0 && (
            <span className="aps-error">{data.errors.join('; ')}</span>
          )}
          {data.status === 'unknown' && data.message && (
            <span className="aps-hint">{data.message}</span>
          )}
        </div>
      )}
      <style jsx>{`
        .auto-pilot-status {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 16px;
          border-radius: 10px;
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.06);
          font-size: 12px;
          color: var(--text-secondary, #8b949e);
          cursor: pointer;
          flex-wrap: wrap;
        }
        .auto-pilot-status:hover {
          background: rgba(255,255,255,0.05);
        }
        .aps-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          flex-shrink: 0;
          animation: pulse 2s infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        .aps-label {
          font-weight: 600;
          color: var(--text-primary, #e6edf3);
        }
        .aps-time {
          color: var(--text-tertiary, #6e7681);
        }
        .aps-detail {
          width: 100%;
          display: flex;
          gap: 12px;
          padding-top: 6px;
          border-top: 1px solid rgba(255,255,255,0.06);
          margin-top: 4px;
          font-size: 11px;
        }
        .aps-error {
          color: #f85149;
        }
        .aps-hint {
          color: #d29922;
        }
      `}</style>
    </div>
  )
}
