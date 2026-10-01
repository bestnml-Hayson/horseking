import type { RaceRow, Race } from './types'

export interface TreblePick {
  row: RaceRow
  pFinal: number
  ev: number
  odds: number
}

export interface TrebleRace {
  race: Race
  picks: TreblePick[]
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
  racePicks: TrebleRace[]
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

function combinationsOf3<T>(arr: T[]): [T, T, T][] {
  const result: [T, T, T][] = []
  for (let i = 0; i < arr.length; i++) {
    for (let j = i + 1; j < arr.length; j++) {
      for (let k = j + 1; k < arr.length; k++) {
        result.push([arr[i], arr[j], arr[k]])
      }
    }
  }
  return result
}

export function generateTreble(
  allRaceData: Map<string, RaceRow[]>,
  races: Race[]
): TrebleResult {
  const racePicks: TrebleRace[] = []

  for (const race of races) {
    const rows = allRaceData.get(race.race_id)
    if (!rows || rows.length < 2) continue
    const picks = getTopPicksForRace(rows, 3)
    if (picks.length > 0) {
      racePicks.push({ race, picks })
    }
  }

  const bestRaces = [...racePicks]
    .sort((a, b) => scoreCandidate(b.picks[0].row) - scoreCandidate(a.picks[0].row))
    .slice(0, 6)

  const raceCombos = combinationsOf3(bestRaces)

  const combinations: TrebleCombination[] = []
  for (const [r1, r2, r3] of raceCombos) {
    for (const p1 of r1.picks) {
      for (const p2 of r2.picks) {
        for (const p3 of r3.picks) {
          const pComposite = p1.pFinal * p2.pFinal * p3.pFinal
          const estimatedOdds = Math.max(1, 1 / pComposite)
          combinations.push({
            legs: [
              { raceNo: r1.race.race_no, row: p1.row, pFinal: p1.pFinal, ev: p1.ev, odds: p1.odds },
              { raceNo: r2.race.race_no, row: p2.row, pFinal: p2.pFinal, ev: p2.ev, odds: p2.odds },
              { raceNo: r3.race.race_no, row: p3.row, pFinal: p3.pFinal, ev: p3.ev, odds: p3.odds },
            ],
            pComposite,
            estimatedOdds,
          })
        }
      }
    }
  }

  combinations.sort((a, b) => b.pComposite - a.pComposite)

  return {
    racePicks,
    combinations: combinations.slice(0, 8),
  }
}
