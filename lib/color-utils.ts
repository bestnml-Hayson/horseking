/**
 * Shared color utilities for the Horse AI racing system.
 * Enforces consistent "win green / loss red" (贏綠輸紅) palette across all components.
 *
 * Green = emerald-400/500 for positive / wins / hits
 * Red   = rose-500    for negative / losses / misses
 */

export function getFormColor(pos: number): string {
  if (pos <= 3) return '#10b981'
  if (pos <= 6) return '#f59e0b'
  return '#ef4444'
}

export function getFormTailwindClass(pos: number): string {
  if (pos <= 3) return 'text-emerald-400 bg-emerald-500/20 border-emerald-500/40'
  if (pos <= 6) return 'text-amber-400 bg-amber-500/20 border-amber-500/40'
  return 'text-rose-500 bg-rose-500/20 border-rose-500/40'
}

export function getROITextClass(value: number): string {
  if (value > 0) return 'text-emerald-400'
  if (value < 0) return 'text-rose-500'
  return 'text-slate-400'
}

export function getROIBgClass(value: number): string {
  if (value > 0) return 'bg-emerald-500/20 text-emerald-400'
  if (value < 0) return 'bg-rose-500/20 text-rose-500'
  return 'bg-slate-500/20 text-slate-400'
}

export function getHitBadgeClass(isHit: boolean): string {
  return isHit
    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40'
    : 'bg-rose-500/20 text-rose-500 border-rose-500/40'
}

export function getKellyColor(value: number | null): string {
  if (value != null && value > 0) return '#10b981'
  return '#64748b'
}

export const FACTOR_COLORS = {
  form: '#818cf8',
  draw: '#f59e0b',
  jockeyTrainer: '#10b981',
  courseDistance: '#3b82f6',
} as const

export const STAT_COLORS = {
  wins: '#10b981',
  places: '#3b82f6',
  shows: '#f59e0b',
} as const

export const PICK_ACCENT_COLORS = ['#f59e0b', '#94a3b8', '#d97706', '#38bdf8'] as const

export const MUTED_TEXT_COLOR = '#64748b'
