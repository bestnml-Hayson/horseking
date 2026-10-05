import { NextResponse } from 'next/server'
import { directFetch } from '@/lib/supabase-server'
import type { AIPerformanceRecord, RaceRunner, ModelPrediction, ComparisonRow, Race } from '@/lib/types'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function GET(
  _req: Request,
  { params }: { params: { raceId: string } }
) {
  try {
    const { raceId } = params

    const [perfRows, runners, predictions, raceRows, results] = await Promise.all([
      directFetch(`ai_performance?race_id=eq.${raceId}&select=*`).then(r => r as unknown as AIPerformanceRecord[]),
      directFetch(`race_runners?race_id=eq.${raceId}&select=*&order=horse_no.asc`).then(r => r as unknown as RaceRunner[]),
      directFetch(`model_predictions?race_id=eq.${raceId}&select=*`).then(r => r as unknown as ModelPrediction[]),
      directFetch(`races?race_id=eq.${raceId}&select=*`).then(r => r as unknown as Race[]),
      directFetch(`race_results?race_id=eq.${raceId}&select=*`).catch(() => [] as unknown[]),
    ])

    const perf = perfRows[0]
    if (!perf) {
      return NextResponse.json({ ok: false, error: 'No analysis found for this race' }, { status: 404 })
    }

    const raceInfo = raceRows[0] ?? null
    const typedRunners = runners ?? []
    const typedPredictions = predictions ?? []

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

    const sortedPreds = typedPredictions.sort(
      (a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0)
    )

    let comparison: ComparisonRow[]

    if (sortedPreds.length > 0) {
      comparison = sortedPreds.map((pred, idx) => {
        const runner = runnerMap.get(pred.runner_id)
        const horseId = runner?.horse_id
        const horseNo = runner?.horse_no
        const finishPos = finishPosMap.get(horseNo!) ?? runner?.finish_position ?? null
        return {
          rank: idx + 1,
          runner_id: pred.runner_id,
          horse_no: horseNo!,
          horse_id: horseId!,
          horse_name: horseNameMap.get(horseId!) || horseId! || `馬${horseNo || '?'}`,
          jockey: runner?.jockey ?? null,
          trainer: runner?.trainer ?? null,
          draw: runner?.draw ?? null,
          win_odds: runner?.win_odds ?? null,
          finish_position: finishPos,
          predicted_prob: pred.final_prob,
          expected_value: pred.expected_value,
          kelly_fraction: pred.kelly_fraction,
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
      comparison = typedRunners.map((runner, idx) => {
        const horseId = runner.horse_id
        const horseNo = runner.horse_no
        const finishPos = finishPosMap.get(horseNo) ?? runner.finish_position ?? null
        return {
          rank: idx + 1,
          runner_id: runner.runner_id,
          horse_no: horseNo,
          horse_id: horseId,
          horse_name: horseNameMap.get(horseId) || horseId || `馬${horseNo || '?'}`,
          jockey: runner.jockey ?? null,
          trainer: runner.trainer ?? null,
          draw: runner.draw ?? null,
          win_odds: runner.win_odds ?? null,
          finish_position: finishPos,
          predicted_prob: null,
          expected_value: null,
          kelly_fraction: null,
          is_top3_pick: false,
          finished_in_top3: finishPos != null && finishPos <= 3,
          is_winner: finishPos === 1,
          official_rating: runner.official_rating ?? null,
          jockey_win_rate: runner.jockey_win_rate ?? null,
          trainer_win_rate: runner.trainer_win_rate ?? null,
          weight_carried_diff: runner.weight_carried_diff ?? null,
          declared_weight: runner.declared_weight ?? null,
        }
      })
    }

    comparison.sort((a, b) => {
      const pa = a.finish_position ?? 999
      const pb = b.finish_position ?? 999
      return pa - pb
    })

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
      performance: perf,
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
