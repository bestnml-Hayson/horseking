import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const supabase = getServerSupabase()

    // Try querying races table for finished races with ai_performance data
    const { data: raceDates, error: raceError } = await supabase
      .from('races')
      .select('race_date')
      .eq('is_finished', true)
      .not('race_date', 'is', null)
      .order('race_date', { ascending: false })

    if (raceError) {
      console.error('[API /performance/dates] races query error:', raceError)
    }

    // Also try ai_performance table as fallback
    const { data: perfDates, error: perfError } = await supabase
      .from('ai_performance')
      .select('race_date')
      .not('race_date', 'is', null)
      .order('race_date', { ascending: false })

    if (perfError) {
      console.error('[API /performance/dates] ai_performance query error:', perfError)
    }

    console.log('[API /performance/dates] races rows:', raceDates?.length ?? 0)
    console.log('[API /performance/dates] ai_performance rows:', perfDates?.length ?? 0)

    const dateSet = new Set<string>()

    // Add dates from races table
    for (const d of ((raceDates ?? []) as { race_date: string | null }[])) {
      if (d.race_date) dateSet.add(d.race_date)
    }

    // Add dates from ai_performance table
    for (const d of ((perfDates ?? []) as { race_date: string | null }[])) {
      if (d.race_date) dateSet.add(d.race_date)
    }

    const uniqueDates = Array.from(dateSet)
      .filter(Boolean)
      .sort()
      .reverse()

    console.log('[API /performance/dates] Total unique dates:', uniqueDates.length)
    console.log('[API /performance/dates] Latest 5:', uniqueDates.slice(0, 5))
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
