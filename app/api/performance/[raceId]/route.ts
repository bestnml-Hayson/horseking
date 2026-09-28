import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'

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

    const perf = perfData as any

    const { data: runners } = await supabase
      .from('race_runners')
      .select('*')
      .eq('race_id', raceId)
      .order('horse_no', { ascending: true })

    const horseIds = (runners ?? []).map((r: any) => r.horse_id).filter(Boolean)
    const { data: horses } = horseIds.length > 0
      ? await supabase
          .from('horses')
          .select('horse_id, horse_name')
          .in('horse_id', horseIds)
      : { data: [] }

    const horseNameMap = new Map((horses ?? []).map((h: any) => [h.horse_id, h.horse_name]))

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
      .single()

    const finishPosMap = new Map<string, number>()
    if (results) {
      if (results.first_horse_id) finishPosMap.set(results.first_horse_id, 1)
      if (results.second_horse_id) finishPosMap.set(results.second_horse_id, 2)
      if (results.third_horse_id) finishPosMap.set(results.third_horse_id, 3)
      if (results.fourth_horse_id) finishPosMap.set(results.fourth_horse_id, 4)
    }

    const runnerMap = new Map((runners ?? []).map((r: any) => [r.runner_id, r]))
    const predMap = new Map((predictions ?? []).map((p: any) => [p.runner_id, p]))

    const sortedPreds = (predictions ?? []).sort(
      (a: any, b: any) => (b.final_prob ?? 0) - (a.final_prob ?? 0)
    )

    const comparison = sortedPreds.map((pred: any, idx: number) => {
      const runner = runnerMap.get(pred.runner_id)
      const horseId = runner?.horse_id
      const finishPos = finishPosMap.get(horseId) ?? runner?.finish_position ?? null
      return {
        rank: idx + 1,
        runner_id: pred.runner_id,
        horse_no: runner?.horse_no,
        horse_id: horseId,
        horse_name: horseNameMap.get(horseId) || horseId || `馬${runner?.horse_no || '?'}`,
        jockey: runner?.jockey,
        trainer: runner?.trainer,
        draw: runner?.draw,
        win_odds: runner?.win_odds,
        finish_position: finishPos,
        predicted_prob: pred.final_prob,
        expected_value: pred.expected_value,
        kelly_fraction: pred.kelly_fraction,
        is_top3_pick: idx < 3,
        finished_in_top3: finishPos != null && finishPos <= 3,
        is_winner: finishPos === 1,
      }
    })

    comparison.sort((a: any, b: any) => {
      const pa = a.finish_position ?? 999
      const pb = b.finish_position ?? 999
      return pa - pb
    })

    let keyFactors: any[] = []
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

    let top3Picks: any[] = []
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
      results: results,
      performance: perf,
      comparison,
      key_factors: keyFactors,
      top3_picks: top3Picks,
    })
  } catch (err: any) {
    console.error('[API /performance/[raceId]] error:', err)
    return NextResponse.json({ ok: false, error: err.message ?? 'Internal error' }, { status: 500 })
  }
}
