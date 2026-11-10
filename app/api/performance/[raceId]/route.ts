import { NextResponse } from 'next/server'
import { directFetch } from '@/lib/supabase-server'
import { computeClientPredictions } from '@/lib/race-utils'
import type { AIPerformanceRecord, RaceRunner, RaceRow, Race, ComparisonRow } from '@/lib/types'
import type { HorseRaceRecord } from '@/lib/supabase-client'

export const dynamic = 'force-dynamic'
export const revalidate = 0

async function fetchHorseHistory(horseIds: string[]): Promise<Map<string, HorseRaceRecord[]>> {
  const historyMap = new Map<string, HorseRaceRecord[]>()
  if (horseIds.length === 0) return historyMap

  const idList = horseIds.map(id => `"${id}"`).join(',')
  const rows = await directFetch(
    `race_runners?select=horse_id,finish_position,races!inner(race_date,venue,distance,class_level)&horse_id=in.(${idList})&finish_position=not.is.null&limit=2000`
  ) as Array<{
    horse_id: string
    finish_position: number | null
    races: { race_date: string; venue: string; distance: number | null; class_level: string | null } | null
  }>

  for (const row of rows) {
    if (row.finish_position == null || row.finish_position <= 0) continue
    const race = row.races
    if (!race?.venue || !race?.distance) continue

    const entry: HorseRaceRecord = {
      venue: race.venue,
      distance: race.distance,
      finish_position: row.finish_position,
      race_date: race.race_date,
      class_level: race.class_level ?? '',
    }

    const existing = historyMap.get(row.horse_id) ?? []
    existing.push(entry)
    historyMap.set(row.horse_id, existing)
  }

  historyMap.forEach((records) => {
    records.sort((a, b) => b.race_date.localeCompare(a.race_date))
  })

  return historyMap
}

export async function GET(
  _req: Request,
  { params }: { params: { raceId: string } }
) {
  try {
    const { raceId } = params

    const [perfRows, runners, raceRows, results] = await Promise.all([
      directFetch(`ai_performance?race_id=eq.${raceId}&select=*`).then(r => r as unknown as AIPerformanceRecord[]),
      directFetch(`race_runners?race_id=eq.${raceId}&select=*&order=horse_no.asc`).then(r => r as unknown as RaceRunner[]),
      directFetch(`races?race_id=eq.${raceId}&select=*`).then(r => r as unknown as Race[]),
      directFetch(`race_results?race_id=eq.${raceId}&select=*`).catch(() => [] as unknown[]),
    ])

    const perf = perfRows[0]
    if (!perf) {
      return NextResponse.json({ ok: false, error: 'No analysis found for this race' }, { status: 404 })
    }

    const raceInfo = raceRows[0] ?? null
    const typedRunners = runners ?? []

    const horseIds = typedRunners.map((r) => r.horse_id).filter(Boolean)
    let horseNameMap = new Map<string, string>()
    if (horseIds.length > 0) {
      const horses = await directFetch(`horses?horse_id=in.(${horseIds.join(',')})&select=horse_id,horse_name`)
      horseNameMap = new Map((horses as { horse_id: string; horse_name: string }[]).map((h) => [h.horse_id, h.horse_name]))
    }

    const finishPosMap = new Map<number, number>()
    for (const r of (results as { horse_no: number | null; finish_position: number | null }[])) {
      if (r.horse_no != null && r.finish_position != null) {
        finishPosMap.set(r.horse_no, r.finish_position)
      }
    }

    const runnerMap = new Map(typedRunners.map((r) => [r.runner_id, r]))

    // Compute predictions using the same client formula as the dashboard
    let comparison: ComparisonRow[]
    if (typedRunners.length > 0) {
      const horseHistory = await fetchHorseHistory(horseIds)
      const raceRowItems: RaceRow[] = typedRunners.map(r => ({
        ...r,
        horse_name: horseNameMap.get(r.horse_id) || r.horse_id || `馬${r.horse_no || '?'}`,
        prediction: null,
      }))

      const venue = raceInfo?.venue
      const predicted = computeClientPredictions(raceRowItems, venue, raceInfo ?? undefined, horseHistory)

      const sorted = [...predicted].sort(
        (a, b) => (b.prediction?.final_prob ?? 0) - (a.prediction?.final_prob ?? 0)
      )

      comparison = sorted.map((row, idx) => {
        const runner = runnerMap.get(row.runner_id)
        const horseId = runner?.horse_id ?? row.horse_id
        const horseNo = runner?.horse_no ?? row.horse_no
        const finishPos = finishPosMap.get(horseNo) ?? runner?.finish_position ?? null
        return {
          rank: idx + 1,
          runner_id: row.runner_id,
          horse_no: horseNo,
          horse_id: horseId,
          horse_name: horseNameMap.get(horseId) || horseId || `馬${horseNo || '?'}`,
          jockey: runner?.jockey ?? row.jockey ?? null,
          trainer: runner?.trainer ?? row.trainer ?? null,
          draw: runner?.draw ?? row.draw ?? null,
          win_odds: runner?.win_odds ?? row.win_odds ?? null,
          finish_position: finishPos,
          predicted_prob: row.prediction?.final_prob ?? null,
          expected_value: row.prediction?.expected_value ?? null,
          kelly_fraction: row.prediction?.kelly_fraction ?? null,
          is_top3_pick: idx < 3,
          finished_in_top3: finishPos != null && finishPos <= 3,
          is_winner: finishPos === 1,
          official_rating: runner?.official_rating ?? null,
          jockey_win_rate: runner?.jockey_win_rate ?? null,
          trainer_win_rate: runner?.trainer_win_rate ?? null,
          weight_carried_diff: runner?.weight_carried_diff ?? null,
          declared_weight: runner?.declared_weight ?? null,
        }
      })
    } else {
      comparison = []
    }

    comparison.sort((a, b) => {
      const pa = a.finish_position ?? 999
      const pb = b.finish_position ?? 999
      return pa - pb
    })

    // Recalculate hit metrics from client predictions (consistent with display)
    const top3Rows = comparison.filter(r => r.is_top3_pick)
    const recalculatedTop3Hits = top3Rows.filter(r => r.finished_in_top3).length
    const recalculatedTop1Hit = top3Rows.length > 0 && top3Rows[0].finish_position === 1
    const perfWithClientMetrics = {
      ...perf,
      top3_hit_count: recalculatedTop3Hits,
      top1_hit: recalculatedTop1Hit,
    }

    let keyFactors: { type: string; description: string; impact: string }[] = []
    if (perf.key_factors) {
      try {
        const parsed = typeof perf.key_factors === 'string'
          ? JSON.parse(perf.key_factors)
          : perf.key_factors
        keyFactors = parsed.factors ?? parsed ?? []
      } catch {
        keyFactors = []
      }
    }

    let top3Picks: unknown[] = []
    if (perf.top3_picks) {
      try {
        top3Picks = typeof perf.top3_picks === 'string'
          ? JSON.parse(perf.top3_picks)
          : perf.top3_picks
      } catch {
        top3Picks = []
      }
    }

    return NextResponse.json({
      ok: true,
      race_id: raceId,
      race_info: raceInfo,
      results,
      performance: perfWithClientMetrics,
      comparison,
      key_factors: keyFactors,
      top3_picks: top3Picks,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Internal error'
    console.error('[API /performance/[raceId]] error:', err)
    return NextResponse.json({ ok: false, error: message }, { status: 500 })
  }
}
