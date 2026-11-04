import { describe, expect, it } from 'vitest'
import { choose, jackpotOdds } from './bets'

describe('choose', () => {
  it('counts combinations', () => {
    expect(choose(60, 6)).toBe(50_063_860)
    expect(choose(60, 2)).toBe(1_770)
    expect(choose(6, 6)).toBe(1)
    expect(choose(60, 20)).toBe(4_191_844_505_805_495)
  })
  it('is 0 outside its domain', () => {
    expect(choose(5, 6)).toBe(0)
    expect(choose(6, -1)).toBe(0)
  })
})

describe('jackpotOdds', () => {
  it('matches the official Mega-Sena odds', () => {
    expect(jackpotOdds(6)).toBe(50_063_860)
    expect(jackpotOdds(7)).toBe(7_151_980)
    expect(jackpotOdds(15)).toBe(10_003)
  })
  it('is null for bets too small or too large', () => {
    expect(jackpotOdds(5)).toBeNull()
    expect(jackpotOdds(61)).toBeNull()
  })
})
