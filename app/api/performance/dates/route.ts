import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const supabase = getServerSupabase()

    // Debug: log env vars (without exposing full keys)
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? process.env.SUPABASE_URL
    const hasServiceKey = !!process.env.SUPABASE_SERVICE_KEY
    console.log('[API /performance/dates] Supabase URL:', url?.substring(0, 30) + '...')
    console.log('[API /performance/dates] Has service key:', hasServiceKey)

    const { data: perfDates, error: perfError } = await supabase
      .from('ai_performance')
      .select('race_date')
      .not('race_date', 'is', null)
      .order('race_date', { ascending: false })

    if (perfError) {
      console.error('[API /performance/dates] error:', perfError)
      return NextResponse.json({ ok: false, error: perfError.message }, { status: 500 })
    }

    console.log('[API /performance/dates] Raw rows count:', perfDates?.length ?? 0)
    if (perfDates && perfDates.length > 0) {
      console.log('[API /performance/dates] First 3 rows:', JSON.stringify(perfDates.slice(0, 3)))
    }

    const dateSet = new Set<string>()
    for (const d of ((perfDates ?? []) as { race_date: string | null }[])) {
      if (d.race_date) dateSet.add(d.race_date)
    }

    const uniqueDates = Array.from(dateSet)
      .filter(Boolean)
      .sort()
      .reverse()

    console.log('[API /performance/dates] Unique dates count:', uniqueDates.length)
    console.log('[API /performance/dates] Has 2026-10-04:', uniqueDates.includes('2026-10-04'))

    return NextResponse.json({
      ok: true,
      dates: uniqueDates,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Internal error'
    console.error('[API /performance/dates] error:', err)
    return NextResponse.json({ ok: false, error: message }, { status: 500 })
  }
}
