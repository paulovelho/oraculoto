import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cached, prime, resetCache, setLatestContest } from './cache'

beforeEach(resetCache)

describe('cached', () => {
  it('shares one call between concurrent and later callers', async () => {
    const load = vi.fn(async () => 42)
    const [a, b] = await Promise.all([cached('k', load), cached('k', load)])
    await cached('k', load)
    expect([a, b]).toEqual([42, 42])
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('never keeps a failure', async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce(7)
    await expect(cached('k', load)).rejects.toThrow('boom')
    await expect(cached('k', load)).resolves.toBe(7)
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('does not let a stale failure evict a newer entry', async () => {
    let fail!: (e: Error) => void
    const first = cached('k', () => new Promise<number>((_, reject) => (fail = reject)))
    setLatestContest(1)
    setLatestContest(2) // clears
    const second = cached('k', async () => 9)
    fail(new Error('old'))
    await expect(first).rejects.toThrow('old')
    const load = vi.fn(async () => 0)
    await expect(cached('k', load)).resolves.toBe(9)
    expect(load).not.toHaveBeenCalled()
    await second
  })
})

describe('setLatestContest', () => {
  it('keeps entries stored before the first /health', async () => {
    await cached('k', async () => 'a')
    setLatestContest(3072)
    await expect(cached('k', async () => 'b')).resolves.toBe('a')
  })

  it('keeps entries when the latest contest is unchanged or unknown', async () => {
    setLatestContest(3072)
    await cached('k', async () => 'a')
    setLatestContest(3072)
    setLatestContest(null)
    await expect(cached('k', async () => 'b')).resolves.toBe('a')
  })

  it('clears everything when a new contest arrives', async () => {
    setLatestContest(3072)
    await cached('k', async () => 'a')
    setLatestContest(3073)
    await expect(cached('k', async () => 'b')).resolves.toBe('b')
  })
})

describe('prime', () => {
  it('seeds a value without overwriting an existing entry', async () => {
    prime('k', 1)
    prime('k', 2)
    await expect(cached('k', async () => 3)).resolves.toBe(1)
  })
})
