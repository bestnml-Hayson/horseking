import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url)
    const date = searchParams.get('date')

    if (!date) {
      return NextResponse.json({ ok: false, error: 'Missing date param' }, { status: 400 })
    }

    const supabase = getServerSupabase()

    const { data: races, error: racesError } = await supabase
      .from('races')
      .select('race_id,race_no,is_finished')
      .eq('race_date', date)
      .order('race_no')

    if (racesError) {
      if (racesError.message?.includes('Could not find') || racesError.code === '42P01') {
        return NextResponse.json({ ok: true, races: [], table_missing: true })
      }
      return NextResponse.json({ ok: false, error: racesError.message }, { status: 500 })
    }

    const raceList = (races ?? []) as Array<{ race_id: string; race_no: number; is_finished: boolean }>
    if (raceList.length === 0) {
      return NextResponse.json({ ok: true, races: [] })
    }

    const raceIds = raceList.map(r => r.race_id)

    const [runnersResp, predsResp, resultsResp, perfResp] = await Promise.all([
      supabase.from('race_runners')
        .select('race_id,runner_id,horse_no,win_odds,finish_position')
        .in('race_id', raceIds),
      supabase.from('model_predictions')
        .select('race_id,runner_id,raw_model_prob,market_implied_prob,final_prob,expected_value')
        .in('race_id', raceIds),
      supabase.from('race_results')
        .select('race_id,race_status')
        .in('race_id', raceIds),
      supabase.from('ai_performance')
        .select('race_id,top1_hit,roi_percent')
        .in('race_id', raceIds),
    ])

    type RunnerRow = { race_id: string; runner_id: string; horse_no: number; win_odds: number | null; finish_position: number | null }
    type PredRow = { race_id: string; runner_id: string; raw_model_prob: number | null; market_implied_prob: number | null; final_prob: number | null; expected_value: number | null }

    const runnersData = (runnersResp.data ?? []) as RunnerRow[]
    const predsData = (predsResp.data ?? []) as PredRow[]
    const resultsData = (resultsResp.data ?? []) as Array<{ race_id: string; race_status: string }>
    const perfData = (perfResp.data ?? []) as Array<{ race_id: string; top1_hit: boolean; roi_percent: number }>

    const runnersByRace = new Map<string, RunnerRow[]>()
    for (const r of runnersData) {
      const list = runnersByRace.get(r.race_id) ?? []
      list.push(r)
      runnersByRace.set(r.race_id, list)
    }

    const predsByRace = new Map<string, PredRow[]>()
    for (const p of predsData) {
      const list = predsByRace.get(p.race_id) ?? []
      list.push(p)
      predsByRace.set(p.race_id, list)
    }

    const resultsMap = new Map<string, { race_status: string }>()
    for (const r of resultsData) {
      resultsMap.set(r.race_id, r)
    }

    const perfMap = new Map<string, { top1_hit: boolean; roi_percent: number }>()
    for (const p of perfData) {
      perfMap.set(p.race_id, p)
    }

    const pipelineRaces = raceList.map(race => {
      const runners = runnersByRace.get(race.race_id) ?? []
      const preds = predsByRace.get(race.race_id) ?? []
      const result = resultsMap.get(race.race_id)
      const perf = perfMap.get(race.race_id)

      const hasRunners = runners.length > 0
      const hasOdds = runners.some(r => r.win_odds != null && r.win_odds > 0)
      const hasPredictions = preds.length > 0
      const hasFinalProb = preds.some(p => p.final_prob != null && p.final_prob > 0)
      const hasResults = runners.some(r => r.finish_position != null)
      const isFinished = race.is_finished === true
      const hasReview = perf != null

      let stage: string
      if (!hasRunners) {
        stage = 'stage0_no_data'
      } else if (!hasOdds) {
        stage = 'stage1_pre_race'
      } else if (!hasFinalProb) {
        stage = 'stage2_need_fusion'
      } else if (!hasResults) {
        stage = 'stage2_ready'
      } else if (!hasReview) {
        stage = 'stage3_need_review'
      } else {
        stage = 'stage3_complete'
      }

      return {
        race_id: race.race_id,
        race_no: race.race_no,
        is_finished: isFinished,
        runner_count: runners.length,
        has_odds: hasOdds,
        has_predictions: hasPredictions,
        has_final_prob: hasFinalProb,
        has_results: hasResults,
        has_review: hasReview,
        stage,
        review: perf ? { top1_hit: perf.top1_hit, roi_percent: perf.roi_percent } : null,
      }
    })

    return NextResponse.json({ ok: true, date, races: pipelineRaces })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Internal error'
    console.error('[API /pipeline/status] error:', err)
    return NextResponse.json({ ok: false, error: message }, { status: 500 })
  }
}
