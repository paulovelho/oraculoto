import { describe, expect, it } from 'vitest'
import { choose, fairBand } from './stats'

describe('choose', () => {
  it('counts the Mega-Sena combinations', () => {
    expect(choose(60, 2)).toBe(1770)
    expect(choose(60, 3)).toBe(34220)
    expect(choose(60, 6)).toBe(50063860)
    expect(choose(5, 7)).toBe(0)
  })
})

describe('fairBand', () => {
  it('matches the normal approximation on a long history', () => {
    // 3072 draws: expected 307.2, σ ≈ 16.63, so roughly 275 to 340.
    const { low, high, outside } = fairBand(3072, 6, 60)
    expect(low).toBeGreaterThanOrEqual(273)
    expect(low).toBeLessThanOrEqual(276)
    expect(high).toBeGreaterThanOrEqual(339)
    expect(high).toBeLessThanOrEqual(341)
    expect(outside).toBeLessThanOrEqual(0.05)
    expect(outside).toBeGreaterThan(0.03)
  })

  it('is exact on a short window', () => {
    // 10 draws, p = 0.1: P(0) = 0.349 > 2.5%, P(≤3) = 0.98720 ≥ 97.5%
    expect(fairBand(10, 6, 60)).toMatchObject({ low: 0, high: 3 })
    expect(fairBand(10, 6, 60).outside).toBeCloseTo(1 - 0.98720, 4)
  })

  it('is empty with no draws', () => {
    expect(fairBand(0, 6, 60)).toEqual({ low: 0, high: 0, outside: 0 })
  })
})
