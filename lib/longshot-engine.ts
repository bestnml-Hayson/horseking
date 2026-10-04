import type { RaceRow } from './types'

export interface LongshotPick {
  row: RaceRow
  pModel: number
  pMarket: number
  pFinal: number
  ev: number
  odds: number
  overlayScore: number
}

export interface LongshotResult {
  longshots: LongshotPick[]
  hotColdCombos: { anchor: LongshotPick; longshots: LongshotPick[] }[]
}

const LONGSHOT_ODDS_THRESHOLD = 12.0

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

function computeOverlayScore(row: RaceRow): number {
  const pModel = getPModel(row)
  const pMarket = getPMarket(row)
  const ev = getEV(row)
  const odds = row.win_odds ?? 99

  if (odds < LONGSHOT_ODDS_THRESHOLD) return -1

  const modelEdge = pModel - pMarket
  return modelEdge * 100 + Math.max(0, ev) * 50
}

export function findLongshots(rows: RaceRow[], maxPick: number = 3): LongshotPick[] {
  return rows
    .filter(r => {
      const odds = r.win_odds ?? 99
      return odds >= LONGSHOT_ODDS_THRESHOLD && getPFinal(r) > 0
    })
    .map(row => ({
      row,
      pModel: getPModel(row),
      pMarket: getPMarket(row),
      pFinal: getPFinal(row),
      ev: getEV(row),
      odds: row.win_odds ?? 0,
      overlayScore: computeOverlayScore(row),
    }))
    .filter(p => p.overlayScore > 0)
    .sort((a, b) => b.overlayScore - a.overlayScore)
    .slice(0, maxPick)
}

export function generateLongshotStrategy(rows: RaceRow[]): LongshotResult | null {
  const longshots = findLongshots(rows, 3)
  if (longshots.length === 0) return null

  const topByPFinal = [...rows]
    .filter(r => getPFinal(r) > 0)
    .sort((a, b) => getPFinal(b) - getPFinal(a))
    .slice(0, 2)
    .map(row => ({
      row,
      pModel: getPModel(row),
      pMarket: getPMarket(row),
      pFinal: getPFinal(row),
      ev: getEV(row),
      odds: row.win_odds ?? 0,
      overlayScore: computeOverlayScore(row),
    }))

  const hotColdCombos = topByPFinal
    .filter(anchor => anchor.overlayScore <= 0 || (anchor.row.win_odds ?? 99) < LONGSHOT_ODDS_THRESHOLD)
    .slice(0, 1)
    .map(anchor => ({
      anchor,
      longshots: longshots.slice(0, 2),
    }))

  return { longshots, hotColdCombos }
}
