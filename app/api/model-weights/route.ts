import { NextResponse } from 'next/server'
import { directFetch } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'
export const revalidate = 0

interface WeightStatus {
  weights?: unknown
  fitted_at?: string
  sample_races?: number
  nll?: number
  baseline_nll?: number
}

export async function GET() {
  try {
    const rows = await directFetch(
      'pipeline_status?id=eq.model_weights_active&select=status_json'
    ) as Array<{ status_json?: WeightStatus }>
    const status = rows?.[0]?.status_json ?? null
    return NextResponse.json({
      ok: true,
      weights: status?.weights ?? null,
      fitted_at: status?.fitted_at ?? null,
      sample_races: status?.sample_races ?? 0,
      nll: status?.nll ?? null,
      baseline_nll: status?.baseline_nll ?? null,
    })
  } catch {
    return NextResponse.json({ ok: true, weights: null })
  }
}