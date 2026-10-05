import { NextResponse } from 'next/server'
import { directFetch } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function GET() {
  try {
    const [raceDates, perfDates] = await Promise.all([
      directFetch('races?is_finished=eq.true&race_date=not.is.null&select=race_date&order=race_date.desc').catch(() => []),
      directFetch('ai_performance?race_date=not.is.null&select=race_date&order=race_date.desc').catch(() => []),
    ])

    const dateSet = new Set<string>()
    for (const d of raceDates as { race_date: string | null }[]) {
      if (d.race_date) dateSet.add(d.race_date)
    }
    for (const d of perfDates as { race_date: string | null }[]) {
      if (d.race_date) dateSet.add(d.race_date)
    }

    const uniqueDates = Array.from(dateSet).filter(Boolean).sort().reverse()

    return NextResponse.json({ ok: true, dates: uniqueDates })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Internal error'
    console.error('[API /performance/dates] error:', err)
    return NextResponse.json({ ok: false, error: message }, { status: 500 })
  }
}
