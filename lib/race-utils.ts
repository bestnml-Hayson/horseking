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

/**
 * Estimate race start time based on venue and race number.
 * Shatin: first race 13:00 (day) / 19:15 (night), ~35 min apart
 * Happy Valley: first race 19:15, ~30 min apart
 */
export function estimateRaceTime(venue: string | undefined, raceNo: number, raceDate?: string | null): string {
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

  // Model logic explanation
  const top1 = topPicks[0]
  const top2 = topPicks[1]
  const logicParts: string[] = []

  if (top1) {
    const p1 = top1.prediction?.final_prob ?? 0
    const ev1 = top1.prediction?.expected_value ?? 0
    logicParts.push(
      `首選「${top1.horse_name}」融合勝率 ${(p1 * 100).toFixed(1)}%` +
      (ev1 > 0 ? `，EV +${(ev1 * 100).toFixed(1)}% 具價值` : '')
    )
  }
  if (top2) {
    const p2 = top2.prediction?.final_prob ?? 0
    logicParts.push(`次選「${top2.horse_name}」勝率 ${(p2 * 100).toFixed(1)}%`)
  }

  const modelLogic = logicParts.length > 0
    ? `Benter 模型以 25% .self評 + 75% 市場賠率融合計算。${logicParts.join('；')}。`
    : 'Benter 模型以 25% .self評分 + 75% 市場賠率融合計算，輸出各馬勝率及期望值。'

  return {
    paceLabel: pace.label,
    paceDetail: pace.detail,
    keyFactors,
    modelLogic,
  }
}
