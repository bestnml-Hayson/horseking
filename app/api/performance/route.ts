import { NextResponse } from 'next/server'
import { directFetch } from '@/lib/supabase-server'
import type { AIPerformanceRecord } from '@/lib/types'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url)
    const date = searchParams.get('date')

    const perfData = await directFetch(
      `ai_performance?race_date=eq.${date ?? 'not-a-date'}&select=*&order=analysis_date.desc`
    )

    const records = perfData as unknown as AIPerformanceRecord[]

    if (records.length === 0) {
      return NextResponse.json({
        ok: true,
        total_races: 0,
        summary: { win_rate: 0, top3_rate: 0, avg_roi: 0, total_bets: 0, total_returns: 0 },
        records: [],
      })
    }

    const totalRaces = records.length
    const top1Hits = records.filter((r) => r.top1_hit).length
    const top3TotalHits = records.reduce((sum, r) => sum + (r.top3_hit_count ?? 0), 0)
    const totalBets = records.reduce((sum, r) => sum + (r.total_bets ?? 0), 0)
    const totalReturns = records.reduce((sum, r) => sum + (r.total_returns ?? 0), 0)
    const avgRoi = records.reduce((sum, r) => sum + (r.roi_percent ?? 0), 0) / totalRaces

    const summary = {
      win_rate: totalRaces > 0 ? (top1Hits / totalRaces) * 100 : 0,
      top3_rate: totalRaces > 0 ? (top3TotalHits / (totalRaces * 3)) * 100 : 0,
      avg_roi: avgRoi,
      total_bets: totalBets,
      total_returns: totalReturns,
      top1_hits: top1Hits,
      top3_total_hits: top3TotalHits,
    }

    return NextResponse.json({
      ok: true,
      total_races: totalRaces,
      summary,
      records,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Internal error'
    if (message.includes('Could not find') || message.includes('42P01') || message.includes('relation')) {
      return NextResponse.json({
        ok: true, total_races: 0,
        summary: { win_rate: 0, top3_rate: 0, avg_roi: 0, total_bets: 0, total_returns: 0, top1_hits: 0, top3_total_hits: 0 },
        records: [], table_missing: true,
      })
    }
    console.error('[API /performance] unexpected error:', err)
    return NextResponse.json({ ok: false, error: message }, { status: 500 })
  }
}
