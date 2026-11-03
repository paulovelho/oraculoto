import { describe, expect, it } from 'vitest'
import { formatBall, formatDate, formatDecimal, formatInt, formatMoney } from './format'

describe('formatMoney', () => {
  it.each([
    ['38295.72', 'R$ 38.295,72'],
    ['0.00', 'R$ 0,00'],
    ['954.26', 'R$ 954,26'],
    ['200000000.00', 'R$ 200.000.000,00'],
    ['187648868.43', 'R$ 187.648.868,43'],
    ['1000', 'R$ 1.000,00'],
    ['12.5', 'R$ 12,50'],
    ['-5.10', '-R$ 5,10'],
    // Precision that a float would lose.
    ['9007199254740993.99', 'R$ 9.007.199.254.740.993,99'],
  ])('%s → %s', (input, expected) => {
    expect(formatMoney(input)).toBe(expected)
  })

  it.each([null, undefined, '', 'abc', '1,5', '1.2.3'])('%s → —', (input) => {
    expect(formatMoney(input)).toBe('—')
  })
})

describe('formatDate', () => {
  it('splits the string, never shifts the day', () => {
    expect(formatDate('2026-10-20')).toBe('20/10/2026')
    expect(formatDate('1996-03-11')).toBe('11/03/1996')
  })

  it.each([null, undefined, '', '2026-10-20T00:00:00Z', '20/10/2026'])('%s → —', (input) => {
    expect(formatDate(input)).toBe('—')
  })
})

describe('formatInt', () => {
  it('groups thousands with dots', () => {
    expect(formatInt(50063860)).toBe('50.063.860')
    expect(formatInt(999)).toBe('999')
    expect(formatInt(0)).toBe('0')
    expect(formatInt(-1234)).toBe('-1.234')
  })

  it('refuses non-integers', () => {
    expect(formatInt(1.5)).toBe('—')
    expect(formatInt(null)).toBe('—')
  })
})

describe('formatBall', () => {
  it('pads to two digits', () => {
    expect(formatBall(2)).toBe('02')
    expect(formatBall(60)).toBe('60')
  })
})

describe('formatDecimal', () => {
  it.each([
    [307.2, '307,2'],
    [26.03, '26,03'],
    [9, '9'],
    [1.8, '1,8'],
    [0, '0'],
    [12345.678, '12.345,68'],
    [-0.001, '0'],
    [-2.5, '-2,5'],
  ])('%s → %s', (input, expected) => {
    expect(formatDecimal(input)).toBe(expected)
  })

  it('returns — for nothing', () => {
    expect(formatDecimal(null)).toBe('—')
    expect(formatDecimal(Number.NaN)).toBe('—')
  })
})
