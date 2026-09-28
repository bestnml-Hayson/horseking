import type { RaceRow, Race } from './types'

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
 * Sort rows by AI score descending.
 */
export function sortByAIScore(rows: RaceRow[]): RaceRow[] {
  return [...rows].sort((a, b) => computeAIScore(b) - computeAIScore(a))
}

/**
 * Get top N picks.
 */
export function getTopPicks(rows: RaceRow[], n: number = 4): RaceRow[] {
  return sortByAIScore(rows).slice(0, n)
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
  if (!odds || odds <= 0) return '-'
  return odds.toFixed(1) + 'x'
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
 * Get form position color.
 */
export function getFormColor(pos: number): string {
  if (pos <= 3) return '#10b981'
  if (pos <= 6) return '#f59e0b'
  return '#ef4444'
}

/**
 * Parse form_history string (e.g. "12-8-9-9-11-5") into number array.
 */
export function parseFormHistory(form: string | null | undefined): number[] {
  if (!form) return []
  return form
    .split(/[-\/\s,]+/)
    .map(s => parseInt(s.trim()))
    .filter(n => !isNaN(n) && n > 0)
    .slice(0, 6)
}
