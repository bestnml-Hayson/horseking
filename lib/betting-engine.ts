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

export interface BettingEngineResult {
  overlays: OverlayHorse[]
  underlays: UnderlayHorse[]
  winBets: WinBet[]
  winPoolValue: boolean
  qCombos: QCombination[]
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

export function runBettingEngine(rows: RaceRow[]): BettingEngineResult {
  const overlays = identifyOverlays(rows)
  const underlays = identifyUnderlays(rows)
  const { bets: winBets, hasValue: winPoolValue } = getWinRecommendations(rows)
  const qCombos = getQCombinations(rows)

  const totalBet = winBets.reduce((s, b) => s + b.units * UNIT, 0) +
    qCombos.reduce((s, q) => s + q.totalCost, 0)

  return {
    overlays,
    underlays,
    winBets,
    winPoolValue,
    qCombos,
    totalRecommendedBet: totalBet,
  }
}
