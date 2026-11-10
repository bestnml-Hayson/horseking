import { NextResponse } from 'next/server'
import { getServerSupabase, directFetch } from '@/lib/supabase-server'
import { computeClientPredictions } from '@/lib/race-utils'
import type { RaceRow, RaceRunner, Race } from '@/lib/types'
import type { HorseRaceRecord } from '@/lib/supabase-client'

export const dynamic = 'force-dynamic'

interface ReviewResult {
  race_id: string
  race_no: number
  top1_hit: boolean
  top3_hit_count: number
  roi_percent: number
  winner_odds: number | null
  commentary: string
}

function generateCommentary(
  raceNo: number,
  top1Hit: boolean,
  top3HitCount: number,
  roiPercent: number,
  winnerOdds: number | null,
  winnerPModel: number | null,
  totalBets: number,
): string {
  const isUpset = winnerOdds != null && winnerOdds >= 12.0
  const aiUnderestimated = isUpset && winnerPModel != null && winnerPModel < 0.10

  if (aiUnderestimated) {
    return `R${raceNo} 爆冷：#${winnerOdds!.toFixed(0)}x 大冷門跑出，AI 模型僅給 ${(winnerPModel! * 100).toFixed(0)}% 勝率，需檢討隱藏因素`
  }
  if (isUpset) {
    return `R${raceNo} 冷門：#${winnerOdds!.toFixed(0)}x 馬胜出，AI 有留意但賠率反映市場低估`
  }
  if (top1Hit && roiPercent > 0) {
    return `R${raceNo} AI 首選命中，EV 策略回報 +${roiPercent.toFixed(0)}%，模型判斷準確`
  }
  if (top1Hit && roiPercent <= 0) {
    return `R${raceNo} AI 首選跑出，但 EV 策略虧損 ${roiPercent.toFixed(0)}%，需收緊入選門檻`
  }
  if (top3HitCount >= 2) {
    return `R${raceNo} AI 前三膽命中 ${top3HitCount}/3，整體方向正確`
  }
  if (top3HitCount === 1) {
    return `R${raceNo} AI 前三膽僅中 1/3，命中率偏低`
  }
  if (totalBets > 0 && roiPercent < -50) {
    return `R${raceNo} AI 全數落空且重虧 ${roiPercent.toFixed(0)}%，本場存在模型未涵蓋因素`
  }
  return `R${raceNo} AI 預測落空，前三膽全數未進前三，累積數據用於權重修正`
}

async function fetchHorseHistoryForReview(horseIds: string[]): Promise<Map<string, HorseRaceRecord[]>> {
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

async function reviewRace(supabase: ReturnType<typeof getServerSupabase>, raceId: string): Promise<ReviewResult | null> {
  const [raceResp, runnersResp] = await Promise.all([
    supabase.from('races').select('race_date,venue,race_no,distance,class_level').eq('race_id', raceId).single(),
    supabase.from('race_runners').select('*').eq('race_id', raceId),
  ])

  const raceMeta = raceResp.data as { race_date: string; venue: string; race_no: number; distance: number | null; class_level: string | null } | null
  const runners = (runnersResp.data ?? []) as RaceRunner[]

  if (!raceMeta || runners.length === 0) return null

  const finished = runners.filter(r => r.finish_position != null)
  if (finished.length === 0) return null

  finished.sort((a, b) => (a.finish_position ?? 99) - (b.finish_position ?? 99))

  // Compute predictions using same client formula as frontend
  const horseIds = runners.map(r => r.horse_id).filter(Boolean)
  const horseHistory = await fetchHorseHistoryForReview(horseIds)

  const raceRowItems: RaceRow[] = runners.map(r => ({
    ...r,
    horse_name: r.horse_id || `馬${r.horse_no}`,
    prediction: null,
  }))

  const raceInfo: Race = {
    race_id: raceId,
    race_date: raceMeta.race_date,
    venue: raceMeta.venue,
    race_no: raceMeta.race_no,
    distance: raceMeta.distance,
    class_level: raceMeta.class_level,
    going: null,
  }

  const predicted = computeClientPredictions(
    raceRowItems, raceMeta.venue, raceInfo, horseHistory,
  )

  const sorted = [...predicted].sort(
    (a, b) => (b.prediction?.final_prob ?? 0) - (a.prediction?.final_prob ?? 0)
  )

  if (sorted.length === 0) return null

  const runnerMap = new Map(runners.map(r => [r.runner_id, r]))

  const top1 = sorted[0]
  const top1Runner = runnerMap.get(top1.runner_id)
  const top1Finish = top1Runner?.finish_position ?? null
  const top1Hit = top1Finish === 1

  const top3 = sorted.slice(0, 3)
  let top3HitCount = 0
  for (const p of top3) {
    const r = runnerMap.get(p.runner_id)
    if (r && r.finish_position != null && r.finish_position <= 3) {
      top3HitCount++
    }
  }

  let totalBets = 0
  let totalReturns = 0
  for (const p of sorted) {
    const ev = p.prediction?.expected_value ?? 0
    if (ev > 0.15) {
      const r = runnerMap.get(p.runner_id)
      if (r?.win_odds && r.finish_position) {
        totalBets += 100
        if (r.finish_position === 1) {
          totalReturns += 100 * r.win_odds
        }
      }
    }
  }
  const roiPercent = totalBets > 0 ? ((totalReturns - totalBets) / totalBets) * 100 : 0

  const winner = finished[0]
  const winnerOdds = winner.win_odds
  const winnerRow = sorted.find(s => s.runner_id === winner.runner_id)
  const winnerPModel = winnerRow?.prediction?.raw_model_prob ?? null

  const commentary = generateCommentary(
    raceMeta.race_no, top1Hit, top3HitCount, roiPercent,
    winnerOdds, winnerPModel, totalBets,
  )

  const top3Info = top3.map(p => {
    const r = runnerMap.get(p.runner_id)
    const finishPos = r?.finish_position ?? null
    return {
      runner_id: p.runner_id,
      horse_no: r?.horse_no ?? null,
      finish_pos: finishPos,
      predicted_prob: p.prediction?.final_prob ?? null,
      hit: finishPos != null && finishPos <= 3,
    }
  })

  const aiPerfRow = {
    race_id: raceId,
    race_date: raceMeta?.race_date,
    venue: raceMeta?.venue,
    race_no: raceMeta?.race_no,
    top1_pick_runner_id: top1.runner_id,
    top1_pick_finish_pos: top1Finish,
    top1_hit: top1Hit,
    top3_picks: JSON.stringify(top3Info),
    top3_hit_count: top3HitCount,
    total_bets: totalBets,
    total_returns: Math.round(totalReturns * 100) / 100,
    roi_percent: Math.round(roiPercent * 100) / 100,
    key_factors: JSON.stringify({ commentary }),
  }

  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    await (supabase.from('ai_performance') as any).upsert(aiPerfRow, { onConflict: 'race_id' })
  } catch (e) {
    console.error(`[AI Review] upsert failed for ${raceId}:`, e)
  }

  return {
    race_id: raceId,
    race_no: raceMeta.race_no,
    top1_hit: top1Hit,
    top3_hit_count: top3HitCount,
    roi_percent: Math.round(roiPercent * 100) / 100,
    winner_odds: winnerOdds,
    commentary,
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const raceIds: string[] = body.race_ids ?? []

    if (raceIds.length === 0) {
      return NextResponse.json({ ok: false, error: 'No race_ids provided' }, { status: 400 })
    }

    const supabase = getServerSupabase()
    const results: ReviewResult[] = []

    for (const raceId of raceIds) {
      const result = await reviewRace(supabase, raceId)
      if (result) {
        results.push(result)
      }
    }

    return NextResponse.json({ ok: true, results })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Internal error'
    console.error('[API /pipeline/ai-review] error:', err)
    return NextResponse.json({ ok: false, error: message }, { status: 500 })
  }
}
