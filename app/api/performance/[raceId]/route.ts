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

    const runnerMap = new Map((runners ?? []).map((r: any) => [r.runner_id, r]))
    const predMap = new Map((predictions ?? []).map((p: any) => [p.runner_id, p]))

    const sortedPreds = (predictions ?? []).sort(
      (a: any, b: any) => (b.final_prob ?? 0) - (a.final_prob ?? 0)
    )

    const comparison = sortedPreds.map((pred: any, idx: number) => {
      const runner = runnerMap.get(pred.runner_id)
      return {
        rank: idx + 1,
        runner_id: pred.runner_id,
        horse_no: runner?.horse_no,
        horse_id: runner?.horse_id,
        horse_name: runner?.horse_name || runner?.horse_id || `馬${runner?.horse_no || '?'}`,
        jockey: runner?.jockey,
        trainer: runner?.trainer,
        draw: runner?.draw,
        win_odds: runner?.win_odds,
        finish_position: runner?.finish_position,
        predicted_prob: pred.final_prob,
        expected_value: pred.expected_value,
        kelly_fraction: pred.kelly_fraction,
        is_top3_pick: idx < 3,
        finished_in_top3: runner?.finish_position != null && runner.finish_position <= 3,
        is_winner: runner?.finish_position === 1,
      }
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
