import type { RaceRow } from './types'

export const DEFAULT_BANKROLL = 10000
const CORRECTION = 1.05

const WIN_EV_THRESHOLD = 0.10
const WIN_PFINAL_THRESHOLD = 0.05
const LONGSHOT_ODDS_THRESHOLD = 20.0
const LONGSHOT_PFINAL_CAP = 0.03

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
  amount: number
  betType: 'WIN' | 'PLACE'
  kellyPct: number
}

export interface QLeg {
  row: RaceRow
  pPair: number
  role: 'anchor' | 'leg'
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

export interface TieredAllocation {
  core: { bets: WinBet[]; qCombos: QCombination[]; amount: number }
  value: { qCombos: QCombination[]; amount: number }
  longshot: { darkHorses: DarkHorse[]; trio: TrioCombination | null; quartet: QuartetCombination | null; amount: number }
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
  bankroll: number
  totalPct: number
  expectedEV: number
  allocation: TieredAllocation
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

function isUnderlay(row: RaceRow, underlayIds: Set<string>): boolean {
  return underlayIds.has(row.runner_id)
}

function isLongshot(row: RaceRow): boolean {
  const odds = row.win_odds ?? 0
  const pFinal = getPFinal(row)
  return odds > LONGSHOT_ODDS_THRESHOLD && pFinal < LONGSHOT_PFINAL_CAP
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

export function getWinRecommendations(rows: RaceRow[], bankroll: number): { bets: WinBet[]; hasValue: boolean } {
  const underlays = identifyUnderlays(rows)
  const underlayIds = new Set(underlays.map(u => u.row.runner_id))

  const candidates = rows
    .filter(r => {
      const ev = getEV(r)
      const kelly = getKelly(r)
      const pFinal = getPFinal(r)
      if (ev <= 0 || kelly <= 0) return false
      if (isUnderlay(r, underlayIds)) return false
      if (isLongshot(r)) return false
      return true
    })
    .map((row): WinBet | null => {
      const ev = getEV(row)
      const kelly = getKelly(row)
      const pFinal = getPFinal(row)

      if (ev > WIN_EV_THRESHOLD && pFinal >= WIN_PFINAL_THRESHOLD) {
        const amount = Math.round(kelly * bankroll)
        const kellyPct = (kelly * 100)
        return { row, ev, kelly, amount, betType: 'WIN', kellyPct }
      }

      if (pFinal >= WIN_PFINAL_THRESHOLD * 0.6) {
        const placeKelly = kelly * 0.5
        const amount = Math.max(10, Math.round(placeKelly * bankroll))
        const kellyPct = (placeKelly * 100)
        return { row, ev, kelly: placeKelly, amount, betType: 'PLACE', kellyPct }
      }

      return null
    })
    .filter((x): x is WinBet => x !== null)
    .sort((a, b) => b.ev - a.ev)

  return {
    bets: candidates.slice(0, 4),
    hasValue: candidates.length > 0,
  }
}

export function getQCombinations(rows: RaceRow[], bankroll: number): QCombination[] {
  const underlays = identifyUnderlays(rows)
  const underlayIds = new Set(underlays.map(u => u.row.runner_id))
  const overlays = identifyOverlays(rows)
  const overlayIds = new Set(overlays.map(o => o.row.runner_id))

  const sorted = [...rows]
    .filter(r => getPFinal(r) > 0 && !isUnderlay(r, underlayIds))
    .sort((a, b) => getPFinal(b) - getPFinal(a))

  if (sorted.length < 2) return []

  const top2 = sorted.slice(0, 2)
  const valueLegs = sorted
    .filter(r => getEV(r) > 0 && !top2.includes(r))
    .slice(0, 3)

  const combos: QCombination[] = []

  for (const anchor of top2) {
    const legs: QLeg[] = []

    for (const leg of valueLegs) {
      const legPFinal = getPFinal(leg)
      const pPair = getPFinal(anchor) * legPFinal * CORRECTION
      legs.push({ row: leg, pPair, role: 'leg' })
    }

    if (legs.length === 0) {
      const fallback = sorted.filter(r => r.runner_id !== anchor.runner_id).slice(0, 2)
      for (const leg of fallback) {
        const legPFinal = getPFinal(leg)
        const pPair = getPFinal(anchor) * legPFinal * CORRECTION
        legs.push({ row: leg, pPair, role: 'leg' })
      }
    }

    const costPerLeg = Math.max(10, Math.round(0.005 * bankroll / Math.max(1, legs.length)))
    const totalCost = legs.length * costPerLeg

    combos.push({
      anchor,
      legs,
      totalCost,
      anchorEV: getEV(anchor),
    })
  }

  return combos
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

export function runBettingEngine(rows: RaceRow[], bankroll: number = DEFAULT_BANKROLL): BettingEngineResult {
  const overlays = identifyOverlays(rows)
  const underlays = identifyUnderlays(rows)
  const { bets: winBets, hasValue: winPoolValue } = getWinRecommendations(rows, bankroll)
  const qCombos = getQCombinations(rows, bankroll)
  const darkHorses = identifyDarkHorses(rows)
  const trio = getTrioCombination(rows)
  const quartet = getQuartetCombination(rows)

  const coreAmount = Math.round(bankroll * 0.60)
  const valueAmount = Math.round(bankroll * 0.30)
  const longshotAmount = Math.round(bankroll * 0.10)

  const coreBets = winBets.filter(b => b.betType === 'WIN').slice(0, 2)
  const coreQ = qCombos.slice(0, 1)
  const coreActual = coreBets.reduce((s, b) => s + b.amount, 0) + coreQ.reduce((s, q) => s + q.totalCost, 0)

  const valueBets = winBets.filter(b => b.betType === 'PLACE')
  const valueQ = qCombos.slice(1)
  const valueActual = valueBets.reduce((s, b) => s + b.amount, 0) + valueQ.reduce((s, q) => s + q.totalCost, 0)

  const longshotActual = (trio ? 10 : 0) + (quartet ? 40 : 0) + darkHorses.length * 10

  const totalBet = coreActual + valueActual + longshotActual
  const totalPct = bankroll > 0 ? (totalBet / bankroll) * 100 : 0

  const allBetsEV = [
    ...winBets.map(b => b.row),
    ...qCombos.flatMap(q => [q.anchor, ...q.legs.map(l => l.row)]),
  ]
    .map(r => getEV(r))
    .filter(ev => ev > 0)
  const expectedEV = allBetsEV.length > 0
    ? allBetsEV.reduce((s, ev) => s + ev, 0) / allBetsEV.length
    : 0

  const allocation: TieredAllocation = {
    core: { bets: coreBets, qCombos: coreQ, amount: Math.min(coreActual, coreAmount) },
    value: { qCombos: valueQ, amount: Math.min(valueActual, valueAmount) },
    longshot: { darkHorses, trio, quartet, amount: Math.min(longshotActual, longshotAmount) },
  }

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
    bankroll,
    totalPct,
    expectedEV,
    allocation,
  }
}
