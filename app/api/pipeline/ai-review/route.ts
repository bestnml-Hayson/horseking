import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'

interface Runner {
  runner_id: string
  horse_id: string
  horse_no: number
  win_odds: number | null
  finish_position: number | null
  draw: number | null
  actual_weight: number | null
}

interface Prediction {
  runner_id: string
  raw_model_prob: number | null
  market_implied_prob: number | null
  final_prob: number | null
  expected_value: number | null
}

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

async function reviewRace(supabase: ReturnType<typeof getServerSupabase>, raceId: string): Promise<ReviewResult | null> {
  const [raceResp, runnersResp, predsResp] = await Promise.all([
    supabase.from('races').select('race_no').eq('race_id', raceId).single(),
    supabase.from('race_runners').select('*').eq('race_id', raceId),
    supabase.from('model_predictions').select('*').eq('race_id', raceId),
  ])

  const raceMeta = raceResp.data as { race_no: number } | null
  const runners = (runnersResp.data ?? []) as Runner[]
  const preds = (predsResp.data ?? []) as Prediction[]

  if (!raceMeta || runners.length === 0) return null

  const finished = runners.filter(r => r.finish_position != null)
  if (finished.length === 0) return null

  finished.sort((a, b) => (a.finish_position ?? 99) - (b.finish_position ?? 99))

  if (preds.length === 0) return null

  const runnerMap = new Map(runners.map(r => [r.runner_id, r]))
  const predMap = new Map(preds.map(p => [p.runner_id, p]))

  const sortedPreds = [...preds].sort(
    (a, b) => (b.final_prob ?? b.raw_model_prob ?? 0) - (a.final_prob ?? a.raw_model_prob ?? 0)
  )

  const top1 = sortedPreds[0]
  const top1Runner = runnerMap.get(top1.runner_id)
  const top1Finish = top1Runner?.finish_position ?? null
  const top1Hit = top1Finish === 1

  const top3 = sortedPreds.slice(0, 3)
  let top3HitCount = 0
  for (const p of top3) {
    const r = runnerMap.get(p.runner_id)
    if (r && r.finish_position != null && r.finish_position <= 3) {
      top3HitCount++
    }
  }

  let totalBets = 0
  let totalReturns = 0
  for (const p of sortedPreds) {
    const ev = p.expected_value ?? 0
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
  const winnerPred = predMap.get(winner.runner_id)
  const winnerPModel = winnerPred?.raw_model_prob ?? winnerPred?.final_prob ?? null

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
      predicted_prob: p.final_prob ?? p.raw_model_prob,
      hit: finishPos != null && finishPos <= 3,
    }
  })

  const aiPerfRow = {
    race_id: raceId,
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
