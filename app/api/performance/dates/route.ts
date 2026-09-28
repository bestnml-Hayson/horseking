import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const supabase = getServerSupabase()

    const { data: perfDates, error: perfError } = await supabase
      .from('ai_performance')
      .select('race_date')
      .not('race_date', 'is', null)
      .order('race_date', { ascending: false })

    if (perfError) {
      console.error('[API /performance/dates] error:', perfError)
      return NextResponse.json({ ok: false, error: perfError.message }, { status: 500 })
    }

    const dateSet = new Set<string>()
    for (const d of (perfDates ?? []) as any[]) {
      if (d.race_date) dateSet.add(d.race_date)
    }

    const uniqueDates = Array.from(dateSet)
      .filter(Boolean)
      .sort()
      .reverse()

    return NextResponse.json({
      ok: true,
      dates: uniqueDates,
    })
  } catch (err: any) {
    console.error('[API /performance/dates] error:', err)
    return NextResponse.json({ ok: false, error: err.message ?? 'Internal error' }, { status: 500 })
  }
}
