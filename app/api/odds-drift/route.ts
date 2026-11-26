import { NextResponse } from 'next/server'
import { directFetch } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'
export const revalidate = 0

interface DriftRace {
  race_date?: string
  runners?: Record<string, unknown>
}

export async function GET(req: Request) {
  const raceId = new URL(req.url).searchParams.get('raceId')
  if (!raceId) {
    return NextResponse.json({ ok: false, error: 'raceId required' }, { status: 400 })
  }
  try {
    const rows = await directFetch(
      'pipeline_status?id=eq.odds_drift&select=status_json'
    ) as Array<{ status_json?: { races?: Record<string, DriftRace> } }>
    const race = rows?.[0]?.status_json?.races?.[raceId]
    return NextResponse.json({
      ok: true,
      race_date: race?.race_date ?? null,
      runners: race?.runners ?? {},
    })
  } catch {
    return NextResponse.json({ ok: true, runners: {} })
  }
}