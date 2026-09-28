import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const supabase = getServerSupabase()

    const { data: perfData, error: perfError } = await supabase
      .from('ai_performance')
      .select('*')
      .order('analysis_date', { ascending: false })

    if (perfError) {
      if (perfError.message?.includes('Could not find') || perfError.code === '42P01') {
        return NextResponse.json({
          ok: true,
          total_races: 0,
          summary: { win_rate: 0, top3_rate: 0, avg_roi: 0, total_bets: 0, total_returns: 0, top1_hits: 0, top3_total_hits: 0 },
          records: [],
          table_missing: true,
        })
      }
      console.error('[API /performance] error:', perfError)
      return NextResponse.json({ ok: false, error: perfError.message }, { status: 500 })
    }

    const records = perfData ?? []

    if (records.length === 0) {
      return NextResponse.json({
        ok: true,
        total_races: 0,
        summary: { win_rate: 0, top3_rate: 0, avg_roi: 0, total_bets: 0, total_returns: 0 },
        records: [],
      })
    }

    const totalRaces = records.length
    const top1Hits = records.filter((r: any) => r.top1_hit).length
    const top3TotalHits = records.reduce((sum: number, r: any) => sum + (r.top3_hit_count ?? 0), 0)
    const totalBets = records.reduce((sum: number, r: any) => sum + (r.total_bets ?? 0), 0)
    const totalReturns = records.reduce((sum: number, r: any) => sum + (r.total_returns ?? 0), 0)
    const avgRoi = records.reduce((sum: number, r: any) => sum + (r.roi_percent ?? 0), 0) / totalRaces

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
  } catch (err: any) {
    console.error('[API /performance] unexpected error:', err)
    return NextResponse.json({ ok: false, error: err.message ?? 'Internal error' }, { status: 500 })
  }
}
