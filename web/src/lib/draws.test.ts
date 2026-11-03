import { describe, expect, it } from 'vitest'
import type { Draw } from '@/api'
import { displayBalls, jackpotWon, locationLabel, sortedPrizes, tierName } from './draws'

// Contest 3072 as the live API returns it (2026-11-03), trimmed.
function draw(overrides: Partial<Draw> = {}): Draw {
  return {
    contest: 3072,
    date: '2026-10-20',
    balls: [2, 6, 9, 16, 31, 40],
    draw_order: null,
    prizes: [
      { hits: 6, winners: 0, prize_per_winner: '0.00' },
      { hits: 5, winners: 140, prize_per_winner: '38295.72' },
      { hits: 4, winners: 9261, prize_per_winner: '954.26' },
    ],
    winner_locations: [],
    total_collected: '134543238.00',
    rollover_amount: '187648868.43',
    next_estimated_prize: '200000000.00',
    special_accumulated: '106119095.67',
    notes: null,
    is_special: null,
    source: 'xlsx',
    ...overrides,
  }
}

describe('displayBalls', () => {
  it('uses ascending order when draw_order is null', () => {
    expect(displayBalls(draw())).toEqual({ balls: [2, 6, 9, 16, 31, 40], drawnOrder: false })
  })

  it('uses the drawn order when known', () => {
    const d = draw({ draw_order: [31, 2, 40, 9, 6, 16] })
    expect(displayBalls(d)).toEqual({ balls: [31, 2, 40, 9, 6, 16], drawnOrder: true })
  })

  it('ignores a draw_order of the wrong length', () => {
    expect(displayBalls(draw({ draw_order: [31, 2] })).drawnOrder).toBe(false)
  })
})

describe('jackpotWon', () => {
  it('is false with zero top-tier winners, whatever the rollover says', () => {
    expect(jackpotWon(draw())).toBe(false)
  })

  it('is true with a winner even when the rollover is not zero', () => {
    const d = draw({ prizes: [{ hits: 6, winners: 1, prize_per_winner: '158039482.14' }], rollover_amount: '36227396.57' })
    expect(jackpotWon(d)).toBe(true)
  })

  it('is null when the top-tier count is unknown', () => {
    expect(jackpotWon(draw({ prizes: [{ hits: 6, winners: null, prize_per_winner: null }] }))).toBe(null)
    expect(jackpotWon(draw({ prizes: [] }))).toBe(null)
  })
})

describe('sortedPrizes / tierName', () => {
  it('puts the most hits first and names the Mega-Sena tiers', () => {
    const prizes = sortedPrizes([...draw().prizes].reverse())
    expect(prizes.map((p) => tierName(p.hits))).toEqual(['Sena', 'Quina', 'Quadra'])
    expect(tierName(3)).toBe('3 acertos')
  })
})

describe('locationLabel', () => {
  it('handles the three shapes the API sends', () => {
    expect(locationLabel({ city: 'FORTALEZA', uf: 'CE', is_online: false, winners: null, raw: 'FORTALEZA/CE' })).toBe('FORTALEZA/CE')
    expect(locationLabel({ city: null, uf: null, is_online: true, winners: null, raw: 'CANAL ELETRONICO' })).toBe('Canal eletrônico (internet)')
    expect(locationLabel({ city: null, uf: null, is_online: false, winners: null, raw: '???' })).toBe('???')
  })
})
