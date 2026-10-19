import type { RaceRow, Race, ModelPrediction } from './types'
import type { HorseRaceRecord } from './supabase-client'
import { getFormColor } from './color-utils'

export { getFormColor }

const MODEL_WEIGHT = 0.5
const MARKET_WEIGHT = 0.5
const FRACTIONAL_KELLY = 0.25

// Temperature scaling for softmax (prevents extreme probability distribution)
// T=15 gives reasonable win probabilities: top horse ~18-25%, others ~3-10%
const SOFTMAX_TEMPERATURE = 15

// Dynamic weighting by racecourse — 9 factors total
export interface RacecourseWeights {
  form: number
  draw: number
  jockeyTrainer: number
  weight: number
  courseDistance: number
  restDays: number
  gear: number
  pace: number
  classMov: number
}

export function getWeightsByVenue(venue: string | undefined): RacecourseWeights {
  if (venue === 'HV') {
    return {
      form: 0.18, draw: 0.14, jockeyTrainer: 0.12, weight: 0.08,
      courseDistance: 0.16, restDays: 0.10, gear: 0.06, pace: 0.08, classMov: 0.08,
    }
  }
  return {
    form: 0.16, draw: 0.08, jockeyTrainer: 0.14, weight: 0.08,
    courseDistance: 0.18, restDays: 0.10, gear: 0.06, pace: 0.10, classMov: 0.10,
  }
}

function softmax(scores: number[], temperature: number = SOFTMAX_TEMPERATURE): number[] {
  if (scores.length === 0) return []
  const maxS = Math.max(...scores)
  // Apply temperature scaling: exp((score - max) / T)
  const exps = scores.map(s => Math.exp((s - maxS) / temperature))
  const total = exps.reduce((a, b) => a + b, 0)
  return total === 0 ? scores.map(() => 1 / scores.length) : exps.map(e => e / total)
}

/**
 * Compute course/distance specialization score (0-100).
 * Checks horse's past performance at same venue+distance.
 */
function computeCourseDistanceScore(
  row: RaceRow,
  race: Race | undefined,
  horseHistory: Map<string, HorseRaceRecord[]> | undefined,
): number {
  if (!race?.venue || !race?.distance || !horseHistory) return 50

  const history = horseHistory.get(row.horse_id)
  if (!history || history.length === 0) return 50

  const sameVenueDist = history.filter(
    h => h.venue === race.venue && h.distance === race.distance,
  )

  if (sameVenueDist.length === 0) {
    const sameVenue = history.filter(h => h.venue === race.venue)
    if (sameVenue.length === 0) return 45
    const avgPos = sameVenue.slice(0, 5).reduce((s, h) => s + h.finish_position, 0) / Math.min(sameVenue.length, 5)
    return Math.max(0, Math.min(100, (1 - (avgPos - 1) / 13) * 100))
  }

  const recent = sameVenueDist.slice(0, 5)
  const wins = recent.filter(h => h.finish_position === 1).length
  const top3 = recent.filter(h => h.finish_position <= 3).length
  const avgPos = recent.reduce((s, h) => s + h.finish_position, 0) / recent.length

  let score = 50
  score += wins * 15
  score += (top3 - wins) * 6
  score += Math.max(0, (5 - avgPos) * 5)
  return Math.max(0, Math.min(100, score))
}

/**
 * Compute rest days / freshness score (0-100).
 * Optimal rest: 21-42 days. Too short (<14) or too long (>90) is penalized.
 */
function computeRestDaysScore(row: RaceRow): number {
  const rest = row.rest_days
  if (rest == null) return 50

  if (rest >= 21 && rest <= 42) return 85 + Math.min(15, (rest - 21) * 0.5)
  if (rest >= 14 && rest < 21) return 65 + (rest - 14) * 3
  if (rest > 42 && rest <= 60) return 75 - (rest - 42) * 0.5
  if (rest > 60 && rest <= 90) return 65 - (rest - 60) * 0.3
  if (rest < 14) return 30 + rest * 2
  return 40
}

/**
 * Compute gear change bonus (0-100).
 * First-time gear (ending in "1") gets bonus, especially blinders (B1).
 */
function computeGearScore(row: RaceRow): number {
  const gear = row.gear
  if (!gear) return 50

  const parts = gear.split('/').map(g => g.trim()).filter(Boolean)
  const newGear = parts.filter(g => g.endsWith('1'))
  if (newGear.length === 0) return 50

  let score = 50
  for (const g of newGear) {
    const base = g.slice(0, -1)
    if (base === 'B') score += 14
    else if (base === 'PC' || base === 'H') score += 10
    else if (base === 'TT' || base === 'XB') score += 6
    else score += 8
  }
  return Math.max(0, Math.min(100, score))
}

/**
 * Compute pace scenario fit score (0-100).
 * Fast pace favors closers (high draw, poor early form), slow pace favors leaders (low draw).
 */
function computePaceScore(
  row: RaceRow,
  paceLabel: string,
  totalRunners: number,
): number {
  const draw = row.draw
  const form = parseFormHistory(row.form_history)
  const formAvg = form.length > 0 ? form.reduce((s, p) => s + p, 0) / form.length : 8

  let score = 50

  if (paceLabel === '快步速') {
    if (draw != null && draw >= 10) score += 18
    else if (draw != null && draw >= 7) score += 10
    if (formAvg > 6) score += 12
    if (draw != null && draw <= 4) score -= 10
  } else if (paceLabel === '慢步速') {
    if (draw != null && draw <= 4) score += 18
    else if (draw != null && draw <= 6) score += 10
    if (formAvg <= 4) score += 12
    if (draw != null && draw >= 10) score -= 10
  }

  return Math.max(0, Math.min(100, score))
}

/**
 * Compute class movement score (0-100).
 * Dropping in class = bonus, rising in class = penalty.
 */
function computeClassMovementScore(
  row: RaceRow,
  race: Race | undefined,
  horseHistory: Map<string, HorseRaceRecord[]> | undefined,
): number {
  if (!race?.class_level || !horseHistory) return 50

  const history = horseHistory.get(row.horse_id)
  if (!history || history.length === 0) return 50

  const recentClass = history[0]?.class_level
  if (!recentClass) return 50

  const classOrder = (c: string): number => {
    const m = c.match(/(\d+)/)
    return m ? parseInt(m[1], 10) : 5
  }

  const currentClass = classOrder(race.class_level)
  const prevClass = classOrder(recentClass)
  const diff = prevClass - currentClass

  if (diff > 0) return Math.min(100, 65 + diff * 10)
  if (diff < 0) return Math.max(0, 50 + diff * 8)
  return 55
}

/**
 * Compute the unified 9-component total score (0-100) for a single horse.
 * Uses dynamic weights based on racecourse (HV vs ST).
 */
function computeTotalScore(
  row: RaceRow,
  totalRunners: number,
  venue?: string,
  race?: Race,
  horseHistory?: Map<string, HorseRaceRecord[]>,
  paceLabel?: string,
): number {
  const w = getWeightsByVenue(venue)
  const form = parseFormHistory(row.form_history)
  const draw = row.draw
  const jockeyWr = row.jockey_win_rate ?? 0.1
  const trainerWr = row.trainer_win_rate ?? 0.1
  const weight = row.actual_weight

  const formAvg = form.length > 0 ? form.reduce((s, p) => s + p, 0) / form.length : 10
  const formScore = Math.max(0, Math.min(100, (1 - (formAvg - 1) / 13) * 100))

  const drawMax = Math.max(14, totalRunners)
  const drawScore = draw != null
    ? Math.max(0, Math.min(100, (1 - (draw - 1) / drawMax) * 100))
    : 50

  const jockeyScore = Math.max(0, Math.min(100, jockeyWr * 500))
  const trainerScore = Math.max(0, Math.min(100, trainerWr * 500))
  const jtScore = jockeyScore * 0.6 + trainerScore * 0.4

  let weightScore = 60
  if (weight != null) {
    if (weight <= 118) weightScore += 20
    else if (weight <= 124) weightScore += 10
    else if (weight >= 132) weightScore -= 15
    else if (weight >= 128) weightScore -= 5
  }
  weightScore = Math.max(0, Math.min(100, weightScore))

  const cdScore = computeCourseDistanceScore(row, race, horseHistory)
  const restScore = computeRestDaysScore(row)
  const gearScore = computeGearScore(row)
  const paceScore = computePaceScore(row, paceLabel ?? '中等步速', totalRunners)
  const classScore = computeClassMovementScore(row, race, horseHistory)

  return (
    formScore * w.form +
    drawScore * w.draw +
    jtScore * w.jockeyTrainer +
    weightScore * w.weight +
    cdScore * w.courseDistance +
    restScore * w.restDays +
    gearScore * w.gear +
    paceScore * w.pace +
    classScore * w.classMov
  )
}

export function computeClientPredictions(
  rows: RaceRow[],
  venue?: string,
  race?: Race,
  horseHistory?: Map<string, HorseRaceRecord[]>,
): RaceRow[] {
  if (rows.length === 0) return rows

  const pace = predictPace(rows)

  const totalScores = rows.map(r =>
    computeTotalScore(r, rows.length, venue, race, horseHistory, pace.label),
  )

  // P_MODEL = softmax of total scores
  const pModels = softmax(totalScores)

  const oddsList = rows.map(r => r.win_odds)
  const hasValidOdds = oddsList.some(o => o != null && o > 1)

  return rows.map((row, i) => {
    const pModel = pModels[i]

    if (!hasValidOdds) {
      const prediction: ModelPrediction = {
        prediction_id: `client-${row.runner_id}`,
        race_id: row.race_id,
        runner_id: row.runner_id,
        raw_model_prob: Math.round(pModel * 10000) / 10000,
        market_implied_prob: null,
        final_prob: Math.round(pModel * 10000) / 10000,
        expected_value: null,
        kelly_fraction: null,
      }
      return { ...row, prediction }
    }

    const pMarket = softmax(oddsList.map(o => (o != null && o > 1) ? 1 / o : 0))[i]
    const pFinal = MODEL_WEIGHT * pModel + MARKET_WEIGHT * pMarket
    const odds = row.win_odds
    const ev = (odds != null && odds > 1) ? pFinal * odds - 1 : null
    const fullKelly = (odds != null && odds > 1 && ev != null && ev > 0) ? ev / (odds - 1) : 0
    const kelly = Math.max(0, fullKelly * FRACTIONAL_KELLY)

    const prediction: ModelPrediction = {
      prediction_id: `client-${row.runner_id}`,
      race_id: row.race_id,
      runner_id: row.runner_id,
      raw_model_prob: Math.round(pModel * 10000) / 10000,
      market_implied_prob: Math.round(pMarket * 10000) / 10000,
      final_prob: Math.max(0, Math.min(1, Math.round(pFinal * 10000) / 10000)),
      expected_value: ev != null ? Math.round(ev * 10000) / 10000 : null,
      kelly_fraction: Math.round(kelly * 100000) / 100000,
    }

    return { ...row, prediction }
  })
}

/**
 * Recompute P_final, EV, Kelly from existing P_model and P_market values.
 * Uses the new linear fusion: P_final = 0.5*P_model + 0.5*P_market.
 * Preserves server-computed P_model and P_market, only updates fusion output.
 */
export function recomputePFusion(rows: RaceRow[]): RaceRow[] {
  return rows.map(row => {
    const pModel = row.prediction?.raw_model_prob ?? 0
    const pMarket = row.prediction?.market_implied_prob ?? null
    const odds = row.win_odds
    const hasOdds = odds != null && odds > 1

    if (pMarket == null || !hasOdds) {
      const prediction: ModelPrediction = {
        ...(row.prediction ?? {
          prediction_id: `client-${row.runner_id}`,
          race_id: row.race_id,
          runner_id: row.runner_id,
          raw_model_prob: pModel,
          market_implied_prob: null,
          final_prob: pModel,
          expected_value: null,
          kelly_fraction: null,
        }),
        market_implied_prob: null,
        final_prob: Math.round(pModel * 10000) / 10000,
        expected_value: null,
        kelly_fraction: null,
      }
      return { ...row, prediction }
    }

    const pFinal = MODEL_WEIGHT * pModel + MARKET_WEIGHT * pMarket
    const ev = pFinal * odds! - 1
    const fullKelly = ev > 0 ? ev / (odds! - 1) : 0
    const kelly = Math.max(0, fullKelly * FRACTIONAL_KELLY)

    const prediction: ModelPrediction = {
      ...(row.prediction ?? {
        prediction_id: `client-${row.runner_id}`,
        race_id: row.race_id,
        runner_id: row.runner_id,
        raw_model_prob: pModel,
        market_implied_prob: pMarket,
        final_prob: pFinal,
        expected_value: ev,
        kelly_fraction: kelly,
      }),
      final_prob: Math.max(0, Math.min(1, Math.round(pFinal * 10000) / 10000)),
      expected_value: Math.round(ev * 10000) / 10000,
      kelly_fraction: Math.round(kelly * 100000) / 100000,
    }

    return { ...row, prediction }
  })
}

/**
 * Compute AI composite score (0-100) from model predictions.
 * Weights: 60% P_final, 25% EV, 15% Kelly
 */
export function computeAIScore(row: RaceRow): number {
  const p = row.prediction?.final_prob ?? 0
  const ev = row.prediction?.expected_value ?? 0
  const kelly = row.prediction?.kelly_fraction ?? 0

  const pScore = Math.min(p * 500, 100)
  const evScore = Math.min(Math.max((ev + 0.1) * 200, 0), 100)
  const kellyScore = Math.min(kelly * 1000, 100)

  return Math.round(pScore * 0.6 + evScore * 0.25 + kellyScore * 0.15)
}

/**
 * Generate expert analysis text for a horse.
 */
export function generateExpertAnalysis(row: RaceRow, rank: number): string {
  const p = row.prediction?.final_prob ?? 0
  const ev = row.prediction?.expected_value ?? 0
  const kelly = row.prediction?.kelly_fraction ?? 0
  const odds = row.win_odds ?? 0
  const draw = row.draw ?? 0

  const phrases: string[] = []

  if (rank === 1) {
    phrases.push('模型評分最高')
    if (p > 0.20) phrases.push('具備爭勝實力')
    if (draw <= 4) phrases.push('內檔有利')
    if (draw >= 10) phrases.push('外檔需克服')
  } else if (rank === 2) {
    phrases.push('次選馬匹')
    if (ev > 0.15) phrases.push('具投注價值')
    if (odds > 0 && odds < 8) phrases.push('賠率合理')
  } else if (rank === 3) {
    phrases.push('第三選擇')
    if (kelly > 0) phrases.push('Kelly 正期望')
  } else {
    phrases.push('第四選擇')
    if (ev > 0.20) phrases.push('冷門價值高')
  }

  if (row.actual_weight && row.actual_weight < 120) {
    phrases.push('負磅輕')
  }

  return phrases.join('，') + '。'
}

/**
 * Predict race pace scenario from runner data.
 */
export function predictPace(rows: RaceRow[]): { label: string; detail: string } {
  if (rows.length === 0) {
    return { label: '未知', detail: '暫無數據' }
  }

  const avgWeight = rows.reduce((s, r) => s + (r.actual_weight ?? 126), 0) / rows.length
  const lowDraws = rows.filter(r => (r.draw ?? 99) <= 4).length
  const highDraws = rows.filter(r => (r.draw ?? 0) >= 10).length

  let paceLabel = '中等步速'
  let detail = ''

  if (avgWeight < 122) {
    paceLabel = '快步速'
    detail = `平均負磅 ${avgWeight.toFixed(1)} 磅，前速馬偏多，預計後追馬有利`
  } else if (avgWeight > 128) {
    paceLabel = '慢步速'
    detail = `平均負磅 ${avgWeight.toFixed(1)} 磅，領放馬少，預計前領馬有利`
  } else {
    detail = `平均負磅 ${avgWeight.toFixed(1)} 磅，步速預計中等`
  }

  if (lowDraws > rows.length * 0.4) {
    detail += '；內檔馬偏多，欄位偏向內側'
  } else if (highDraws > rows.length * 0.4) {
    detail += '；外檔馬偏多，注意外側擠迫'
  }

  return { label: paceLabel, detail }
}

/**
 * Get going status display.
 */
export function getGoingInfo(race: Race | undefined): { label: string; bias: string } {
  const going = race?.going ?? '好地'
  let bias = '場地均勻，無明顯偏差'

  if (going.includes('快')) {
    bias = '快地偏利前領馬，後追馬需留意'
  } else if (going.includes('軟') || going.includes('黏')) {
    bias = '偏軟場地，留意馬匹場地適應力'
  } else if (going.includes('慢')) {
    bias = '慢地，體力消耗較大'
  }

  return { label: going, bias }
}

/**
 * Sort rows by P_model (pure ability, no odds) descending.
 * Ensures "AI 精選 4 膽" reflects true model strength ranking.
 */
/**
 * Get top N picks sorted by P_final (model + market fusion).
 */
export function getTopPicks(rows: RaceRow[], n: number = 4): RaceRow[] {
  return [...rows].sort((a, b) =>
    (b.prediction?.final_prob ?? 0) - (a.prediction?.final_prob ?? 0)
  ).slice(0, n)
}

/**
 * Compute best WIN/PLACE bet (highest EV with positive Kelly).
 */
export function getBestWinBet(rows: RaceRow[]): RaceRow | null {
  const withPred = rows.filter(r =>
    r.prediction?.expected_value != null &&
    r.prediction?.kelly_fraction != null &&
    r.prediction.kelly_fraction > 0 &&
    r.prediction.expected_value > 0.15
  )
  if (withPred.length === 0) return null
  return withPred.sort((a, b) => (b.prediction!.expected_value! - a.prediction!.expected_value!))[0]
}

/**
 * Compute best Q (連贏) combination: top pick as anchor + next 3.
 */
export function getQCombination(rows: RaceRow[]): { anchor: RaceRow; legs: RaceRow[] } | null {
  const top4 = getTopPicks(rows, 4)
  if (top4.length < 2) return null
  return { anchor: top4[0], legs: top4.slice(1) }
}

/**
 * Compute best Trio (單T) combination: top 4 horses.
 */
export function getTrioCombination(rows: RaceRow[]): RaceRow[] | null {
  const top4 = getTopPicks(rows, 4)
  if (top4.length < 3) return null
  return top4
}

/**
 * Format odds display.
 */
export function fmtOdds(odds: number | null): string {
  if (odds == null || odds <= 0) return '待定'
  return odds.toFixed(1)
}

export function isOddsPending(odds: number | null): boolean {
  return odds == null || odds <= 0
}

/**
 * Format Kelly percentage.
 */
export function fmtKelly(kelly: number | null): string {
  if (!kelly || kelly <= 0) return '-'
  return (kelly * 100).toFixed(2) + '%'
}

/**
 * Format EV percentage.
 */
export function fmtEV(ev: number | null): string {
  if (ev == null) return '-'
  const sign = ev > 0 ? '+' : ''
  return sign + (ev * 100).toFixed(1) + '%'
}

/**
 * Parse form_history string (e.g. "12-8-9-9-11-5") into number array.
 * Handles mixed content like "第 2 場(806) 3-5-7" by extracting only valid finish positions (1-20).
 */
export function parseFormHistory(form: string | null | undefined): number[] {
  if (!form) return []
  // Remove JSON-like noise and extract all numbers
  const cleaned = form.replace(/[{}"':]/g, ' ')
  // Extract all numbers from the string
  const numbers = cleaned.match(/\d+/g) ?? []
  // Parse and filter to valid finish positions (1-20)
  return numbers
    .map(s => parseInt(s, 10))
    .filter(n => !isNaN(n) && n > 0 && n <= 20)
    .slice(0, 6)
}

/**
 * Estimate race start time based on venue and race number.
 * Shatin: first race 13:00 (day) / 19:15 (night), ~35 min apart
 * Happy Valley: first race 19:15, ~30 min apart
 */
const ACTUAL_RACE_TIMES: Record<string, string[]> = {
  '2026-10-04': ['12:30', '13:00', '13:30', '14:00', '14:30', '15:00', '15:35', '16:05', '16:35', '17:10', '17:45'],
  '2026-10-07': ['18:35', '19:05', '19:35', '20:05', '20:35', '21:05', '21:35', '22:05', '22:35'],
  '2026-10-14': ['18:35', '19:05', '19:35', '20:05', '20:35', '21:05', '21:35', '22:05', '22:35'],
}

export function estimateRaceTime(venue: string | undefined, raceNo: number, raceDate?: string | null): string {
  if (raceDate) {
    const d = typeof raceDate === 'string' ? raceDate.slice(0, 10) : null
    const times = d ? ACTUAL_RACE_TIMES[d] : undefined
    if (times && raceNo >= 1 && raceNo <= times.length) return times[raceNo - 1]
  }

  const isHV = venue === 'HV'
  const baseHour = isHV ? 19 : 13
  const baseMin = isHV ? 15 : 0
  const interval = isHV ? 30 : 35

  const totalMin = baseHour * 60 + baseMin + (raceNo - 1) * interval
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
}

/**
 * Generate comprehensive AI race analysis text.
 */
export function generateRaceAnalysis(rows: RaceRow[], race: Race | undefined, topPicks: RaceRow[]): {
  paceLabel: string
  paceDetail: string
  keyFactors: { type: string; text: string; impact: 'positive' | 'negative' | 'neutral' }[]
  modelLogic: string
} {
  const pace = predictPace(rows)
  const going = getGoingInfo(race)

  const keyFactors: { type: string; text: string; impact: 'positive' | 'negative' | 'neutral' }[] = []

  // Draw bias analysis
  const avgDraw = rows.length > 0
    ? rows.reduce((s, r) => s + (r.draw ?? 7), 0) / rows.length
    : 7
  const lowDrawCount = rows.filter(r => (r.draw ?? 99) <= 4).length
  if (lowDrawCount > rows.length * 0.4) {
    keyFactors.push({
      type: 'draw_bias',
      text: `內檔馬偏多 (${lowDrawCount}/${rows.length} 匹 ≤ 4 檔)，有利前領/跟前馬搶佔內欄位置`,
      impact: 'neutral',
    })
  }

  // Distance/class factor
  const dist = race?.distance ?? 0
  if (dist <= 1200) {
    keyFactors.push({
      type: 'distance',
      text: `短途賽 (${dist}m)，速度型馬匹佔優，起步反應至關重要`,
      impact: 'positive',
    })
  } else if (dist >= 2000) {
    keyFactors.push({
      type: 'distance',
      text: `長途賽 (${dist}m)，耐力與氣量為關鍵，後勁充沛馬匹看俏`,
      impact: 'positive',
    })
  }

  // Going bias
  if (going.bias !== '場地均勻，無明顯偏差') {
    keyFactors.push({
      type: 'going',
      text: going.bias,
      impact: 'neutral',
    })
  }

  // Jockey/trainer combo strength
  const topJockeys = rows.filter(r => (r.jockey_win_rate ?? 0) > 0.15).length
  if (topJockeys >= 3) {
    keyFactors.push({
      type: 'jockey',
      text: `${topJockeys} 位騎師近績 > 15% 勝率，頂尖騎練組合集中`,
      impact: 'positive',
    })
  }

  // Value bets presence
  const valueBets = rows.filter(r => (r.prediction?.expected_value ?? 0) > 0.15 && (r.prediction?.kelly_fraction ?? 0) > 0)
  if (valueBets.length > 0) {
    keyFactors.push({
      type: 'value',
      text: `${valueBets.length} 匹馬具正期望值 (EV > 15%)，市場可能低估`,
      impact: 'positive',
    })
  }

  // Model logic explanation — two-stage architecture
  const top1 = topPicks[0]
  const top2 = topPicks[1]
  const logicParts: string[] = []

  if (top1) {
    const pm1 = top1.prediction?.raw_model_prob ?? 0
    const ev1 = top1.prediction?.expected_value ?? 0
    logicParts.push(
      `首選「${top1.horse_name}」純實力評分最高 (P_model ${(pm1 * 100).toFixed(1)}%)` +
      (ev1 > 0 ? `，融合賠率後 EV +${(ev1 * 100).toFixed(1)}% 具價值` : '')
    )
  }
  if (top2) {
    const pm2 = top2.prediction?.raw_model_prob ?? 0
    logicParts.push(`次選「${top2.horse_name}」純實力 P_model ${(pm2 * 100).toFixed(1)}%`)
  }

  const modelLogic = logicParts.length > 0
    ? `Benter 兩階段模型：階段一以往績、檔位、騎練等特徵計算純實力 P_model；階段二融合市場賠率生成 P_final。${logicParts.join('；')}。`
    : 'Benter 兩階段模型：階段一計算純實力 P_model，階段二融合市場賠率生成 P_final，輸出各馬勝率及期望值。'

  return {
    paceLabel: pace.label,
    paceDetail: pace.detail,
    keyFactors,
    modelLogic,
  }
}

function analyzeFormTrend(form: number[]): { trend: 'improving' | 'declining' | 'consistent' | 'mixed'; avg: number; recent3Avg: number } {
  if (form.length === 0) return { trend: 'consistent', avg: 0, recent3Avg: 0 }
  const avg = form.reduce((s, p) => s + p, 0) / form.length
  const recent = form.slice(0, 3)
  const recent3Avg = recent.length > 0 ? recent.reduce((s, p) => s + p, 0) / recent.length : avg
  const older = form.slice(3)
  const olderAvg = older.length > 0 ? older.reduce((s, p) => s + p, 0) / older.length : avg

  if (recent3Avg < olderAvg - 2) return { trend: 'improving', avg, recent3Avg }
  if (recent3Avg > olderAvg + 2) return { trend: 'declining', avg, recent3Avg }
  if (form.every(p => Math.abs(p - avg) <= 3)) return { trend: 'consistent', avg, recent3Avg }
  return { trend: 'mixed', avg, recent3Avg }
}

/**
 * Quant Insight Engine v2 — 機構級三段式量化評語
 *
 * Returns structured insight with tag + 3 parts:
 *   tag: classification label (e.g. 強勢頭馬膽, 高EV爆發腳)
 *   base: 實力與動態評估
 *   tactical: 戰術、檔位與賽道剖析
 *   recommendation: 量化戰術定位與投注建議
 */
export interface QuantInsight {
  tag: string
  tagClass: 'elite' | 'value' | 'underlay' | 'longshot' | 'solid' | 'weak'
  base: string
  tactical: string
  recommendation: string
}

export function generateQuantInsight(
  row: RaceRow,
  rank: number,
  totalRunners: number,
  paceLabel?: string
): QuantInsight {
  const pred = row.prediction
  const pModel = pred?.raw_model_prob ?? null
  const pMarket = pred?.market_implied_prob ?? null
  const pFinal = pred?.final_prob ?? null
  const ev = pred?.expected_value ?? null
  const kelly = pred?.kelly_fraction ?? null
  const draw = row.draw
  const weight = row.actual_weight
  const jockey = row.jockey
  const trainer = row.trainer
  const jockeyWr = row.jockey_win_rate
  const trainerWr = row.trainer_win_rate
  const odds = row.win_odds
  const form = parseFormHistory(row.form_history)
  const formTrend = analyzeFormTrend(form)
  const gear = row.gear
  const restDays = row.rest_days

  const pModelPct = pModel != null ? pModel * 100 : 0
  const pMarketPct = pMarket != null ? pMarket * 100 : 0
  const evPct = ev != null ? ev * 100 : 0

  // === PART 1: 實力與動態評估 (Base Class & Synergy) ===
  const baseParts: string[] = []

  if (form.length > 0) {
    const formAvg = form.reduce((s, p) => s + p, 0) / form.length
    if (formTrend.trend === 'improving') {
      baseParts.push(`近 ${form.length} 戰走勢回升（均名次 ${formAvg.toFixed(1)}），狀態進入巔峰`)
    } else if (formTrend.trend === 'consistent' && formAvg <= 5) {
      baseParts.push(`近績穩定靠前（均名次 ${formAvg.toFixed(1)}），水準一貫可靠`)
    } else if (formTrend.trend === 'declining') {
      baseParts.push(`近 ${form.length} 戰走勢下滑（均名次 ${formAvg.toFixed(1)}），狀態存疑`)
    } else {
      baseParts.push(`近 ${form.length} 戰均名次 ${formAvg.toFixed(1)}，表現起伏`)
    }
  } else {
    baseParts.push('暫無近績數據')
  }

  const jtWr = jockeyWr != null && trainerWr != null
    ? jockeyWr * 0.6 + trainerWr * 0.4
    : null
  if (jtWr != null && jtWr >= 0.15) {
    baseParts.push(`騎練契合度 ${(jtWr * 100).toFixed(1)}%（${jockey ?? '-'}/${trainer ?? '-'}），屬頂級組合`)
  } else if (jtWr != null && jtWr >= 0.10) {
    baseParts.push(`騎練組合${jockey ?? '-'}／${trainer ?? '-'}，配合不俗`)
  }

  if (form.length >= 2 && form[0] <= 3) {
    baseParts.push(`上場跑第 ${form[0]} 名，狀態正佳`)
  }

  if (restDays != null && restDays >= 90) {
    baseParts.push(`久休 ${restDays} 天復出， freshness 待驗證`)
  } else if (restDays != null && restDays <= 14) {
    baseParts.push(`僅休 ${restDays} 天，頻密出賽需留意體力`)
  }

  if (gear) {
    const gearParts = gear.split('/').map(g => g.trim()).filter(Boolean)
    const newGear = gearParts.filter(g => g.endsWith('1'))
    if (newGear.length > 0) {
      const gearNames: Record<string, string> = {
        'B1': '眼罩', 'B': '眼罩', 'TT1': '吐舌帶', 'TT': '吐舌帶',
        'XB1': '開孔眼罩', 'XB': '開孔眼罩', 'V1': '眼罩', 'V': '眼罩',
        'P1': '眼罩', 'P': '眼罩', 'H1': '頭罩', 'H': '頭罩',
      }
      const gearDesc = newGear.map(g => {
        const base = g.replace(/\d$/, '')
        return gearNames[g] || gearNames[base] || g
      }).join('、')
      baseParts.push(`初戴${gearDesc}，具新鮮感加成`)
    }
  }

  // === PART 2: 戰術、檔位與賽道剖析 (Tactical & Course Bias) ===
  const tacticalParts: string[] = []

  if (draw != null) {
    if (draw <= 3) {
      tacticalParts.push(`排 ${draw} 檔內檔，搶先佔欄位有利`)
    } else if (draw <= 6) {
      tacticalParts.push(`排 ${draw} 檔中內檔，位置靈活`)
    } else if (draw <= 9) {
      tacticalParts.push(`排 ${draw} 檔中檔，需視步速決定走位`)
    } else if (draw <= 11) {
      tacticalParts.push(`排 ${draw} 檔偏外，須多走路程搶位`)
    } else {
      tacticalParts.push(`排 ${draw} 檔大外檔，形勢受壓`)
    }
  }

  if (weight != null) {
    if (weight <= 118) {
      tacticalParts.push(`負 ${weight} 磅輕磅出擊，減磅優勢明顯`)
    } else if (weight >= 132) {
      tacticalParts.push(`頂磅 ${weight} 磅，長途負擔較重`)
    }
  }

  if (paceLabel) {
    if (paceLabel === '慢步速' && draw != null && draw <= 5) {
      tacticalParts.push('慢步速形勢下，內檔可輕鬆前領佔先')
    } else if (paceLabel === '快步速' && formTrend.trend === 'improving') {
      tacticalParts.push('快步速有利後上馬發力，近績回升者受惠')
    } else if (paceLabel === '快步速' && draw != null && draw <= 4) {
      tacticalParts.push('快步速下內檔馬可節省路程，等候衝刺')
    }
  }

  // === PART 3: 量化戰術定位與投注建議 + TAG ===
  let tag = ''
  let tagClass: QuantInsight['tagClass'] = 'solid'
  const recParts: string[] = []

  if (pModel != null && pModel >= 0.20) {
    tag = '強勢頭馬膽'
    tagClass = 'elite'
    recParts.push(`P_model ${pModelPct.toFixed(1)}% 為本場核心，建議作為連贏／三重彩主力馬膽`)
  } else if (pModel != null && pModel >= 0.12) {
    if (ev != null && ev > 0) {
      tag = '高EV爆發腳'
      tagClass = 'value'
      recParts.push(`P_model ${pModelPct.toFixed(1)}% 具顯著 Overlay（EV ${evPct > 0 ? '+' : ''}${evPct.toFixed(1)}%），極具冷門配腳價值`)
    } else if (ev != null && ev < -0.20 && pMarket != null && pMarket > pModel) {
      tag = '過熱防呆'
      tagClass = 'underlay'
      recParts.push(`P_model ${pModelPct.toFixed(1)}% 但市場追捧過熱（P_market ${pMarketPct.toFixed(1)}%），性價比低，建議觀望或僅做 Q 腳`)
    } else {
      tag = '穩健配腳'
      tagClass = 'solid'
      recParts.push(`P_model ${pModelPct.toFixed(1)}%，模型評分穩居前列，適合作位置 Q／三重彩配腳`)
    }
  } else if (pModel != null && pModel >= 0.075) {
    if (ev != null && ev > 0.10) {
      tag = '冷門價值馬'
      tagClass = 'value'
      recParts.push(`P_model ${pModelPct.toFixed(1)}%，EV +${evPct.toFixed(1)}% 正期望，四連環／位置 Q 冷腳之選`)
    } else if (pMarket != null && pMarket < 0.05) {
      tag = '潛伏爆冷馬'
      tagClass = 'longshot'
      recParts.push(`P_model ${pModelPct.toFixed(1)}% 被市場忽視（P_market ${pMarketPct.toFixed(1)}%），具爆冷潛質`)
    } else {
      tag = '中游配腳'
      tagClass = 'solid'
      recParts.push(`P_model ${pModelPct.toFixed(1)}%，適合作四連環冷腳配搭`)
    }
  } else {
    tag = '觀望'
    tagClass = 'weak'
    recParts.push(`P_model ${pModelPct.toFixed(1)}%，模型評分偏低，建議觀望`)
  }

  if (kelly != null && kelly > 0 && ev != null && ev > 0) {
    recParts.push(`Kelly 注碼 ${(kelly * 100).toFixed(2)}%，可考慮獨贏下注`)
  }

  return {
    tag,
    tagClass,
    base: baseParts.join('。') + '。',
    tactical: tacticalParts.join('。') + '。',
    recommendation: recParts.join('。') + '。',
  }
}

/**
 * Legacy string-based insight for backward compatibility.
 * Delegates to generateQuantInsight and formats as a single string.
 */
export function generateHorseInsight(
  row: RaceRow,
  rank: number,
  totalRunners: number,
  paceLabel?: string
): string {
  const insight = generateQuantInsight(row, rank, totalRunners, paceLabel)
  return `【${insight.tag}】${insight.base}｜${insight.tactical}｜${insight.recommendation}`
}

export function generateHorseComprehensiveInsight(
  detail: {
    horse_name: string
    total_starts: number
    total_wins: number
    win_rate: number
    top3_rate: number
    recent_form: number[]
    venue_stats: { venue: string; starts: number; wins: number; win_rate: number; top3_rate: number }[]
    best_distance: string | null
    jockey_partners: { name: string; rides: number; wins: number }[]
    avg_odds: number
  },
  raceRow?: RaceRow | null
): string {
  const parts: string[] = []
  const d = detail

  if (d.total_starts >= 5 && d.win_rate >= 15) {
    parts.push(`${d.horse_name} 生涯 ${d.total_starts} 戰 ${d.total_wins} 勝，勝率 ${d.win_rate.toFixed(1)}%，前三率 ${d.top3_rate.toFixed(1)}%，屬穩定型賽馬`)
  } else if (d.total_starts >= 5) {
    parts.push(`${d.horse_name} 生涯 ${d.total_starts} 戰，勝率 ${d.win_rate.toFixed(1)}%，前三率 ${d.top3_rate.toFixed(1)}%`)
  } else if (d.total_starts > 0) {
    parts.push(`${d.horse_name} 出賽經驗尚淺（${d.total_starts} 場）`)
  } else {
    parts.push(`${d.horse_name} 暫無歷史賽績記錄`)
  }

  const formTrend = analyzeFormTrend(d.recent_form)
  if (d.recent_form.length >= 3) {
    if (formTrend.trend === 'improving') {
      parts.push('近期走勢明顯回升，狀態進入巔峰期')
    } else if (formTrend.trend === 'declining') {
      parts.push('近績走勢下滑，需留意狀態是否見頂')
    } else if (formTrend.trend === 'consistent' && formTrend.avg <= 4) {
      parts.push('近績穩定靠前，表現一貫可靠')
    } else {
      parts.push('近績表現起伏不定')
    }
  }

  if (d.best_distance) {
    parts.push(`最佳路程為${d.best_distance}，留意今場路程是否配合`)
  }

  if (d.venue_stats.length > 0) {
    const st = d.venue_stats.find(v => v.venue === 'ST')
    const hv = d.venue_stats.find(v => v.venue === 'HV')
    if (st && st.starts >= 3 && st.win_rate >= 15) {
      parts.push('沙田戰績出色，適應該場地')
    }
    if (hv && hv.starts >= 3 && hv.win_rate >= 15) {
      parts.push('跑馬地戰績優異，擅長此場地')
    }
  }

  if (d.jockey_partners.length > 0) {
    const top = d.jockey_partners[0]
    if (top.rides >= 3 && top.wins >= 1) {
      parts.push(`與騎師 ${top.name} 合作 ${top.rides} 次贏 ${top.wins} 場，默契不俗`)
    }
  }

  if (raceRow) {
    const draw = raceRow.draw
    const weight = raceRow.actual_weight
    const pFinal = raceRow.prediction?.final_prob
    const ev = raceRow.prediction?.expected_value

    if (draw != null && draw <= 4) {
      parts.push(`今場排 ${draw} 檔內檔有利`)
    } else if (draw != null && draw >= 11) {
      parts.push(`今場排 ${draw} 檔大外檔需克服`)
    }

    if (weight != null && weight <= 118) {
      parts.push('負磅輕，有減磅優勢')
    } else if (weight != null && weight >= 132) {
      parts.push('頂磅出擊，負擔較重')
    }

    if (pFinal != null && pFinal >= 0.18) {
      parts.push(`Benter 模型計算奪魁機會 ${(pFinal * 100).toFixed(1)}%`)
    }
    if (ev != null && ev > 0.15) {
      parts.push('期望值正，具投注價值')
    }
  }

  return parts.join('。') + '。'
}

export interface FormSubIndices {
  avgFinish: number | null
  bestFinish: number | null
  trendLabel: '上升' | '下滑' | '穩定' | '起伏'
  trendScore: number
  lastRacePos: number | null
}

export interface DrawSubIndices {
  drawBiasCoeff: number
  trackBiasIndex: number
  drawAdvantage: '內檔有利' | '中檔中性' | '外檔不利'
}

export interface JockeyTrainerSubIndices {
  jockeyWinRate: number
  trainerWinRate: number
  synergyScore: number
  jockeyLabel: string
  trainerLabel: string
}

export interface CourseDistanceSubIndices {
  weightEffect: number
  classEstimate: string
  goingAdaptability: number
  goingLabel: string
}

export interface BenterBreakdown {
  formScore: number
  drawScore: number
  jockeyTrainerScore: number
  weightScore: number
  courseDistanceScore: number
  restDaysScore: number
  gearScore: number
  paceScore: number
  classMovScore: number
  totalScore: number
  pFinal: number | null
  summary: string
  formSub: FormSubIndices
  drawSub: DrawSubIndices
  jtSub: JockeyTrainerSubIndices
  cdSub: CourseDistanceSubIndices
  weights: RacecourseWeights
  venue: string
  venueLabel: string
}

export function computeBenterBreakdown(row: RaceRow, venue?: string): BenterBreakdown {
  const w = getWeightsByVenue(venue)
  const form = parseFormHistory(row.form_history)
  const draw = row.draw
  const jockeyWr = row.jockey_win_rate ?? 0.1
  const trainerWr = row.trainer_win_rate ?? 0.1
  const weight = row.actual_weight
  const pFinal = row.prediction?.final_prob

  const formAvg = form.length > 0 ? form.reduce((s, p) => s + p, 0) / form.length : 10
  const formScore = Math.max(0, Math.min(100, Math.round((1 - (formAvg - 1) / 13) * 100)))

  const drawMax = 14
  const drawScore = draw != null
    ? Math.max(0, Math.min(100, Math.round((1 - (draw - 1) / drawMax) * 100)))
    : 50

  const jockeyScore = Math.max(0, Math.min(100, Math.round(jockeyWr * 500)))
  const trainerScore = Math.max(0, Math.min(100, Math.round(trainerWr * 500)))
  const jockeyTrainerScore = Math.round(jockeyScore * 0.6 + trainerScore * 0.4)

  let weightScore = 60
  if (weight != null) {
    if (weight <= 118) weightScore += 20
    else if (weight <= 124) weightScore += 10
    else if (weight >= 132) weightScore -= 15
    else if (weight >= 128) weightScore -= 5
  }
  weightScore = Math.max(0, Math.min(100, weightScore))

  const courseDistanceScore = 50
  const restDaysScore = computeRestDaysScore(row)
  const gearScore = computeGearScore(row)
  const paceScore = 50
  const classMovScore = 50

  const totalScore = Math.round(
    formScore * w.form +
    drawScore * w.draw +
    jockeyTrainerScore * w.jockeyTrainer +
    weightScore * w.weight +
    courseDistanceScore * w.courseDistance +
    restDaysScore * w.restDays +
    gearScore * w.gear +
    paceScore * w.pace +
    classMovScore * w.classMov
  )

  const venueKey = venue === 'HV' ? 'HV' : 'ST'
  const venueLabel = venue === 'HV' ? '跑馬地' : '沙田'

  // --- Sub-indices ---

  // Form sub-indices
  const formTrend = analyzeFormTrend(form)
  const trendMap = { improving: '上升' as const, declining: '下滑' as const, consistent: '穩定' as const, mixed: '起伏' as const }
  const trendScoreVal = formTrend.trend === 'improving' ? 85 : formTrend.trend === 'consistent' ? 70 : formTrend.trend === 'mixed' ? 55 : 35
  const formSub: FormSubIndices = {
    avgFinish: form.length > 0 ? Math.round(formAvg * 10) / 10 : null,
    bestFinish: form.length > 0 ? Math.min(...form) : null,
    trendLabel: trendMap[formTrend.trend],
    trendScore: trendScoreVal,
    lastRacePos: form.length > 0 ? form[0] : null,
  }

  // Draw sub-indices
  const drawBiasCoeff = draw != null ? Math.round((1 - (draw - 1) / drawMax) * 100) / 100 : 0.5
  const totalRunnersEst = 12
  const innerRatio = draw != null ? (draw - 1) / Math.min(totalRunnersEst - 1, drawMax - 1) : 0.5
  const trackBiasIndex = draw != null ? Math.round((1 - innerRatio * 0.6) * 100) / 100 : 0.7
  const drawAdvantage: '內檔有利' | '中檔中性' | '外檔不利' =
    draw != null && draw <= 5 ? '內檔有利' : draw != null && draw >= 10 ? '外檔不利' : '中檔中性'
  const drawSub: DrawSubIndices = {
    drawBiasCoeff,
    trackBiasIndex,
    drawAdvantage,
  }

  // Jockey/Trainer sub-indices
  const synergyScore = Math.round((jockeyWr * 0.6 + trainerWr * 0.4) * 500)
  const jtSub: JockeyTrainerSubIndices = {
    jockeyWinRate: Math.round(jockeyWr * 1000) / 10,
    trainerWinRate: Math.round(trainerWr * 1000) / 10,
    synergyScore: Math.max(0, Math.min(100, synergyScore)),
    jockeyLabel: row.jockey ?? '-',
    trainerLabel: row.trainer ?? '-',
  }

  // Course/Distance sub-indices
  let weightEffect = 0
  if (weight != null) {
    if (weight <= 118) weightEffect = 20
    else if (weight <= 124) weightEffect = 10
    else if (weight <= 128) weightEffect = 0
    else if (weight <= 132) weightEffect = -10
    else weightEffect = -20
  }
  const goingAdaptability = 70
  const goingLabel = '好地 (標準)'
  const classEstimate = weight != null
    ? weight >= 130 ? '高班' : weight >= 122 ? '中班' : '低班'
    : '未知'
  const cdSub: CourseDistanceSubIndices = {
    weightEffect,
    classEstimate,
    goingAdaptability,
    goingLabel,
  }

  const summary = generateBenterSummary(row, formScore, drawScore, jockeyTrainerScore, courseDistanceScore, totalScore)

  return {
    formScore,
    drawScore,
    jockeyTrainerScore,
    weightScore,
    courseDistanceScore,
    restDaysScore,
    gearScore,
    paceScore,
    classMovScore,
    totalScore,
    pFinal: pFinal ?? null,
    summary,
    formSub,
    drawSub,
    jtSub,
    cdSub,
    weights: w,
    venue: venueKey,
    venueLabel,
  }
}

function generateBenterSummary(
  row: RaceRow,
  formScore: number,
  drawScore: number,
  jockeyTrainerScore: number,
  courseDistanceScore: number,
  totalScore: number
): string {
  const parts: string[] = []
  const name = row.horse_name

  const strengths: string[] = []
  const weaknesses: string[] = []

  if (formScore >= 75) strengths.push('近況走勢強勁')
  else if (formScore < 50) weaknesses.push('近績稍遜')

  if (drawScore >= 75) strengths.push('檔位優越')
  else if (drawScore < 40) weaknesses.push('外檔不利')

  if (jockeyTrainerScore >= 75) strengths.push('騎練組合出色')
  else if (jockeyTrainerScore < 50) weaknesses.push('騎練配合一般')

  if (courseDistanceScore >= 75) strengths.push('途程負磅配合得宜')
  else if (courseDistanceScore < 50) weaknesses.push('負磅偏重')

  if (strengths.length > 0) {
    parts.push(`${name}${strengths.join('、')}`)
  }

  if (weaknesses.length > 0) {
    parts.push(`唯${weaknesses.join('、')}`)
  }

  if (totalScore >= 75) {
    parts.push('綜合評分極高，為首選之馬')
  } else if (totalScore >= 60) {
    parts.push('綜合評分不俗，可作膽材考量')
  } else if (totalScore >= 45) {
    parts.push('綜合評分中等，適合作冷門配腳')
  } else {
    parts.push('綜合評分偏低，建議觀望')
  }

  return parts.join('，') + '。'
}
