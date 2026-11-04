// Mega-Sena: 6 balls drawn from 1–60 (v1 has one game, as in api/index.ts).
const POOL = 60
const DRAWN = 6

/** C(n, k), exact up to C(60, 20) (≈ 4.2e15, below 2^53). */
export function choose(n: number, k: number): number {
  if (!Number.isInteger(n) || !Number.isInteger(k) || k < 0 || k > n) return 0
  const m = Math.min(k, n - k)
  let r = 1
  for (let i = 1; i <= m; i++) r = (r * (n - m + i)) / i
  return Math.round(r)
}

/**
 * The "1 in N" of hitting the jackpot with a k-number bet: C(60,6) / C(k,6), rounded.
 * 6 numbers → 50,063,860 (docs/web.md §5). Null outside the game's bet sizes.
 */
export function jackpotOdds(k: number, pool = POOL, drawn = DRAWN): number | null {
  const ways = choose(k, drawn)
  if (k > pool || ways === 0) return null
  return Math.round(choose(pool, drawn) / ways)
}
