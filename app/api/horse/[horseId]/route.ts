import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: Request,
  { params }: { params: { horseId: string } }
) {
  try {
    const { horseId } = params
    const supabase = getServerSupabase()

    const { data: horse, error: horseError } = await supabase
      .from('horses')
      .select('horse_id, horse_name, country')
      .eq('horse_id', horseId)
      .single()

    if (horseError || !horse) {
      return NextResponse.json({ ok: false, error: 'Horse not found' }, { status: 404 })
    }

    const h = horse as any

    const { data: runnerHistory } = await supabase
      .from('race_runners')
      .select('race_id, horse_no, jockey, trainer, win_odds, finish_position, actual_weight, draw, form_history')
      .eq('horse_id', horseId)
      .order('race_id', { ascending: false })
      .limit(20)

    const raceIds = (runnerHistory ?? []).map((r: any) => r.race_id)
    let raceMetaMap = new Map<string, any>()

    if (raceIds.length > 0) {
      const { data: raceMeta } = await supabase
        .from('races')
        .select('race_id, race_date, venue, race_no, distance, going')
        .in('race_id', raceIds)

      raceMetaMap = new Map((raceMeta ?? []).map((r: any) => [r.race_id, r]))
    }

    const raceHistory = (runnerHistory ?? []).map((r: any) => {
      const meta = raceMetaMap.get(r.race_id) || {}
      return {
        race_id: r.race_id,
        race_date: meta.race_date ?? null,
        venue: meta.venue ?? null,
        race_no: meta.race_no ?? null,
        distance: meta.distance ?? null,
        going: meta.going ?? null,
        finish_position: r.finish_position ?? null,
        horse_no: r.horse_no,
        win_odds: r.win_odds,
        jockey: r.jockey,
        trainer: r.trainer,
        weight_carried: r.actual_weight,
        draw: r.draw,
        form_history: r.form_history,
      }
    })

    const totalStarts = raceHistory.filter(r => r.finish_position != null).length
    const totalWins = raceHistory.filter(r => r.finish_position === 1).length
    const top3Count = raceHistory.filter(r => r.finish_position != null && r.finish_position <= 3).length

    const latestForm = raceHistory.find(r => r.form_history)?.form_history

    const recentForm = latestForm
      ? latestForm.split(/[-/\s,]+/).map((s: string) => parseInt(s.trim())).filter((n: number) => !isNaN(n) && n > 0).slice(0, 6)
      : raceHistory.slice(0, 6).map((r: any) => r.finish_position).filter((p: number | null): p is number => p != null)

    return NextResponse.json({
      ok: true,
      horse_id: h.horse_id,
      horse_name: h.horse_name,
      country: h.country,
      recent_form: recentForm,
      race_history: raceHistory,
      total_starts: totalStarts,
      total_wins: totalWins,
      win_rate: totalStarts > 0 ? (totalWins / totalStarts) * 100 : 0,
      top3_rate: totalStarts > 0 ? (top3Count / totalStarts) * 100 : 0,
    })
  } catch (err: any) {
    console.error('[API /horse/[horseId]] error:', err)
    return NextResponse.json({ ok: false, error: err.message ?? 'Internal error' }, { status: 500 })
  }
}
