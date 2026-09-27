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

  const { data: latestRace, error: latestError } = await supabase
    .from('races')
    .select('race_date, venue')
    .order('race_date', { ascending: false })
    .order('race_id', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (latestError) {
    console.error('[fetchLatestRaces] latest race query error:', latestError)
    throw latestError
  }
  if (!latestRace?.race_date || !latestRace?.venue) {
    console.warn('[fetchLatestRaces] No races found in database')
    return []
  }

  console.log(`[fetchLatestRaces] Locking to ${latestRace.race_date} ${latestRace.venue}`)

  const { data, error } = await supabase
    .from('races')
    .select('*')
    .eq('race_date', latestRace.race_date)
    .eq('venue', latestRace.venue)
    .order('race_no', { ascending: true })

  if (error) {
    console.error('[fetchLatestRaces] races query error:', error)
    throw error
  }
  console.log(`[fetchLatestRaces] Found ${data?.length ?? 0} races at ${latestRace.venue}`)
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
