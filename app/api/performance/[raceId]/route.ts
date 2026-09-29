import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'
import type { AIPerformanceRecord, RaceRunner, ModelPrediction, ComparisonRow, Race } from '@/lib/types'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: Request,
  { params }: { params: { raceId: string } }
) {
  try {
    const { raceId } = params
    const supabase = getServerSupabase()

    const { data: perfData, error: perfError } = await supabase
      .from('ai_performance')
      .select('*')
      .eq('race_id', raceId)
      .single()

    if (perfError || !perfData) {
      return NextResponse.json({ ok: false, error: 'No analysis found for this race' }, { status: 404 })
    }

    const perf = perfData as unknown as AIPerformanceRecord

    const { data: runners } = await supabase
      .from('race_runners')
      .select('*')
      .eq('race_id', raceId)
      .order('horse_no', { ascending: true })

    const typedRunners = (runners ?? []) as unknown as RaceRunner[]
    const horseIds = typedRunners.map((r) => r.horse_id).filter(Boolean)
    const { data: horses } = horseIds.length > 0
      ? await supabase
          .from('horses')
          .select('horse_id, horse_name')
          .in('horse_id', horseIds)
      : { data: [] as { horse_id: string; horse_name: string }[] }

    const horseNameMap = new Map<string, string>((horses ?? []).map((h) => [h.horse_id, h.horse_name]))

    const { data: predictions } = await supabase
      .from('model_predictions')
      .select('*')
      .eq('race_id', raceId)

    const { data: raceInfo } = await supabase
      .from('races')
      .select('*')
      .eq('race_id', raceId)
      .single()

    const { data: results } = await supabase
      .from('race_results')
      .select('*')
      .eq('race_id', raceId)

    const finishPosMap = new Map<number, number>()
    if (results && results.length > 0) {
      for (const r of results) {
        const row = r as { horse_no: number | null; finish_position: number | null }
        if (row.horse_no != null && row.finish_position != null) {
          finishPosMap.set(row.horse_no, row.finish_position)
        }
      }
    }

    const typedPredictions = (predictions ?? []) as unknown as ModelPrediction[]
    const runnerMap = new Map(typedRunners.map((r) => [r.runner_id, r]))
    const predMap = new Map(typedPredictions.map((p) => [p.runner_id, p]))

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
      race_info: raceInfo as unknown as Race,
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
