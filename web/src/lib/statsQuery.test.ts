import { describe, expect, it } from 'vitest'
import { parseBalls, parseTogether, parseWindow, positiveInt, statsRouteQuery, windowQuery } from './statsQuery'

const RULES = { ball_min: 1, ball_max: 60, balls_drawn: 6 }

describe('positiveInt', () => {
  it.each([
    ['12', 12],
    [' 7 ', 7],
    ['0', null],
    ['-3', null],
    ['1.5', null],
    ['12abc', null],
    ['', null],
    [null, null],
    ['99999999999999999999', null],
  ])('%s → %s', (input, expected) => {
    expect(positiveInt(input)).toBe(expected)
  })
})

describe('parseWindow', () => {
  it('defaults to the whole history', () => {
    expect(parseWindow({})).toEqual({ kind: 'all' })
  })

  it('reads last=N', () => {
    expect(parseWindow({ last: '100' })).toEqual({ kind: 'last', last: 100 })
  })

  it('reads from/to, either one optional', () => {
    expect(parseWindow({ from: '10', to: '20' })).toEqual({ kind: 'range', from: 10, to: 20 })
    expect(parseWindow({ from: '10' })).toEqual({ kind: 'range', from: 10, to: null })
    expect(parseWindow({ to: '20' })).toEqual({ kind: 'range', from: null, to: 20 })
  })

  it('drops what the API would reject', () => {
    expect(parseWindow({ last: '5', from: '1' })).toEqual({ kind: 'all' })
    expect(parseWindow({ from: '20', to: '10' })).toEqual({ kind: 'all' })
    expect(parseWindow({ last: '0' })).toEqual({ kind: 'all' })
  })

  it('takes the first of repeated keys', () => {
    expect(parseWindow({ last: ['3', '4'] })).toEqual({ kind: 'last', last: 3 })
  })
})

describe('windowQuery', () => {
  it('matches the API parameters', () => {
    expect(windowQuery({ kind: 'all' })).toEqual({})
    expect(windowQuery({ kind: 'last', last: 50 })).toEqual({ last: 50 })
    expect(windowQuery({ kind: 'range', from: 1, to: null })).toEqual({ from: 1, to: null })
  })
})

describe('parseBalls', () => {
  it('sorts a valid selection', () => {
    expect(parseBalls('53,10', RULES)).toEqual([10, 53])
  })

  it.each(['', '0', '61', '10,10', '1,2,3,4,5,6,7', '10,,53', 'a'])('rejects %j', (raw) => {
    expect(parseBalls(raw, RULES)).toEqual([])
  })
})

describe('parseTogether / statsRouteQuery', () => {
  it('round-trips', () => {
    const query = { last: '100', balls: '10,53', jackpot: '1', page: '3' }
    const together = parseTogether(query, RULES)
    expect(together).toEqual({ balls: [10, 53], jackpot: true, page: 3 })
    expect(statsRouteQuery(parseWindow(query), together)).toEqual(query)
  })

  it('leaves defaults and orphan together keys out', () => {
    expect(statsRouteQuery({ kind: 'range', from: 5, to: null }, { balls: [], jackpot: true, page: 2 })).toEqual({ from: '5' })
    expect(statsRouteQuery({ kind: 'all' }, { balls: [4], jackpot: false, page: 1 })).toEqual({ balls: '4' })
  })
})
