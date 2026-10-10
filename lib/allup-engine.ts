import type { RaceRow, Race } from './types'

export interface AllUpLeg {
  raceNo: number
  raceId: string
  horses: { horseNo: number; horseName: string; pFinal: number; ev: number; odds: number; isFavorite: boolean }[]
  legType: 'win' | 'qp' | 'q'
  legProb: number
}

export interface AllUpStrategy {
  id: string
  name: string
  nameShort: string
  description: string
  betType: string
  legs: AllUpLeg[]
  compositeProb: number
  estimatedOdds: number
  kellyFraction: number
  suggestedStake: number
  riskLevel: 'low' | 'medium' | 'high'
}

export interface AllUpResult {
  strategies: AllUpStrategy[]
}

function pf(row: RaceRow): number {
  return row.prediction?.final_prob ?? 0
}

function ev(row: RaceRow): number {
  return row.prediction?.expected_value ?? -1
}

function pModel(row: RaceRow): number {
  return row.prediction?.raw_model_prob ?? 0
}

function pMarket(row: RaceRow): number {
  return row.prediction?.market_implied_prob ?? 0
}

function kelly(row: RaceRow): number {
  return row.prediction?.kelly_fraction ?? 0
}

function horseName(row: RaceRow): string {
  return row.horse_name || `#${row.horse_no}`
}

function toRow(r: RaceRow) {
  return {
    horseNo: r.horse_no,
    horseName: horseName(r),
    pFinal: pf(r),
    ev: ev(r),
    odds: r.win_odds ?? 0,
    isFavorite: false,
  }
}

function raceBestRows(rows: RaceRow[], n: number): RaceRow[] {
  return [...rows]
    .filter(r => pf(r) > 0)
    .sort((a, b) => pf(b) - pf(a))
    .slice(0, n)
}

function raceQpProb(rows: RaceRow[], topN: number): number {
  const top = raceBestRows(rows, topN)
  if (top.length < 2) return 0
  const probs = top.map(r => pf(r))
  const p1 = probs[0]
  const p2 = probs.length > 1 ? probs[1] : probs[0] * 0.5
  return p1 * p2 + p1 * (1 - p2) * 0.5 + (1 - p1) * p2 * 0.5
}

function raceStabilityScore(rows: RaceRow[]): number {
  const top3 = raceBestRows(rows, 3)
  if (top3.length < 2) return 0
  const p1 = pf(top3[0])
  const p2 = pf(top3[1])
  const favOdds = top3[0].win_odds ?? 99
  const stability = p1 * 0.5 + p2 * 0.3 + (favOdds <= 5 ? 0.2 : favOdds <= 10 ? 0.1 : 0)
  return stability
}

function strategy1_StableQP(allRaceData: Map<string, RaceRow[]>, races: Race[]): AllUpStrategy | null {
  const raceScores: { race: Race; rows: RaceRow[]; score: number }[] = []

  for (const race of races) {
    const rows = allRaceData.get(race.race_id)
    if (!rows || rows.length < 4) continue
    const score = raceStabilityScore(rows)
    if (score > 0) raceScores.push({ race, rows, score })
  }

  raceScores.sort((a, b) => b.score - a.score)
  const selected = raceScores.slice(0, 3)

  if (selected.length < 3) return null

  const legs: AllUpLeg[] = selected.map(({ race, rows }) => {
    const top2 = raceBestRows(rows, 2)
    const favNo = top2.length > 0 ? top2[0].horse_no : -1
    const horses = top2.map((r, i) => ({
      ...toRow(r),
      isFavorite: r.horse_no === favNo && i === 0,
    }))
    const legProb = raceQpProb(rows, 2)
    return {
      raceNo: race.race_no,
      raceId: race.race_id,
      horses,
      legType: 'qp' as const,
      legProb,
    }
  })

  const compositeProb = legs.reduce((acc, l) => acc * l.legProb, 1)
  const estimatedOdds = compositeProb > 0 ? 1 / compositeProb : 0
  const avgKelly = legs.reduce((acc, l) => {
    const bestHorse = l.horses[0]
    return acc + (bestHorse?.ev ?? 0 > 0 ? 0.003 : 0.001)
  }, 0) / legs.length

  return {
    id: 'stable-qp',
    name: '穩健型位置 Q 過關',
    nameShort: '穩健 QP',
    description: '挑選 P_final 最穩定嘅 3 場，每場選 Top 2 馬進行位置 Q 過關',
    betType: '位置 Q 3關3',
    legs,
    compositeProb,
    estimatedOdds,
    kellyFraction: Math.min(avgKelly, 0.01),
    suggestedStake: Math.min(avgKelly * 100, 1),
    riskLevel: 'low',
  }
}

function strategy2_HighEV(allRaceData: Map<string, RaceRow[]>, races: Race[]): AllUpStrategy | null {
  const raceEV: { race: Race; rows: RaceRow[]; bestEV: number; bestRow: RaceRow }[] = []

  for (const race of races) {
    const rows = allRaceData.get(race.race_id)
    if (!rows || rows.length < 4) continue

    const candidates = rows.filter(r => {
      const e = ev(r)
      const pm = pModel(r)
      const pmk = pMarket(r)
      return e > 0 && pm > pmk
    })

    if (candidates.length === 0) continue

    candidates.sort((a, b) => ev(b) - ev(a))
    raceEV.push({
      race,
      rows,
      bestEV: ev(candidates[0]),
      bestRow: candidates[0],
    })
  }

  raceEV.sort((a, b) => b.bestEV - a.bestEV)
  const selected = raceEV.slice(0, 3)

  if (selected.length < 2) return null

  const legs: AllUpLeg[] = selected.map(({ race, rows, bestRow }) => {
    const top2 = raceBestRows(rows, 2)
    const horses = top2.map(r => ({
      ...toRow(r),
      isFavorite: r.horse_no === bestRow.horse_no,
    }))
    const legProb = pf(bestRow)
    return {
      raceNo: race.race_no,
      raceId: race.race_id,
      horses,
      legType: 'win' as const,
      legProb,
    }
  })

  const compositeProb = legs.reduce((acc, l) => acc * l.legProb, 1)
  const estimatedOdds = legs.reduce((acc, l) => {
    const bestOdds = l.horses.find(h => h.isFavorite)?.odds ?? l.horses[0]?.odds ?? 1
    return acc * bestOdds
  }, 1)
  const avgKelly = legs.reduce((acc, l) => acc + (l.horses.find(h => h.isFavorite)?.ev ?? 0), 0) / legs.length

  return {
    id: 'high-ev',
    name: '高期望值混合過關',
    nameShort: '高EV過關',
    description: '挑選 EV 最高且 P_model > P_market 嘅 2-3 場，獨贏過關放大邊際優勢',
    betType: selected.length >= 3 ? '獨贏 3關1' : '獨贏 2關3',
    legs,
    compositeProb,
    estimatedOdds,
    kellyFraction: Math.min(Math.max(avgKelly, 0.002), 0.01),
    suggestedStake: Math.min(Math.max(avgKelly * 100, 0.2), 1),
    riskLevel: 'medium',
  }
}

function strategy3_Longshot(allRaceData: Map<string, RaceRow[]>, races: Race[]): AllUpStrategy | null {
  const raceLongshots: { race: Race; rows: RaceRow[]; fav: RaceRow; longshot: RaceRow; score: number }[] = []

  for (const race of races) {
    const rows = allRaceData.get(race.race_id)
    if (!rows || rows.length < 4) continue

    const sorted = [...rows].filter(r => pf(r) > 0).sort((a, b) => pf(b) - pf(a))
    if (sorted.length < 2) continue

    const fav = sorted[0]

    const longshots = sorted.filter(r =>
      (r.win_odds ?? 0) >= 12 && ev(r) > 0
    )

    if (longshots.length === 0) continue

    longshots.sort((a, b) => ev(b) - ev(a))
    const longshot = longshots[0]

    const score = ev(longshot) * (pf(fav) + 0.1)
    raceLongshots.push({ race, rows, fav, longshot, score })
  }

  raceLongshots.sort((a, b) => b.score - a.score)
  const selected = raceLongshots.slice(0, 2)

  if (selected.length < 2) return null

  const legs: AllUpLeg[] = selected.map(({ race, fav, longshot }) => {
    const horses = [
      { ...toRow(fav), isFavorite: true },
      { ...toRow(longshot), isFavorite: false },
    ]
    const favP = pf(fav)
    const lsP = pf(longshot)
    const legProb = favP * lsP + favP * (1 - lsP) * 0.3 + (1 - favP) * lsP * 0.3
    return {
      raceNo: race.race_no,
      raceId: race.race_id,
      horses,
      legType: 'q' as const,
      legProb,
    }
  })

  const compositeProb = legs.reduce((acc, l) => acc * l.legProb, 1)
  const oddsProduct = legs.reduce((acc, l) => {
    const favOdds = l.horses.find(h => h.isFavorite)?.odds ?? 1
    const lsOdds = l.horses.find(h => !h.isFavorite)?.odds ?? 1
    return acc * (favOdds + lsOdds) / 2
  }, 1)

  return {
    id: 'longshot-allup',
    name: '高彩金爆冷冷熱配過關',
    nameShort: '爆冷過關',
    description: '每場以熱門強馬 (膽) 搭超值冷門馬 (腳)，博取高額賠率乘積',
    betType: '連贏 Q 2關3',
    legs,
    compositeProb,
    estimatedOdds: oddsProduct,
    kellyFraction: 0.005,
    suggestedStake: 0.5,
    riskLevel: 'high',
  }
}

export function generateAllUp(
  allRaceData: Map<string, RaceRow[]>,
  races: Race[]
): AllUpResult | null {
  if (!allRaceData || allRaceData.size === 0 || races.length === 0) return null

  const strategies: AllUpStrategy[] = []

  const s1 = strategy1_StableQP(allRaceData, races)
  if (s1) strategies.push(s1)

  const s2 = strategy2_HighEV(allRaceData, races)
  if (s2) strategies.push(s2)

  const s3 = strategy3_Longshot(allRaceData, races)
  if (s3) strategies.push(s3)

  if (strategies.length === 0) return null

  return { strategies }
}
