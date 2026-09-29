import type { RaceRow, Race, ModelPrediction } from './types'
import { getFormColor } from './color-utils'

export { getFormColor }

const ALPHA = 0.25
const FRACTIONAL_KELLY = 0.25
const W_FORM = 0.30
const W_RATING = 0.20
const W_JOCKEY = 0.20
const W_TRAINER = 0.15
const W_DRAW = 0.15

function normalize(arr: (number | null | undefined)[]): number[] {
  const vals = arr.filter((v): v is number => v != null)
  if (vals.length === 0) return arr.map(() => 0.5)
  const mn = Math.min(...vals)
  const mx = Math.max(...vals)
  const rng = mx !== mn ? mx - mn : 1
  return arr.map(v => v != null ? (v - mn) / rng : 0.5)
}

function softmax(scores: number[]): number[] {
  if (scores.length === 0) return []
  const maxS = Math.max(...scores)
  const exps = scores.map(s => Math.exp(s - maxS))
  const total = exps.reduce((a, b) => a + b, 0)
  return total === 0 ? scores.map(() => 1 / scores.length) : exps.map(e => e / total)
}

function parseFormForScore(form: string | null | undefined): number {
  if (!form) return 10
  const positions = form.split(/[-/\s,]+/).map(s => parseInt(s.trim())).filter(n => !isNaN(n) && n > 0)
  if (positions.length === 0) return 10
  return positions.slice(0, 6).reduce((s, p) => s + p, 0) / positions.length
}

export function computeClientPredictions(rows: RaceRow[]): RaceRow[] {
  if (rows.length === 0) return rows

  const formScores = rows.map(r => parseFormForScore(r.form_history))
  const ratings = rows.map(r => r.official_rating)
  const jockeyWrs = rows.map(r => r.jockey_win_rate)
  const trainerWrs = rows.map(r => r.trainer_win_rate)
  const draws = rows.map(r => r.draw)

  const nForm = normalize(formScores.map(f => 1 / f))
  const nRating = normalize(ratings)
  const nJockey = normalize(jockeyWrs)
  const nTrainer = normalize(trainerWrs)

  const nDraws = draws.map(d => {
    if (d == null) return 0.5
    const mid = (rows.length + 1) / 2
    return Math.max(0, Math.min(1, 1 - Math.abs(d - mid) / mid))
  })

  const rawScores = rows.map((_, i) =>
    W_FORM * nForm[i] + W_RATING * nRating[i] + W_JOCKEY * nJockey[i] +
    W_TRAINER * nTrainer[i] + W_DRAW * nDraws[i]
  )
  const pModels = softmax(rawScores)

  const oddsList = rows.map(r => r.win_odds)
  const hasValidOdds = oddsList.some(o => o != null && o > 1)
  const pMarkets = hasValidOdds
    ? softmax(oddsList.map(o => (o != null && o > 1) ? 1 / o : 0))
    : rows.map(() => 1 / rows.length)

  return rows.map((row, i) => {
    const pModel = pModels[i]
    const pMarket = pMarkets[i]
    const eps = 1e-10
    const pFinal = Math.exp(ALPHA * Math.log(Math.max(pModel, eps)) + (1 - ALPHA) * Math.log(Math.max(pMarket, eps)))
    const odds = row.win_odds
    const ev = (odds != null && odds > 1) ? pFinal * odds - 1 : 0
    const fullKelly = (odds != null && odds > 1 && ev > 0) ? ev / (odds - 1) : 0
    const kelly = Math.max(0, fullKelly * FRACTIONAL_KELLY)

    const prediction: ModelPrediction = {
      prediction_id: `client-${row.runner_id}`,
      race_id: row.race_id,
      runner_id: row.runner_id,
      raw_model_prob: Math.round(pModel * 10000) / 10000,
      market_implied_prob: Math.round(pMarket * 10000) / 10000,
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

export function generateHorseInsight(
  row: RaceRow,
  rank: number,
  totalRunners: number,
  paceLabel?: string
): string {
  const parts: string[] = []
  const pred = row.prediction
  const pFinal = pred?.final_prob ?? null
  const ev = pred?.expected_value ?? null
  const kelly = pred?.kelly_fraction ?? null
  const draw = row.draw
  const weight = row.actual_weight
  const jockey = row.jockey
  const jockeyWr = row.jockey_win_rate
  const trainerWr = row.trainer_win_rate
  const odds = row.win_odds
  const form = parseFormHistory(row.form_history)
  const formTrend = analyzeFormTrend(form)

  if (rank === 1) {
    parts.push('Benter 模型計算奪魁機會最高')
  } else if (rank === 2) {
    parts.push('模型評估爭勝能力第二')
  } else if (rank === 3) {
    parts.push('模型評分第三選擇')
  } else if (rank <= 6) {
    parts.push('中規中矩')
  } else {
    parts.push('模型評分偏低')
  }

  if (draw != null) {
    if (draw <= 3) {
      parts.push(`排 ${draw} 檔好檔，內欄有利搶先`)
    } else if (draw <= 7) {
      parts.push(`排 ${draw} 檔中規中矩`)
    } else if (draw <= 10) {
      parts.push(`排 ${draw} 檔偏外，需多走路程`)
    } else {
      parts.push(`排 ${draw} 檔大外檔，形勢不利`)
    }
  }

  if (form.length >= 3) {
    if (formTrend.trend === 'improving') {
      parts.push('近績走勢回升，狀態上揚')
    } else if (formTrend.trend === 'declining') {
      parts.push('近期走勢下滑，狀態存疑')
    } else if (formTrend.trend === 'consistent' && formTrend.avg <= 5) {
      parts.push('近績穩定在前列，水準可靠')
    }
    if (form[0] <= 3) {
      parts.push('上場表現出色')
    }
  }

  if (jockeyWr != null && jockeyWr >= 0.15) {
    parts.push(`騎師 ${jockey ?? ''} 近績 ${(jockeyWr * 100).toFixed(0)}% 勝率，狀態正佳`)
  }

  if (weight != null) {
    if (weight <= 118) {
      parts.push('負磅輕巧，有減磅優勢')
    } else if (weight >= 132) {
      parts.push('頂磅出擊，負擔較重')
    }
  }

  if (ev != null && ev > 0.15 && kelly != null && kelly > 0) {
    parts.push('EV 正期望，具投注價值')
  } else if (odds != null && odds > 0 && pFinal != null) {
    const impliedProb = 1 / odds
    if (pFinal > impliedProb * 1.2) {
      parts.push('模型勝率高於市場預期')
    }
  }

  if (paceLabel) {
    if (paceLabel === '慢步速' && draw != null && draw <= 5) {
      parts.push('慢步速形勢下內檔可前領')
    } else if (paceLabel === '快步速' && formTrend.trend === 'improving') {
      parts.push('快步速有利後上馬發力')
    }
  }

  // Gear change insight
  const gear = row.gear
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
      parts.push(`初戴${gearDesc}，可能有新鮮感`)
    }
  }

  // Rest days insight
  const restDays = row.rest_days
  if (restDays != null && restDays > 0) {
    if (restDays >= 90) {
      parts.push(`久休${restDays}天復出，狀態待觀察`)
    } else if (restDays >= 60) {
      parts.push(`休養${restDays}天，充分休息`)
    } else if (restDays <= 14) {
      parts.push(`僅休息${restDays}天，頻密出賽`)
    }
  }

  if (parts.length > 3) {
    return parts.slice(0, 3).join('；') + '。'
  }
  return parts.join('；') + '。'
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
  courseDistanceScore: number
  totalScore: number
  pFinal: number | null
  summary: string
  formSub: FormSubIndices
  drawSub: DrawSubIndices
  jtSub: JockeyTrainerSubIndices
  cdSub: CourseDistanceSubIndices
}

export function computeBenterBreakdown(row: RaceRow): BenterBreakdown {
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

  let courseDistanceScore = 60
  if (weight != null) {
    if (weight <= 118) courseDistanceScore += 20
    else if (weight <= 124) courseDistanceScore += 10
    else if (weight >= 132) courseDistanceScore -= 15
    else if (weight >= 128) courseDistanceScore -= 5
  }
  courseDistanceScore = Math.max(0, Math.min(100, courseDistanceScore))

  const totalScore = Math.round(
    formScore * 0.30 +
    drawScore * 0.15 +
    jockeyTrainerScore * 0.35 +
    courseDistanceScore * 0.20
  )

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
    courseDistanceScore,
    totalScore,
    pFinal: pFinal ?? null,
    summary,
    formSub,
    drawSub,
    jtSub,
    cdSub,
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
