// Small bits of arithmetic the stats page needs on top of what the API sends. Only baselines
// derived from the API's own `expected`, never a number that could pass for a prediction.

/** n choose k, exact for the sizes we use (60 choose 3 = 34,220). */
export function choose(n: number, k: number): number {
  if (k < 0 || k > n) return 0
  let r = 1
  for (let i = 1; i <= k; i++) r = (r * (n - k + i)) / i
  return Math.round(r)
}

/**
 * Where one ball's count lands in a fair draw: the exact binomial (n draws, p = balls_drawn / pool)
 * central range holding at least 1 − 2·tail of the probability, and the actual chance of falling
 * outside it. Exact, not ±2σ: with a short window (expected ≈ 1) the normal approximation lies.
 */
export function fairBand(
  draws: number,
  ballsDrawn: number,
  pool: number,
  tail = 0.025,
): { low: number; high: number; outside: number } {
  if (draws <= 0) return { low: 0, high: 0, outside: 0 }
  const p = ballsDrawn / pool
  const ratio = Math.log(p) - Math.log1p(-p)
  // Log space: (1 − p)^n underflows for long histories.
  let logPmf = draws * Math.log1p(-p)
  let cdf = 0
  let low = -1
  let below = 0
  for (let k = 0; k <= draws; k++) {
    const before = cdf
    cdf += Math.exp(logPmf)
    if (low < 0 && cdf > tail) {
      low = k
      below = before
    }
    if (cdf >= 1 - tail) return { low, high: k, outside: below + Math.max(0, 1 - cdf) }
    logPmf += Math.log(draws - k) - Math.log(k + 1) + ratio
  }
  return { low: Math.max(0, low), high: draws, outside: below }
}
