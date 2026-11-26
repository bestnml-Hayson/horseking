'use client'

import { useState, useMemo } from 'react'
import type { Race, RaceRow } from '@/lib/types'
import { runBettingEngine, DEFAULT_BANKROLL } from '@/lib/betting-engine'
import type { AllUpResult } from '@/lib/allup-engine'
import { fmtOdds, fmtEV, fmtKelly, isOddsPending, MODEL_WEIGHT, MARKET_WEIGHT } from '@/lib/race-utils'

const LONGSHOT_STAKE = 10
const SAFE_MIN_STAKE = 20
const LONGSHOT_ODDS_FLOOR = 12.0

type Kind = 'safe' | 'value' | 'longshot'

interface Pick {
  kind: Kind
  row: RaceRow | null
  stake: number | null
  stars: number
}

const KIND_LABEL: Record<Kind, string> = { safe: '穩選', value: '值博', longshot: '爆冷' }

interface BetRecommendationProps {
  rows: RaceRow[]
  race: Race | null
  raceTime?: string
  allUpData?: AllUpResult | null
  onHorseClick?: (horseId: string, horseName: string) => void
}

function pModel(r: RaceRow): number {
  return r.prediction?.raw_model_prob ?? 0
}
function pMarket(r: RaceRow): number {
  return r.prediction?.market_implied_prob ?? 0
}
function pFinal(r: RaceRow): number {
  return r.prediction?.final_prob ?? 0
}
function ev(r: RaceRow): number {
  return r.prediction?.expected_value ?? 0
}
function kelly(r: RaceRow): number {
  return r.prediction?.kelly_fraction ?? 0
}

function starsFor(pFinalValue: number): number {
  if (pFinalValue >= 0.2) return 3
  if (pFinalValue >= 0.13) return 2
  if (pFinalValue >= 0.07) return 1
  return 0
}

const LEG_TYPE: Record<'win' | 'qp' | 'q', string> = { win: '獨贏', qp: '單配', q: '連贏' }

const RISK_LABEL: Record<'low' | 'medium' | 'high', string> = { low: '低風險', medium: '中風險', high: '高風險' }

const RISK_STAKE_CAP: Record<'low' | 'medium' | 'high', number> = { low: 50, medium: 30, high: 20 }

function crossStake(compositeProb: number, riskLevel: 'low' | 'medium' | 'high'): number {
  const raw = Math.round((compositeProb * DEFAULT_BANKROLL * 0.25) / 10) * 10
  return Math.min(RISK_STAKE_CAP[riskLevel], Math.max(10, raw))
}

export function BetRecommendation({ rows, race, raceTime, allUpData, onHorseClick }: BetRecommendationProps) {
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showCrossRace, setShowCrossRace] = useState(false)

  const engine = useMemo(() => runBettingEngine(rows, DEFAULT_BANKROLL), [rows])

  const ranked = useMemo(
    () => [...rows].filter(r => pFinal(r) > 0).sort((a, b) => pFinal(b) - pFinal(a)),
    [rows],
  )

  const marketRankById = useMemo(() => {
    const map = new Map<string, number>()
    ;[...rows]
      .filter(r => !isOddsPending(r.win_odds))
      .sort((a, b) => (a.win_odds as number) - (b.win_odds as number))
      .forEach((r, i) => map.set(r.runner_id, i + 1))
    return map
  }, [rows])

  const oddsReady = rows.length > 0 && rows.every(r => !isOddsPending(r.win_odds))

  const picks = useMemo((): Pick[] => {
    if (ranked.length === 0) return []

    const safe = ranked[0]
    const safeBet = engine.winBets.find(b => b.row.runner_id === safe.runner_id && b.betType === 'WIN')
      ?? engine.winBets.find(b => b.row.runner_id === safe.runner_id)
    const safeStake = safeBet
      ? safeBet.amount
      : (ev(safe) > 0 ? Math.max(SAFE_MIN_STAKE, Math.round(kelly(safe) * DEFAULT_BANKROLL)) : SAFE_MIN_STAKE)

    const value = ranked.find(r => r.runner_id !== safe.runner_id && ev(r) > 0 && pMarket(r) > 0 && pModel(r) > pMarket(r))
    const valueBet = value ? engine.winBets.find(b => b.row.runner_id === value.runner_id) : undefined
    const valueStake = valueBet
      ? valueBet.amount
      : (value ? Math.max(LONGSHOT_STAKE, Math.round(kelly(value) * DEFAULT_BANKROLL)) : null)

    const usedIds = new Set([safe.runner_id, ...(value ? [value.runner_id] : [])])
    const longshotRow =
      engine.darkHorses.find(d => !usedIds.has(d.row.runner_id))?.row
      ?? ranked.find(r =>
        !usedIds.has(r.runner_id)
        && (r.win_odds ?? 0) >= LONGSHOT_ODDS_FLOOR
        && pMarket(r) > 0
        && pModel(r) > pMarket(r))

    return [
      { kind: 'safe', row: safe, stake: oddsReady ? safeStake : null, stars: starsFor(pFinal(safe)) },
      { kind: 'value', row: value ?? null, stake: value && oddsReady ? valueStake : null, stars: value ? starsFor(pFinal(value)) : 0 },
      { kind: 'longshot', row: longshotRow ?? null, stake: longshotRow && oddsReady ? LONGSHOT_STAKE : null, stars: longshotRow ? starsFor(pFinal(longshotRow)) : 0 },
    ]
  }, [ranked, engine, oddsReady])

  if (picks.length === 0) return null

  const totalStake = picks.reduce((s, p) => s + (p.stake ?? 0), 0)
  const crossRace = (allUpData?.strategies ?? []).slice(0, 3)

  return (
    <div className="bet-rec animate-fade-in">
      <div className="bet-rec-head">
        <div className="bet-rec-title">
          <span className="bet-rec-icon">&#x1F3AF;</span>
          <span>投注建議</span>
          <span className="bet-rec-meta">
            R{race?.race_no ?? '-'} {race?.venue === 'HV' ? '跑馬地' : race?.venue === 'ST' ? '沙田' : ''} {raceTime ?? race?.race_time ?? ''}
          </span>
        </div>
        <div className="bet-rec-budget">
          {oddsReady ? `HKD $${totalStake}/場` : '注碼待賠率開出'}
        </div>
      </div>

      {!oddsReady && (
        <div className="bet-rec-warn">
          賠率未開出 — 贏面可用，注碼與值博／爆冷須等即時賠率注入
        </div>
      )}

      <div className="bet-rec-rows">
        {picks.map(p => (
          <RecRow
            key={p.kind}
            pick={p}
            oddsReady={oddsReady}
            marketRank={p.row ? marketRankById.get(p.row.runner_id) : undefined}
            onHorseClick={onHorseClick}
          />
        ))}
      </div>

      <div className="bet-rec-toggles">
        <button
          type="button"
          className={`bet-rec-toggle ${showAdvanced ? 'open' : ''}`}
          onClick={() => setShowAdvanced(v => !v)}
        >
          進階數據 <span className="bet-rec-caret">{showAdvanced ? '▾' : '▸'}</span>
        </button>
        {crossRace.length > 0 && (
          <button
            type="button"
            className={`bet-rec-toggle ${showCrossRace ? 'open' : ''}`}
            onClick={() => setShowCrossRace(v => !v)}
          >
            跨場組合 <span className="bet-rec-caret">{showCrossRace ? '▾' : '▸'}</span>
          </button>
        )}
      </div>

      {showAdvanced && (
        <div className="bet-rec-advanced">
          <div className="bet-rec-weights">
            融合 P_final = {Math.round(MODEL_WEIGHT * 100)}% 模型 + {Math.round(MARKET_WEIGHT * 100)}% 市場
            &nbsp;·&nbsp; 每場預設資金 HKD ${DEFAULT_BANKROLL.toLocaleString()}（注碼按 1/4 Kelly 計算）
          </div>
          <table className="bet-rec-table">
            <thead>
              <tr>
                <th>馬匹</th>
                <th>P_model</th>
                <th>P_market</th>
                <th>P_final</th>
                <th>EV</th>
                <th>Kelly</th>
                <th>賠率</th>
                <th>市# / 分析#</th>
              </tr>
            </thead>
            <tbody>
              {ranked.slice(0, 6).map((r, i) => {
                const mr = marketRankById.get(r.runner_id)
                const delta = mr ? mr - (i + 1) : null
                return (
                  <tr key={r.runner_id}>
                    <td className="bet-rec-horse">#{r.horse_no} {r.horse_name}</td>
                    <td>{(pModel(r) * 100).toFixed(1)}%</td>
                    <td>{oddsReady ? `${(pMarket(r) * 100).toFixed(1)}%` : '待定'}</td>
                    <td>{(pFinal(r) * 100).toFixed(1)}%</td>
                    <td>{oddsReady ? fmtEV(ev(r)) : '待定'}</td>
                    <td>{oddsReady ? fmtKelly(kelly(r)) : '待定'}</td>
                    <td>{fmtOdds(r.win_odds)}</td>
                    <td>{mr ? `市#${mr} / 析#${i + 1}${delta && delta !== 0 ? ` (${delta > 0 ? '+' : ''}${delta})` : ''}` : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="bet-rec-combos">
            <span className="bet-rec-combo-label">組合</span>
            {engine.qCombos.slice(0, 2).map(q => (
              <span key={q.anchor.runner_id} className="bet-rec-chip">
                Q {q.anchor.horse_no} × {q.legs.map(l => l.row.horse_no).join(', ')} · ${q.totalCost}
              </span>
            ))}
            {engine.trio && (
              <span className="bet-rec-chip">
                單T {engine.trio.horses.map(h => h.horse_no).join('-')} · {engine.trio.estimatedOdds ? `估計 ${engine.trio.estimatedOdds.toFixed(0)}` : '賠率待定'}
              </span>
            )}
            {engine.quartet && (
              <span className="bet-rec-chip">
                四連環 {engine.quartet.horses.map(h => h.horse_no).join('-')}
              </span>
            )}
            {engine.overlays.length > 0 && (
              <span className="bet-rec-chip bet-rec-chip-good">
                Overlay {engine.overlays.slice(0, 3).map(o => `#${o.row.horse_no}(+${Math.round((o.ratio - 1) * 100)}%)`).join(' ')}
              </span>
            )}
            {engine.underlays.length > 0 && (
              <span className="bet-rec-chip bet-rec-chip-bad">
                市場高估 {engine.underlays.slice(0, 3).map(u => `#${u.row.horse_no}`).join(' ')}
              </span>
            )}
          </div>
        </div>
      )}

      {showCrossRace && crossRace.length > 0 && (
        <div className="bet-rec-cross">
          {crossRace.map(s => {
            const stake = crossStake(s.compositeProb, s.riskLevel)
            return (
              <div key={s.id} className="bet-rec-cross-row">
                <div className="bet-rec-line">
                  <span className="bet-rec-cross-name">{s.nameShort}</span>
                  <span className={`bet-rec-risk bet-rec-risk-${s.riskLevel}`}>{RISK_LABEL[s.riskLevel]}</span>
                  <span className="bet-rec-cross-payout">
                    {s.estimatedOdds
                      ? <>注 ${stake} 中咗有 <strong>${Math.round(s.estimatedOdds * stake)}</strong></>
                      : <>注 ${stake} · 賠率待定</>}
                  </span>
                </div>
                <div className="bet-rec-cross-legs">
                  {s.legs.map(leg => (
                    <span key={`${leg.raceId}-${leg.raceNo}`} className="bet-rec-cross-leg">
                      R{leg.raceNo} {LEG_TYPE[leg.legType]} {leg.horses.map(h => `#${h.horseNo}`).join('/')}
                    </span>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function RecRow({
  pick,
  oddsReady,
  marketRank,
  onHorseClick,
}: {
  pick: Pick
  oddsReady: boolean
  marketRank?: number
  onHorseClick?: (horseId: string, horseName: string) => void
}) {
  const { row, kind } = pick

  if (!row) {
    return (
      <div className={`bet-rec-row bet-rec-row-${kind} bet-rec-row-empty`}>
        <div className="bet-rec-line">
          <span className={`bet-rec-tag bet-rec-tag-${kind}`}>{KIND_LABEL[kind]}</span>
          <span className="bet-rec-none">暫無建議</span>
        </div>
        <div className="bet-rec-sub">
          {kind === 'value'
            ? (oddsReady ? '本場冇馬嘅賠率抵過模型估計 — 留手，等賠率有優勢先買' : '值博要等即時賠率開出先計到')
            : (oddsReady ? '本場冇符合條件嘅冷門價值馬' : '賠率未開出，未搵到冷腳')}
        </div>
      </div>
    )
  }

  const odds = row.win_odds ?? 0

  let right = ''
  let sub = ''
  if (kind === 'safe') {
    right = `贏面 ${(pFinal(row) * 100).toFixed(0)}%`
    sub = !oddsReady
      ? '賠率未開出 — 呢隻暫時贏面最高，注碼待定'
      : ev(row) > 0
        ? `賠 ${fmtOdds(odds)}，仲有 +${(ev(row) * 100).toFixed(1)}% 優勢`
        : '全場勝率最高，但賠率冇優勢 — 小注或留手'
  } else if (kind === 'value') {
    right = oddsReady ? `賠 ${fmtOdds(odds)} · 好過市場 ${((pModel(row) - pMarket(row)) * 100).toFixed(1)}%` : '好過市場 — 待賠率'
    sub = oddsReady ? `每投 $100，長遠期望多返 ${Math.round(ev(row) * 100)} 元` : '注碼要等即時賠率開出'
  } else {
    right = oddsReady ? `賠 ${fmtOdds(odds)} · 中咗有 $${Math.round(odds * (pick.stake ?? LONGSHOT_STAKE))}` : '小注博爆冷 · 待賠率'
    sub = oddsReady ? '市場睇低、模型睇高，輸贏唔傷元氣' : '賠率開出後先搵到冷腳'
  }

  return (
    <div className={`bet-rec-row bet-rec-row-${kind}`}>
      <div className="bet-rec-line">
        <span className={`bet-rec-tag bet-rec-tag-${kind}`}>{KIND_LABEL[kind]}</span>
        <button
          type="button"
          className="bet-rec-horse-btn"
          onClick={() => onHorseClick?.(row.horse_id, row.horse_name)}
        >
          #{row.horse_no} {row.horse_name}
        </button>
        <span className="bet-rec-stake">{pick.stake ? `$${pick.stake}` : '待賠率'}</span>
      </div>
      <div className="bet-rec-line">
        <span className="bet-rec-detail">{right}</span>
        <span className="bet-rec-extra">
          {pick.stars > 0 && <span className="bet-rec-stars">{'★'.repeat(pick.stars)}</span>}
          {marketRank ? <span className="bet-rec-mrank">市#{marketRank}</span> : null}
        </span>
      </div>
      <div className="bet-rec-sub">{sub}</div>
    </div>
  )
}
