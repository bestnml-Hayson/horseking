import { NextResponse } from 'next/server'
import { directFetch } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function GET() {
  try {
    const data = await directFetch(
      `pipeline_status?id=eq.auto_pilot_latest&select=*`
    )
    const rows = data as unknown as Array<{
      id: string
      last_run: string
      status_json: Record<string, unknown>
    }>

    if (!rows || rows.length === 0) {
      return NextResponse.json({
        ok: true,
        status: 'unknown',
        message: '尚未執行自動巡檢',
        last_run: null,
      })
    }

    const row = rows[0]
    const s = row.status_json ?? {}

    return NextResponse.json({
      ok: true,
      status: s.success ? 'healthy' : 'error',
      last_run: row.last_run,
      discovered: s.discovered ?? 0,
      scraped: s.scraped ?? 0,
      archived: s.archived ?? 0,
      errors: s.errors ?? [],
      elapsed_seconds: s.elapsed_seconds ?? 0,
    })
  } catch (e) {
    return NextResponse.json({
      ok: true,
      status: 'unknown',
      message: 'pipeline_status 表未建立或無法連線',
      last_run: null,
    })
  }
}
