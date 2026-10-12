import type { RaceRow, Race } from './types'

// ============================================================================
// Multi-Pool Value Maximizer Engine
// Calculates EV across all HKJC betting pools and recommends optimal strategies
// ============================================================================

export interface PoolEV {
  poolType: string
  poolName: string
  ev: number
  probability: number
  estimatedOdds: number
  recommended: boolean
  reason: string
}

export interface SingleRaceStrategy {
  poolType: string
  poolName: string
  horses: { horseNo: number; horseName: string; role: string }[]
  ev: number
  probability: number
  estimatedOdds: number
  cost: number
  recommendation: string
}

export interface AllUpLeg {
  raceNo: number
  horseNo: number
  horseName: string
  betType: 'WIN' | 'PLACE' | 'Q'
  pFinal: number
}

export interface AllUpStrategy {
  legs: AllUpLeg[]
  combinedProbability: number
  estimatedOdds: number
  ev: number
  cost: number
  recommendation: string
}

export interface MultiPoolResult {
  bestSingleStrategy: SingleRaceStrategy | null
  highRewardStrategy: SingleRaceStrategy | null
  bestAllUpStrategy: AllUpStrategy | null
  allPoolEVs: PoolEV[]
}

// Synergy multiplier for pair combinations (jockey-trainer-horse chemistry)
const PAIR_SYNERGY = 1.15

// Minimum EV threshold for recommendation
const MIN_EV_THRESHOLD = 0.10

// HKJC pool takeout rates (approximate)
const TAKEOUT_RATES = {
  WIN: 0.175,
  PLACE: 0.175,
  Q: 0.22,
  QP: 0.22,
  FORECAST: 0.22,
  TRIO: 0.22,
  SINGLE_T: 0.22,
  QUARTET: 0.22,
  TRIPLE_TRIO: 0.25,
}

// ============================================================================
// Single Race Pool Calculations
// ============================================================================

/**
 * Calculate WIN/PLACE pool EV
 */
function calculateWinPlaceEV(rows: RaceRow[]): PoolEV[] {
  const results: PoolEV[] = []

  for (const row of rows) {
    const pFinal = row.prediction?.final_prob ?? 0
    const odds = row.win_odds ?? 0

    if (odds <= 1) continue

    const ev = pFinal * odds - 1
    const recommended = ev > MIN_EV_THRESHOLD && pFinal > 0.05

    results.push({
      poolType: 'WIN',
      poolName: '獨贏',
      ev,
      probability: pFinal,
      estimatedOdds: odds,
      recommended,
      reason: recommended ? `EV +${(ev * 100).toFixed(1)}%，勝率 ${(pFinal * 100).toFixed(1)}%` : '',
    })

    // PLACE bet (approximately 1/3 of win odds for place)
    const placeOdds = Math.max(1.5, odds / 3)
    const placeEV = pFinal * placeOdds - 1
    results.push({
      poolType: 'PLACE',
      poolName: '位置',
      ev: placeEV,
      probability: Math.min(0.35, pFinal * 2.5),
      estimatedOdds: placeOdds,
      recommended: placeEV > MIN_EV_THRESHOLD,
      reason: placeEV > MIN_EV_THRESHOLD ? `位置 EV +${(placeEV * 100).toFixed(1)}%` : '',
    })
  }

  return results
}

/**
 * Calculate Q/QP (Quinella/Quinella Place) EV
 */
function calculateQEV(rows: RaceRow[]): PoolEV[] {
  const results: PoolEV[] = []
  const topHorses = rows
    .filter(r => (r.win_odds ?? 0) > 1)
    .sort((a, b) => (b.prediction?.final_prob ?? 0) - (a.prediction?.final_prob ?? 0))
    .slice(0, 6)

  // Calculate pair probabilities
  for (let i = 0; i < topHorses.length; i++) {
    for (let j = i + 1; j < topHorses.length; j++) {
      const horse1 = topHorses[i]
      const horse2 = topHorses[j]
      const p1 = horse1.prediction?.final_prob ?? 0
      const p2 = horse2.prediction?.final_prob ?? 0

      // Pair probability with synergy
      const pPair = p1 * p2 * PAIR_SYNERGY * 2 // *2 for either order

      // Estimate Q odds (simplified)
      const qOdds = 1 / (pPair * (1 - TAKEOUT_RATES.Q))

      const ev = pPair * qOdds - 1

      results.push({
        poolType: 'Q',
        poolName: '連贏',
        ev,
        probability: pPair,
        estimatedOdds: qOdds,
        recommended: ev > MIN_EV_THRESHOLD && pPair > 0.01,
        reason: ev > MIN_EV_THRESHOLD
          ? `#${horse1.horse_no}+#${horse2.horse_no} EV +${(ev * 100).toFixed(1)}%`
          : '',
      })
    }
  }

  return results
}

/**
 * Calculate Forecast (二重彩) EV
 */
function calculateForecastEV(rows: RaceRow[]): PoolEV[] {
  const results: PoolEV[] = []
  const topHorses = rows
    .filter(r => (r.win_odds ?? 0) > 1)
    .sort((a, b) => (b.prediction?.final_prob ?? 0) - (a.prediction?.final_prob ?? 0))
    .slice(0, 5)

  // Forecast requires exact order
  for (let i = 0; i < topHorses.length; i++) {
    for (let j = 0; j < topHorses.length; j++) {
      if (i === j) continue

      const horse1 = topHorses[i]
      const horse2 = topHorses[j]
      const p1 = horse1.prediction?.final_prob ?? 0
      const p2 = horse2.prediction?.final_prob ?? 0

      // Exact order probability
      const pForecast = p1 * p2 * PAIR_SYNERGY

      const forecastOdds = 1 / (pForecast * (1 - TAKEOUT_RATES.FORECAST))
      const ev = pForecast * forecastOdds - 1

      results.push({
        poolType: 'FORECAST',
        poolName: '二重彩',
        ev,
        probability: pForecast,
        estimatedOdds: forecastOdds,
        recommended: ev > MIN_EV_THRESHOLD * 1.5 && pForecast > 0.005,
        reason: ev > MIN_EV_THRESHOLD * 1.5
          ? `#${horse1.horse_no}→#${horse2.horse_no} EV +${(ev * 100).toFixed(1)}%`
          : '',
      })
    }
  }

  return results
}

/**
 * Calculate Trio (三重彩) EV
 */
function calculateTrioEV(rows: RaceRow[]): PoolEV[] {
  const results: PoolEV[] = []
  const topHorses = rows
    .filter(r => (r.win_odds ?? 0) > 1)
    .sort((a, b) => (b.prediction?.final_prob ?? 0) - (a.prediction?.final_prob ?? 0))
    .slice(0, 6)

  // Trio requires exact top 3 order
  for (let i = 0; i < topHorses.length; i++) {
    for (let j = 0; j < topHorses.length; j++) {
      if (j === i) continue
      for (let k = 0; k < topHorses.length; k++) {
        if (k === i || k === j) continue

        const h1 = topHorses[i]
        const h2 = topHorses[j]
        const h3 = topHorses[k]
        const p1 = h1.prediction?.final_prob ?? 0
        const p2 = h2.prediction?.final_prob ?? 0
        const p3 = h3.prediction?.final_prob ?? 0

        const pTrio = p1 * p2 * p3 * Math.pow(PAIR_SYNERGY, 2)
        const trioOdds = 1 / (pTrio * (1 - TAKEOUT_RATES.TRIO))
        const ev = pTrio * trioOdds - 1

        results.push({
          poolType: 'TRIO',
          poolName: '三重彩',
          ev,
          probability: pTrio,
          estimatedOdds: trioOdds,
          recommended: ev > MIN_EV_THRESHOLD * 2 && pTrio > 0.001,
          reason: ev > MIN_EV_THRESHOLD * 2
            ? `#${h1.horse_no}→#${h2.horse_no}→#${h3.horse_no}`
            : '',
        })
      }
    }
  }

  return results
}

/**
 * Calculate Single T (單T) EV - any order top 3
 */
function calculateSingleTEV(rows: RaceRow[]): PoolEV[] {
  const results: PoolEV[] = []
  const topHorses = rows
    .filter(r => (r.win_odds ?? 0) > 1)
    .sort((a, b) => (b.prediction?.final_prob ?? 0) - (a.prediction?.final_prob ?? 0))
    .slice(0, 6)

  // Single T: any order of top 3
  for (let i = 0; i < topHorses.length; i++) {
    for (let j = i + 1; j < topHorses.length; j++) {
      for (let k = j + 1; k < topHorses.length; k++) {
        const h1 = topHorses[i]
        const h2 = topHorses[j]
        const h3 = topHorses[k]
        const p1 = h1.prediction?.final_prob ?? 0
        const p2 = h2.prediction?.final_prob ?? 0
        const p3 = h3.prediction?.final_prob ?? 0

        // Any order: 6 permutations
        const pSingleT = p1 * p2 * p3 * 6 * Math.pow(PAIR_SYNERGY, 2)
        const singleTOdds = 1 / (pSingleT * (1 - TAKEOUT_RATES.SINGLE_T))
        const ev = pSingleT * singleTOdds - 1

        results.push({
          poolType: 'SINGLE_T',
          poolName: '單T',
          ev,
          probability: pSingleT,
          estimatedOdds: singleTOdds,
          recommended: ev > MIN_EV_THRESHOLD && pSingleT > 0.005,
          reason: ev > MIN_EV_THRESHOLD
            ? `#${h1.horse_no}+#${h2.horse_no}+#${h3.horse_no} (任意次序)`
            : '',
        })
      }
    }
  }

  return results
}

/**
 * Calculate Quartet (四連環) EV - any order top 4
 */
function calculateQuartetEV(rows: RaceRow[]): PoolEV[] {
  const results: PoolEV[] = []
  const topHorses = rows
    .filter(r => (r.win_odds ?? 0) > 1)
    .sort((a, b) => (b.prediction?.final_prob ?? 0) - (a.prediction?.final_prob ?? 0))
    .slice(0, 7)

  // Quartet: any order of top 4
  for (let i = 0; i < topHorses.length; i++) {
    for (let j = i + 1; j < topHorses.length; j++) {
      for (let k = j + 1; k < topHorses.length; k++) {
        for (let l = k + 1; l < topHorses.length; l++) {
          const h1 = topHorses[i]
          const h2 = topHorses[j]
          const h3 = topHorses[k]
          const h4 = topHorses[l]
          const p1 = h1.prediction?.final_prob ?? 0
          const p2 = h2.prediction?.final_prob ?? 0
          const p3 = h3.prediction?.final_prob ?? 0
          const p4 = h4.prediction?.final_prob ?? 0

          // Any order: 24 permutations
          const pQuartet = p1 * p2 * p3 * p4 * 24 * Math.pow(PAIR_SYNERGY, 3)
          const quartetOdds = 1 / (pQuartet * (1 - TAKEOUT_RATES.QUARTET))
          const ev = pQuartet * quartetOdds - 1

          results.push({
            poolType: 'QUARTET',
            poolName: '四連環',
            ev,
            probability: pQuartet,
            estimatedOdds: quartetOdds,
            recommended: ev > MIN_EV_THRESHOLD && pQuartet > 0.001,
            reason: ev > MIN_EV_THRESHOLD
              ? `#${h1.horse_no}+#${h2.horse_no}+#${h3.horse_no}+#${h4.horse_no}`
              : '',
          })
        }
      }
    }
  }

  return results
}

// ============================================================================
// Multi-Leg (All-Up) Calculations
// ============================================================================

/**
 * Calculate All-Up (過關) EV across multiple races
 */
export function calculateAllUpEV(
  raceData: Map<string, RaceRow[]>,
  races: Race[]
): AllUpStrategy | null {
  // Find races with good WIN EV opportunities
  const raceOpportunities: {
    race: Race
    rows: RaceRow[]
    bestEV: number
    bestHorse: RaceRow
    betType: 'WIN' | 'PLACE'
  }[] = []

  for (const race of races) {
    const rows = raceData.get(race.race_id) ?? []
    if (rows.length === 0) continue

    const validRows = rows.filter(r => (r.win_odds ?? 0) > 1)
    if (validRows.length === 0) continue

    // Find best EV horse in this race
    let bestEV = 0
    let bestHorse: RaceRow | null = null
    let bestBetType: 'WIN' | 'PLACE' = 'WIN'

    for (const row of validRows) {
      const pFinal = row.prediction?.final_prob ?? 0
      const odds = row.win_odds ?? 0
      const ev = pFinal * odds - 1

      if (ev > bestEV && pFinal > 0.08) {
        bestEV = ev
        bestHorse = row
        bestBetType = 'WIN'
      }

      // Check PLACE bet
      const placeOdds = Math.max(1.5, odds / 3)
      const placeEV = pFinal * placeOdds - 1
      if (placeEV > bestEV && pFinal > 0.12) {
        bestEV = placeEV
        bestHorse = row
        bestBetType = 'PLACE'
      }
    }

    if (bestHorse && bestEV > 0.05) {
      raceOpportunities.push({
        race,
        rows: validRows,
        bestEV,
        bestHorse,
        betType: bestBetType,
      })
    }
  }

  // Sort by EV and pick top 2-3 races for All-Up
  raceOpportunities.sort((a, b) => b.bestEV - a.bestEV)

  if (raceOpportunities.length < 2) return null

  // Build 2-leg or 3-leg All-Up
  const numLegs = Math.min(3, raceOpportunities.length)
  const selectedRaces = raceOpportunities.slice(0, numLegs)

  // Calculate combined probability and EV
  let combinedProb = 1
  let combinedOdds = 1

  const legs: AllUpLeg[] = selectedRaces.map(op => {
    const pFinal = op.bestHorse.prediction?.final_prob ?? 0
    const odds = op.bestHorse.win_odds ?? 0

    combinedProb *= op.betType === 'WIN' ? pFinal : Math.min(0.35, pFinal * 2.5)
    combinedOdds *= op.betType === 'WIN' ? odds : Math.max(1.5, odds / 3)

    return {
      raceNo: op.race.race_no,
      horseNo: op.bestHorse.horse_no,
      horseName: op.bestHorse.horse_name,
      betType: op.betType,
      pFinal,
    }
  })

  const allUpEV = combinedProb * combinedOdds - 1

  return {
    legs,
    combinedProbability: combinedProb,
    estimatedOdds: combinedOdds,
    ev: allUpEV,
    cost: numLegs === 2 ? 20 : 60,
    recommendation: `${numLegs}關${numLegs === 2 ? '1' : '3'}過關`,
  }
}

// ============================================================================
// Main Engine: Calculate All Pool EVs and Recommend Best Strategies
// ============================================================================

export function calculateMultiPoolEV(
  rows: RaceRow[],
  raceData: Map<string, RaceRow[]>,
  races: Race[],
  currentRace: Race
): MultiPoolResult {
  // Calculate all single-race pool EVs
  const winPlaceEVs = calculateWinPlaceEV(rows)
  const qEVs = calculateQEV(rows)
  const forecastEVs = calculateForecastEV(rows)
  const trioEVs = calculateTrioEV(rows)
  const singleTEVs = calculateSingleTEV(rows)
  const quartetEVs = calculateQuartetEV(rows)

  const allPoolEVs = [
    ...winPlaceEVs,
    ...qEVs,
    ...forecastEVs,
    ...trioEVs,
    ...singleTEVs,
    ...quartetEVs,
  ].filter(ev => ev.probability > 0)

  // Find best single-race strategy
  const recommendedPools = allPoolEVs.filter(ev => ev.recommended)
  recommendedPools.sort((a, b) => b.ev - a.ev)

  let bestSingleStrategy: SingleRaceStrategy | null = null
  let highRewardStrategy: SingleRaceStrategy | null = null

  if (recommendedPools.length > 0) {
    const best = recommendedPools[0]

    // Determine horses for this strategy
    let horses: { horseNo: number; horseName: string; role: string }[] = []

    if (best.poolType === 'WIN' || best.poolType === 'PLACE') {
      const horse = rows.find(r => {
        const pFinal = r.prediction?.final_prob ?? 0
        const odds = r.win_odds ?? 0
        return Math.abs(pFinal * odds - 1 - best.ev) < 0.01
      })
      if (horse) {
        horses = [{ horseNo: horse.horse_no, horseName: horse.horse_name, role: '膽' }]
      }
    } else if (best.poolType === 'Q') {
      // Extract horse numbers from reason
      const match = best.reason.match(/#(\d+)\+#(\d+)/)
      if (match) {
        const h1 = rows.find(r => r.horse_no === parseInt(match[1]))
        const h2 = rows.find(r => r.horse_no === parseInt(match[2]))
        if (h1 && h2) {
          horses = [
            { horseNo: h1.horse_no, horseName: h1.horse_name, role: '膽' },
            { horseNo: h2.horse_no, horseName: h2.horse_name, role: '腳' },
          ]
        }
      }
    } else if (best.poolType === 'SINGLE_T' || best.poolType === 'TRIO') {
      const match = best.reason.match(/#(\d+)[+#→]+#(\d+)[+#→]+#(\d+)/)
      if (match) {
        const h1 = rows.find(r => r.horse_no === parseInt(match[1]))
        const h2 = rows.find(r => r.horse_no === parseInt(match[2]))
        const h3 = rows.find(r => r.horse_no === parseInt(match[3]))
        if (h1 && h2 && h3) {
          horses = [
            { horseNo: h1.horse_no, horseName: h1.horse_name, role: '膽' },
            { horseNo: h2.horse_no, horseName: h2.horse_name, role: '配腳' },
            { horseNo: h3.horse_no, horseName: h3.horse_name, role: '配腳' },
          ]
        }
      }
    }

    bestSingleStrategy = {
      poolType: best.poolType,
      poolName: best.poolName,
      horses,
      ev: best.ev,
      probability: best.probability,
      estimatedOdds: best.estimatedOdds,
      cost: best.poolType === 'WIN' ? 10 : best.poolType === 'Q' ? 20 : 60,
      recommendation: best.reason,
    }

    // Find high-reward strategy (Trio or Quartet with highest odds)
    const highRewardPools = recommendedPools.filter(
      ev => ev.poolType === 'TRIO' || ev.poolType === 'QUARTET' || ev.poolType === 'FORECAST'
    )
    if (highRewardPools.length > 0) {
      const highReward = highRewardPools.sort((a, b) => b.estimatedOdds - a.estimatedOdds)[0]
      // Similar horse extraction logic...
      highRewardStrategy = {
        poolType: highReward.poolType,
        poolName: highReward.poolName,
        horses: [],
        ev: highReward.ev,
        probability: highReward.probability,
        estimatedOdds: highReward.estimatedOdds,
        cost: 60,
        recommendation: highReward.reason,
      }
    }
  }

  // Calculate All-Up strategy
  const bestAllUpStrategy = calculateAllUpEV(raceData, races)

  return {
    bestSingleStrategy,
    highRewardStrategy,
    bestAllUpStrategy,
    allPoolEVs,
  }
}
