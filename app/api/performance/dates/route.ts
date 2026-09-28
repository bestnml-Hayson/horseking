import { NextResponse } from 'next/server'
import { getServerSupabase } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const supabase = getServerSupabase()

    const { data: dates, error } = await supabase
      .from('ai_performance')
      .select('race_date')
      .not('race_date', 'is', null)
      .order('race_date', { ascending: false })

    if (error) {
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 })
    }

    const uniqueDates = Array.from(new Set((dates ?? []).map((d: any) => d.race_date)))
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
