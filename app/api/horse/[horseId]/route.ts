import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'
import type { Horse, RaceRunner, Race, HorseRaceHistory } from '@/lib/types'

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

    const h = horse as Horse

    const { data: runnerHistory } = await supabase
      .from('race_runners')
      .select('race_id, horse_no, jockey, trainer, win_odds, finish_position, actual_weight, draw, finish_time, form_history')
      .eq('horse_id', horseId)
      .order('race_id', { ascending: false })
      .limit(30)

    const raceIds = (runnerHistory ?? []).map((r) => (r as unknown as RaceRunner).race_id)
    let raceMetaMap = new Map<string, Race>()

    if (raceIds.length > 0) {
      const { data: raceMeta } = await supabase
        .from('races')
        .select('race_id, race_date, venue, race_no, distance, going')
        .in('race_id', raceIds)

      raceMetaMap = new Map((raceMeta ?? []).map((r) => {
        const race = r as unknown as Race
        return [race.race_id, race]
      }))
    }

    const raceHistory: HorseRaceHistory[] = (runnerHistory ?? []).map((r) => {
      const row = r as unknown as RaceRunner
      const meta = raceMetaMap.get(row.race_id)
      return {
        race_id: row.race_id,
        race_date: meta?.race_date ?? null,
        venue: meta?.venue ?? null,
        race_no: meta?.race_no ?? null,
        distance: meta?.distance ?? null,
        going: meta?.going ?? null,
        finish_position: row.finish_position ?? null,
        horse_no: row.horse_no,
        win_odds: row.win_odds,
        jockey: row.jockey,
        trainer: row.trainer,
        weight_carried: row.actual_weight,
        draw: row.draw,
        finish_time: row.finish_time,
        form_history: row.form_history,
      }
    })

    const finished = raceHistory.filter(r => r.finish_position != null)
    const totalStarts = finished.length
    const totalWins = finished.filter(r => r.finish_position === 1).length
    const totalPlaces = finished.filter(r => r.finish_position === 2).length
    const totalShows = finished.filter(r => r.finish_position === 3).length
    const totalFourth = finished.filter(r => r.finish_position === 4).length

    const latestForm = raceHistory.find(r => r.form_history)?.form_history
    const recentForm = latestForm
      ? latestForm.split(/[-/\s,]+/).map((s: string) => parseInt(s.trim())).filter((n: number) => !isNaN(n) && n > 0).slice(0, 6)
      : finished.slice(0, 6).map((r) => r.finish_position as number)

    const oddsValues = finished.map(r => r.win_odds).filter((o: number | null): o is number => o != null && o > 0)
    const avgOdds = oddsValues.length > 0 ? oddsValues.reduce((a: number, b: number) => a + b, 0) / oddsValues.length : 0

    const venueMap = new Map<string, { starts: number; wins: number }>()
    for (const r of finished) {
      const v = r.venue ?? 'UNK'
      if (!venueMap.has(v)) venueMap.set(v, { starts: 0, wins: 0 })
      const s = venueMap.get(v)!
      s.starts++
      if (r.finish_position === 1) s.wins++
    }
    const venueStats = Array.from(venueMap.entries()).map(([venue, s]) => ({
      venue,
      starts: s.starts,
      wins: s.wins,
      win_rate: s.starts > 0 ? (s.wins / s.starts) * 100 : 0,
      top3_rate: s.starts > 0
        ? (finished.filter(r => r.venue === venue && r.finish_position != null && r.finish_position <= 3).length / s.starts) * 100
        : 0,
    }))

    const distMap = new Map<string, { starts: number; wins: number }>()
    for (const r of finished) {
      if (r.distance == null) continue
      const bucket = r.distance <= 1200 ? '短途 (≤1200m)' : r.distance <= 1600 ? '中途 (1201-1600m)' : '長途 (>1600m)'
      if (!distMap.has(bucket)) distMap.set(bucket, { starts: 0, wins: 0 })
      const s = distMap.get(bucket)!
      s.starts++
      if (r.finish_position === 1) s.wins++
    }
    let bestDistance: string | null = null
    let bestWinRate = 0
    distMap.forEach((s, bucket) => {
      if (s.starts >= 2) {
        const wr = s.wins / s.starts
        if (wr > bestWinRate) {
          bestWinRate = wr
          bestDistance = bucket
        }
      }
    })

    const jockeyMap = new Map<string, { rides: number; wins: number }>()
    for (const r of finished) {
      if (!r.jockey) continue
      if (!jockeyMap.has(r.jockey)) jockeyMap.set(r.jockey, { rides: 0, wins: 0 })
      const j = jockeyMap.get(r.jockey)!
      j.rides++
      if (r.finish_position === 1) j.wins++
    }
    const jockeyPartners = Array.from(jockeyMap.entries())
      .map(([name, s]) => ({ name, rides: s.rides, wins: s.wins }))
      .sort((a, b) => b.rides - a.rides)
      .slice(0, 5)

    return NextResponse.json({
      ok: true,
      horse_id: h.horse_id,
      horse_name: h.horse_name,
      country: h.country,
      recent_form: recentForm,
      race_history: raceHistory.slice(0, 10),
      total_starts: totalStarts,
      total_wins: totalWins,
      total_places: totalPlaces,
      total_shows: totalShows,
      total_fourth: totalFourth,
      win_rate: totalStarts > 0 ? (totalWins / totalStarts) * 100 : 0,
      top3_rate: totalStarts > 0 ? ((totalWins + totalPlaces + totalShows) / totalStarts) * 100 : 0,
      top4_rate: totalStarts > 0 ? ((totalWins + totalPlaces + totalShows + totalFourth) / totalStarts) * 100 : 0,
      avg_odds: Math.round(avgOdds * 10) / 10,
      venue_stats: venueStats,
      best_distance: bestDistance,
      jockey_partners: jockeyPartners,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Internal error'
    console.error('[API /horse/[horseId]] error:', err)
    return NextResponse.json({ ok: false, error: message }, { status: 500 })
  }
}
