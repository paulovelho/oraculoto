import type { Draw, PrizeTier, WinnerLocation } from '@/api'

/** The order to show the balls in: as drawn when known, ascending otherwise. */
export function displayBalls(draw: Draw): { balls: number[]; drawnOrder: boolean } {
  const order = draw.draw_order
  return order && order.length === draw.balls.length
    ? { balls: order, drawnOrder: true }
    : { balls: draw.balls, drawnOrder: false }
}

const TIER_NAMES: Record<number, string> = { 6: 'Sena', 5: 'Quina', 4: 'Quadra' }

export function tierName(hits: number): string {
  return TIER_NAMES[hits] ?? `${hits} acertos`
}

/**
 * Whether the jackpot was won, from the prize tiers. Never from rollover_amount: 25 contests had
 * a jackpot winner and a non-zero rollover (docs/database.md §2). Null when we don't know.
 */
export function jackpotWon(draw: Draw): boolean | null {
  const top = Math.max(...draw.prizes.map((p) => p.hits))
  const winners = draw.prizes.find((p) => p.hits === top)?.winners
  return winners === null || winners === undefined ? null : winners > 0
}

/** Tiers, most hits first, whatever order they arrive in. */
export function sortedPrizes(prizes: PrizeTier[]): PrizeTier[] {
  return [...prizes].sort((a, b) => b.hits - a.hits)
}

export function locationLabel(loc: WinnerLocation): string {
  if (loc.is_online) return 'Canal eletrônico (internet)'
  if (loc.city && loc.uf) return `${loc.city}/${loc.uf}`
  return loc.raw
}
