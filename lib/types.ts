export interface Race {
  race_id: string
  race_date: string
  venue: string
  race_no: number
  distance: number | null
  going: string | null
  class_level: string | null
  is_finished?: boolean
  race_time?: string | null
  track_course?: string | null
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
  official_rating: number | null
  recent_form_score: number | null
  weight_carried_diff: number | null
  jockey_win_rate: number | null
  trainer_win_rate: number | null
  rest_days: number | null
  win_odds: number | null
  finish_position: number | null
  finish_time: number | null
  form_history: string | null
  age: number | null
  career_starts: number | null
  career_wins: number | null
  career_places: number | null
  total_prize_money: number | null
  declared_weight: number | null
  sectional_times: string | null
  margin: number | null
  weight_change: number | null
  best_time: string | null
  gender: string | null
  season_prize: number | null
  priority: string | null
  gear: string | null
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
  sire?: string | null
  dam?: string | null
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
  track_course: string | null
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
  official_rating: number | null
  jockey_win_rate: number | null
  trainer_win_rate: number | null
  rest_days: number | null
  recent_form_score: number | null
  declared_weight: number | null
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

export interface RaceResult {
  race_id: string
  race_date: string
  venue: string
  race_no: number
  finish_position: number
  horse_no: number
  horse_name: string
  jockey: string
  trainer: string
  win_odds: number | null
  margin: number | null
  official_rating: number | null
}

export interface AIPerformanceRecord {
  race_id: string
  race_date: string
  venue: string
  race_no: number
  top1_pick_runner_id: string | null
  top1_pick_finish_pos: number | null
  top1_hit: boolean
  top3_picks: string | null
  top3_hit_count: number
  total_bets: number
  total_returns: number
  roi_percent: number
  key_factors: string | null
  pace_analysis: string | null
  draw_bias: string | null
  market_move: string | null
  analysis_date: string
}

export interface ComparisonRow {
  rank: number
  runner_id: string
  horse_no: number
  horse_id: string
  horse_name: string
  jockey: string | null
  trainer: string | null
  draw: number | null
  win_odds: number | null
  finish_position: number | null
  predicted_prob: number | null
  expected_value: number | null
  kelly_fraction: number | null
  is_top3_pick: boolean
  finished_in_top3: boolean
  is_winner: boolean
  official_rating: number | null
  jockey_win_rate: number | null
  trainer_win_rate: number | null
  weight_carried_diff: number | null
  declared_weight: number | null
}

export interface APIResponse<T> {
  ok: boolean
  error?: string
  data?: T
}
