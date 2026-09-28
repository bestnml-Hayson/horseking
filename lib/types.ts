export interface Race {
  race_id: string
  race_date: string
  venue: string
  race_no: number
  distance: number | null
  going: string | null
  class_level: string | null
  race_time?: string | null
}

export interface RaceRunner {
  runner_id: string
  race_id: string
  horse_id: string
  horse_no: number
  jockey: string | null
  trainer: string | null
  actual_weight: number | null
  draw: number | null
  past_rating: number | null
  recent_form_score: number | null
  weight_carried_diff: number | null
  jockey_win_rate: number | null
  trainer_win_rate: number | null
  rest_days: number | null
  win_odds: number | null
  finish_position: number | null
  finish_time: number | null
  form_history: string | null
}

export interface ModelPrediction {
  prediction_id: string
  race_id: string
  runner_id: string
  raw_model_prob: number | null
  market_implied_prob: number | null
  final_prob: number | null
  expected_value: number | null
  kelly_fraction: number | null
}

export interface Horse {
  horse_id: string
  horse_name: string
  country: string | null
}

export interface RaceRow extends RaceRunner {
  horse_name: string
  prediction: ModelPrediction | null
}

export interface FormEntry {
  position: number
  race_date?: string
  distance?: number
  going?: string
  venue?: string
}

export interface HorseRaceHistory {
  race_id: string
  race_date: string | null
  venue: string | null
  race_no: number | null
  distance: number | null
  going: string | null
  finish_position: number | null
  horse_no: number
  win_odds: number | null
  jockey: string | null
  trainer: string | null
  weight_carried: number | null
  draw: number | null
  finish_time: number | null
  form_history: string | null
}

export interface HorseVenueStats {
  venue: string
  starts: number
  wins: number
  win_rate: number
  top3_rate: number
}

export interface HorseDetail {
  horse_id: string
  horse_name: string
  country: string | null
  recent_form: number[]
  race_history: HorseRaceHistory[]
  total_starts: number
  total_wins: number
  total_places: number
  total_shows: number
  total_fourth: number
  win_rate: number
  top3_rate: number
  top4_rate: number
  avg_odds: number
  venue_stats: HorseVenueStats[]
  best_distance: string | null
  jockey_partners: { name: string; rides: number; wins: number }[]
}
