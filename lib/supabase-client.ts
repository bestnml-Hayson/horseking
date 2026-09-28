import { createBrowserClient } from '@supabase/ssr'
import type { Race, RaceRunner, ModelPrediction, Horse, HorseDetail } from './types'

function getSupabase() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}

export async function fetchLatestRaces(): Promise<Race[]> {
  const supabase = getSupabase()
  const today = new Date().toISOString().split('T')[0]

  const { data: allCandidateRaces, error: candidateError } = await supabase
    .from('races')
    .select('race_id, race_date, venue')
    .gte('race_date', today)
    .order('race_date', { ascending: true })
    .order('race_no', { ascending: true })

  if (candidateError) {
    console.error('[fetchLatestRaces] candidate query error:', candidateError)
    throw candidateError
  }

  let targetDate: string | null = null
  let targetVenue: string | null = null

  if (allCandidateRaces && allCandidateRaces.length > 0) {
    const raceIds = allCandidateRaces.map(r => r.race_id)
    const { data: existingRunners } = await supabase
      .from('race_runners')
      .select('race_id')
      .in('race_id', raceIds)

    const validRaceIds = new Set(existingRunners?.map(r => r.race_id) ?? [])
    for (const race of allCandidateRaces) {
      if (validRaceIds.has(race.race_id)) {
        targetDate = race.race_date
        targetVenue = race.venue
        break
      }
    }
  }

  if (!targetDate) {
    const { data: latestRaces } = await supabase
      .from('races')
      .select('race_id, race_date, venue')
      .order('race_date', { ascending: false })
      .order('race_no', { ascending: true })

    if (latestRaces && latestRaces.length > 0) {
      const raceIds = latestRaces.map(r => r.race_id)
      const { data: existingRunners } = await supabase
        .from('race_runners')
        .select('race_id')
        .in('race_id', raceIds)

      const validRaceIds = new Set(existingRunners?.map(r => r.race_id) ?? [])
      for (const race of latestRaces) {
        if (validRaceIds.has(race.race_id)) {
          targetDate = race.race_date
          targetVenue = race.venue
          break
        }
      }
    }
  }

  if (!targetDate || !targetVenue) {
    console.warn('[fetchLatestRaces] No races with runners found')
    return []
  }

  console.log(`[fetchLatestRaces] Locking to ${targetDate} ${targetVenue}`)

  const { data, error } = await supabase
    .from('races')
    .select('*')
    .eq('race_date', targetDate)
    .eq('venue', targetVenue)
    .order('race_no', { ascending: true })

  if (error) {
    console.error('[fetchLatestRaces] races query error:', error)
    throw error
  }
  console.log(`[fetchLatestRaces] Found ${data?.length ?? 0} races at ${targetVenue}`)
  return data ?? []
}

export async function fetchRaceRunners(raceId: string): Promise<RaceRunner[]> {
  const supabase = getSupabase()
  const { data, error } = await supabase
    .from('race_runners')
    .select('*')
    .eq('race_id', raceId)
    .order('horse_no', { ascending: true })

  if (error) {
    console.error('[fetchRaceRunners] error:', error)
    throw error
  }
  return data ?? []
}

export async function fetchPredictions(raceId: string): Promise<ModelPrediction[]> {
  const supabase = getSupabase()
  const { data, error } = await supabase
    .from('model_predictions')
    .select('*')
    .eq('race_id', raceId)

  if (error) {
    console.error('[fetchPredictions] error:', error)
    throw error
  }
  return data ?? []
}

export async function fetchHorses(horseIds: string[]): Promise<Horse[]> {
  if (horseIds.length === 0) return []
  const supabase = getSupabase()
  const { data, error } = await supabase
    .from('horses')
    .select('horse_id, horse_name, country')
    .in('horse_id', horseIds)

  if (error) {
    console.error('[fetchHorses] error:', error)
    throw error
  }
  return data ?? []
}

export async function fetchHorseDetail(horseId: string): Promise<HorseDetail | null> {
  const supabase = getSupabase()

  const { data: horse, error: horseError } = await supabase
    .from('horses')
    .select('horse_id, horse_name, country')
    .eq('horse_id', horseId)
    .single()

  if (horseError || !horse) return null

  const { data: results, error: resultsError } = await supabase
    .from('race_results')
    .select('*')
    .eq('horse_no', horseId)
    .order('race_date', { ascending: false })
    .limit(20)

  if (resultsError) {
    console.error('[fetchHorseDetail] race_results error:', resultsError)
  }

  const raceHistory = (results ?? []).map((r: any) => ({
    race_id: r.race_id,
    race_date: r.race_date ?? null,
    venue: r.venue ?? null,
    race_no: r.race_no ?? null,
    distance: r.distance ?? null,
    going: r.going ?? null,
    finish_position: r.finish_position ?? null,
    horse_no: r.horse_no,
    win_odds: r.win_odds,
    jockey: r.jockey,
    trainer: r.trainer,
    weight_carried: null,
    draw: null,
    finish_time: null,
    form_history: null,
  }))

  const totalStarts = raceHistory.length
  const totalWins = raceHistory.filter(r => r.finish_position === 1).length
  const top3Count = raceHistory.filter(r => r.finish_position != null && r.finish_position <= 3).length

  const recentForm = raceHistory.slice(0, 6).map(r => r.finish_position).filter((p): p is number => p != null)

  return {
    horse_id: horse.horse_id,
    horse_name: horse.horse_name,
    country: horse.country,
    recent_form: recentForm,
    race_history: raceHistory,
    total_starts: totalStarts,
    total_wins: totalWins,
    total_places: 0,
    total_shows: 0,
    total_fourth: 0,
    win_rate: totalStarts > 0 ? (totalWins / totalStarts) * 100 : 0,
    top3_rate: totalStarts > 0 ? (top3Count / totalStarts) * 100 : 0,
    top4_rate: 0,
    avg_odds: 0,
    venue_stats: [],
    best_distance: null,
    jockey_partners: [],
  }
}
