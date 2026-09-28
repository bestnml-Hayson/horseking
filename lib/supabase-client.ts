import { createBrowserClient } from '@supabase/ssr'
import type { Race, RaceRunner, ModelPrediction, Horse } from './types'

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
