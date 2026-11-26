import { createClient } from '@supabase/supabase-js'

export function getServerSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? process.env.SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!url || !key) throw new Error('Missing Supabase env vars')
  return createClient(url, key)
}

export async function directFetch(query: string): Promise<unknown[]> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? process.env.SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!url || !key) throw new Error('Missing Supabase env vars')

  const res = await fetch(`${url}/rest/v1/${query}`, {
    headers: {
      'apikey': key,
      'Authorization': `Bearer ${key}`,
    },
    cache: 'no-store',
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Supabase REST ${res.status}: ${text}`)
  }
  return res.json()
}

/**
 * directFetch across every page. This server clamps each response to 1000 rows
 * whatever `limit` says, so a large `in.(...)` batch silently loses rows unless
 * it is paged with a stable order.
 */
export async function directFetchAll(baseQuery: string, orderBy: string): Promise<unknown[]> {
  const all: unknown[] = []
  for (let offset = 0; ; offset += 1000) {
    const rows = await directFetch(`${baseQuery}&order=${orderBy}.asc&offset=${offset}&limit=1000`) as unknown[]
    all.push(...rows)
    if (rows.length < 1000) return all
  }
}
