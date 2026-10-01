import type { RaceRow } from './types'

const BANKROLL = 1000
const UNIT = 10
const CORRECTION = 1.05

export interface OverlayHorse {
  row: RaceRow
  ratio: number
  label: string
}

export interface UnderlayHorse {
  row: RaceRow
  ratio: number
}

export interface WinBet {
  row: RaceRow
  ev: number
  kelly: number
  units: number
  betType: 'WIN' | 'PLACE'
}

export interface QLeg {
  row: RaceRow
  pPair: number
}

export interface QCombination {
  anchor: RaceRow
  legs: QLeg[]
  totalCost: number
  anchorEV: number
}

export interface DarkHorse {
  row: RaceRow
  modelRank: number
  marketRank: number
  ev: number
  odds: number
}

export interface TrioCombination {
  horses: RaceRow[]
  pTrio: number
  estimatedOdds: number
}

export interface QuartetCombination {
  horses: RaceRow[]
  pQuartet: number
  estimatedOdds: number
}

export interface BettingEngineResult {
  overlays: OverlayHorse[]
  underlays: UnderlayHorse[]
  winBets: WinBet[]
  winPoolValue: boolean
  qCombos: QCombination[]
  darkHorses: DarkHorse[]
  trio: TrioCombination | null
  quartet: QuartetCombination | null
  totalRecommendedBet: number
}

function getPModel(row: RaceRow): number {
  return row.prediction?.raw_model_prob ?? 0
}

function getPMarket(row: RaceRow): number {
  return row.prediction?.market_implied_prob ?? 0
}

function getPFinal(row: RaceRow): number {
  return row.prediction?.final_prob ?? 0
}

function getEV(row: RaceRow): number {
  return row.prediction?.expected_value ?? 0
}

function getKelly(row: RaceRow): number {
  return row.prediction?.kelly_fraction ?? 0
}

export function identifyOverlays(rows: RaceRow[]): OverlayHorse[] {
  return rows
    .map(row => {
      const pModel = getPModel(row)
      const pMarket = getPMarket(row)
      if (pMarket <= 0 || pModel < 0.07) return null
      const ratio = pModel / pMarket
      if (ratio < 1.3) return null
      return {
        row,
        ratio,
        label: `模型評分高於市場 ${(ratio * 100 - 100).toFixed(0)}%`,
      }
    })
    .filter((x): x is OverlayHorse => x !== null)
    .sort((a, b) => b.ratio - a.ratio)
}

export function identifyUnderlays(rows: RaceRow[]): UnderlayHorse[] {
  return rows
    .map(row => {
      const pModel = getPModel(row)
      const pMarket = getPMarket(row)
      if (pModel <= 0) return null
      const ratio = pMarket / pModel
      if (ratio < 1.5) return null
      return { row, ratio }
    })
    .filter((x): x is UnderlayHorse => x !== null)
    .sort((a, b) => b.ratio - a.ratio)
}

export function getWinRecommendations(rows: RaceRow[]): { bets: WinBet[]; hasValue: boolean } {
  const candidates = rows
    .filter(r => {
      const ev = getEV(r)
      const kelly = getKelly(r)
      return ev > 0.05 && kelly > 0
    })
    .map((row): WinBet => {
      const ev = getEV(row)
      const kelly = getKelly(row)
      const units = Math.max(1, Math.round(kelly * BANKROLL / UNIT))
      const betType: 'WIN' | 'PLACE' = ev > 0.10 ? 'WIN' : 'PLACE'
      return { row, ev, kelly, units, betType }
    })
    .sort((a, b) => b.ev - a.ev)

  return {
    bets: candidates.slice(0, 3),
    hasValue: candidates.length > 0,
  }
}

export function getQCombinations(rows: RaceRow[]): QCombination[] {
  const overlays = identifyOverlays(rows)
  const underlays = identifyUnderlays(rows)
  const underlayIds = new Set(underlays.map(u => u.row.runner_id))

  const sorted = [...rows]
    .filter(r => getPFinal(r) > 0)
    .sort((a, b) => getPFinal(b) - getPFinal(a))

  if (sorted.length < 2) return []

  const positiveEV = sorted.filter(r => getEV(r) > 0 && !underlayIds.has(r.runner_id))
  const candidates = positiveEV.length > 0
    ? [...positiveEV].sort((a, b) => getPModel(b) - getPModel(a))
    : sorted.filter(r => !underlayIds.has(r.runner_id))

  const anchor = candidates[0] ?? sorted[0]
  const overlayIds = new Set(overlays.map(o => o.row.runner_id))

  const coldLegs = sorted
    .slice(1)
    .filter(r => overlayIds.has(r.runner_id))
    .slice(0, 3)

  const fallbackLegs = sorted.slice(1, 4)
  const legs = coldLegs.length >= 2 ? coldLegs : fallbackLegs

  const anchorPFinal = getPFinal(anchor)

  const qLegs: QLeg[] = legs.map(leg => {
    const legPFinal = getPFinal(leg)
    const pPair = anchorPFinal * legPFinal * CORRECTION
    return { row: leg, pPair }
  })

  const totalCost = qLegs.length * UNIT

  return [{
    anchor,
    legs: qLegs,
    totalCost,
    anchorEV: getEV(anchor),
  }]
}

export function identifyDarkHorses(rows: RaceRow[]): DarkHorse[] {
  const modelSorted = [...rows].sort((a, b) => getPModel(b) - getPModel(a))
  const marketSorted = [...rows].sort((a, b) => getPMarket(b) - getPMarket(a))

  return rows
    .map(row => {
      const modelRank = modelSorted.indexOf(row) + 1
      const marketRank = marketSorted.indexOf(row) + 1
      const ev = getEV(row)
      const odds = row.win_odds ?? 0
      return { row, modelRank, marketRank, ev, odds }
    })
    .filter(d => d.modelRank <= 5 && d.marketRank > 5 && d.odds > 15 && d.ev > 0.03)
    .sort((a, b) => b.ev - a.ev)
    .slice(0, 3)
}

export function getTrioCombination(rows: RaceRow[]): TrioCombination | null {
  const sorted = [...rows]
    .filter(r => getPFinal(r) > 0)
    .sort((a, b) => getPFinal(b) - getPFinal(a))

  if (sorted.length < 3) return null

  const top3 = sorted.slice(0, 3)
  const pTrio = top3.reduce((p, r) => p * getPFinal(r), 1) * 1.1
  const avgOdds = top3.reduce((s, r) => s + (r.win_odds ?? 10), 0) / 3
  const estimatedOdds = avgOdds * avgOdds * 0.3

  return { horses: top3, pTrio, estimatedOdds }
}

export function getQuartetCombination(rows: RaceRow[]): QuartetCombination | null {
  const sorted = [...rows]
    .filter(r => getPFinal(r) > 0)
    .sort((a, b) => getPFinal(b) - getPFinal(a))

  if (sorted.length < 4) return null

  const top4 = sorted.slice(0, 4)
  const pQuartet = top4.reduce((p, r) => p * getPFinal(r), 1) * 1.15
  const avgOdds = top4.reduce((s, r) => s + (r.win_odds ?? 10), 0) / 4
  const estimatedOdds = avgOdds * avgOdds * avgOdds * 0.15

  return { horses: top4, pQuartet, estimatedOdds }
}

export function runBettingEngine(rows: RaceRow[]): BettingEngineResult {
  const overlays = identifyOverlays(rows)
  const underlays = identifyUnderlays(rows)
  const { bets: winBets, hasValue: winPoolValue } = getWinRecommendations(rows)
  const qCombos = getQCombinations(rows)
  const darkHorses = identifyDarkHorses(rows)
  const trio = getTrioCombination(rows)
  const quartet = getQuartetCombination(rows)

  const totalBet = winBets.reduce((s, b) => s + b.units * UNIT, 0) +
    qCombos.reduce((s, q) => s + q.totalCost, 0) +
    (trio ? UNIT : 0) +
    (quartet ? UNIT * 4 : 0)

  return {
    overlays,
    underlays,
    winBets,
    winPoolValue,
    qCombos,
    darkHorses,
    trio,
    quartet,
    totalRecommendedBet: totalBet,
  }
}
