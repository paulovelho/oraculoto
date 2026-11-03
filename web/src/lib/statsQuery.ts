// The stats page keeps its state in the URL, so a window or a "together" search can be shared.
// Keys: last | from, to (the window, as the API takes it) and balls, jackpot, page (together).
// Anything malformed is dropped, never sent: the API would only answer with a 400.

import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import type { Query } from '@/api'

export type WindowSel =
  | { kind: 'all' }
  | { kind: 'last'; last: number }
  | { kind: 'range'; from: number | null; to: number | null }

export interface TogetherSel {
  balls: number[]
  jackpot: boolean
  page: number
}

export interface BallRules {
  ball_min: number
  ball_max: number
  balls_drawn: number
}

function first(value: LocationQuery[string] | undefined): string | null {
  const v = Array.isArray(value) ? value[0] : value
  return v ?? null
}

/** A positive integer, or null. "12abc", "0", "-3" and "1.5" are null. */
export function positiveInt(value: string | null | undefined): number | null {
  if (!value || !/^\d+$/.test(value.trim())) return null
  const n = Number(value)
  return Number.isSafeInteger(n) && n >= 1 ? n : null
}

export function parseWindow(query: LocationQuery): WindowSel {
  const last = positiveInt(first(query.last))
  const from = positiveInt(first(query.from))
  const to = positiveInt(first(query.to))
  if (last !== null) return from === null && to === null ? { kind: 'last', last } : { kind: 'all' }
  if (from === null && to === null) return { kind: 'all' }
  if (from !== null && to !== null && from > to) return { kind: 'all' }
  return { kind: 'range', from, to }
}

/** The window as API query parameters (and as URL query keys: they're the same). */
export function windowQuery(sel: WindowSel): Query {
  if (sel.kind === 'last') return { last: sel.last }
  if (sel.kind === 'range') return { from: sel.from, to: sel.to }
  return {}
}

/** Distinct, in range, at most balls_drawn, ascending. Anything else gives no selection at all. */
export function parseBalls(raw: string | null, rules: BallRules): number[] {
  if (!raw) return []
  const parts = raw.split(',')
  const balls = parts.map((p) => positiveInt(p))
  if (balls.some((b) => b === null || b < rules.ball_min || b > rules.ball_max)) return []
  const unique = [...new Set(balls as number[])].sort((a, b) => a - b)
  if (unique.length !== balls.length || unique.length > rules.balls_drawn) return []
  return unique
}

export function parseTogether(query: LocationQuery, rules: BallRules): TogetherSel {
  return {
    balls: parseBalls(first(query.balls), rules),
    jackpot: first(query.jackpot) === '1',
    page: positiveInt(first(query.page)) ?? 1,
  }
}

/** The whole page state as a URL query; defaults are left out to keep links short. */
export function statsRouteQuery(sel: WindowSel, together: TogetherSel): LocationQueryRaw {
  const q: LocationQueryRaw = {}
  for (const [k, v] of Object.entries(windowQuery(sel))) if (v !== null && v !== undefined) q[k] = String(v)
  if (together.balls.length) {
    q.balls = together.balls.join(',')
    if (together.jackpot) q.jackpot = '1'
    if (together.page > 1) q.page = String(together.page)
  }
  return q
}
