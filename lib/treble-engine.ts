import type { RaceRow, Race } from './types'

export interface TreblePick {
  row: RaceRow
  pFinal: number
  ev: number
  odds: number
}

export interface TrebleLeg {
  raceNo: number
  row: RaceRow
  pFinal: number
  ev: number
  odds: number
}

export interface TrebleCombination {
  legs: TrebleLeg[]
  pComposite: number
  estimatedOdds: number
}

export interface TrebleResult {
  picks: { raceNo: number; picks: TreblePick[] }[]
  combinations: TrebleCombination[]
}

function getPFinal(row: RaceRow): number {
  return row.prediction?.final_prob ?? 0
}

function getEV(row: RaceRow): number {
  return row.prediction?.expected_value ?? 0
}

function scoreCandidate(row: RaceRow): number {
  const pFinal = getPFinal(row)
  const ev = getEV(row)
  return pFinal * (1 + Math.max(0, ev))
}

function getTopPicksForRace(rows: RaceRow[], n: number): TreblePick[] {
  return [...rows]
    .filter(r => getPFinal(r) > 0)
    .sort((a, b) => scoreCandidate(b) - scoreCandidate(a))
    .slice(0, n)
    .map(row => ({
      row,
      pFinal: getPFinal(row),
      ev: getEV(row),
      odds: row.win_odds ?? 0,
    }))
}

export function generateTreble(
  allRaceData: Map<string, RaceRow[]>,
  races: Race[]
): TrebleResult | null {
  const trebleRaces = [5, 6, 7]
    .map(no => races.find(r => r.race_no === no))
    .filter((r): r is Race => r != null)

  if (trebleRaces.length < 3) return null

  const picks = trebleRaces.map(race => {
    const rows = allRaceData.get(race.race_id)
    return {
      raceNo: race.race_no,
      picks: rows ? getTopPicksForRace(rows, 3) : [],
    }
  })

  if (picks.some(p => p.picks.length === 0)) return null

  const [r1, r2, r3] = picks
  const combinations: TrebleCombination[] = []

  for (const p1 of r1.picks) {
    for (const p2 of r2.picks) {
      for (const p3 of r3.picks) {
        const pComposite = p1.pFinal * p2.pFinal * p3.pFinal
        combinations.push({
          legs: [
            { raceNo: 5, row: p1.row, pFinal: p1.pFinal, ev: p1.ev, odds: p1.odds },
            { raceNo: 6, row: p2.row, pFinal: p2.pFinal, ev: p2.ev, odds: p2.odds },
            { raceNo: 7, row: p3.row, pFinal: p3.pFinal, ev: p3.ev, odds: p3.odds },
          ],
          pComposite,
          estimatedOdds: Math.max(1, 1 / pComposite),
        })
      }
    }
  }

  combinations.sort((a, b) => b.pComposite - a.pComposite)

  return { picks, combinations: combinations.slice(0, 5) }
}
