import { cached, prime } from '@/lib/cache'
import { buildUrl, request, type Query } from './client'
import type { Combinations, Draw, Frequency, Game, Gaps, Heat, Health, OraculotoBet, Page, Together } from './types'

export { ApiError, toApiError, type Query } from './client'
export type * from './types'

// v1 has a single game. When there are more, this becomes a parameter, not a rewrite.
const GAME = 'megasena'

// /health is never cached: it is what tells us whether anything else is stale.
export const getHealth = () => request<Health>('/health')
export const getGames = () => cached('games', () => request<Game[]>('/games'))
export const getGame = async () => (await getGames()).find((g) => g.slug === GAME) ?? null

export const getLatestDraw = () =>
  cached(`${GAME}/draws/latest`, async () => {
    const draw = await request<Draw>(`/games/${GAME}/draws/latest`)
    prime(`${GAME}/draws/${draw.contest}`, draw)
    return draw
  })

export const getDraw = (contest: number) =>
  cached(`${GAME}/draws/${contest}`, () => request<Draw>(`/games/${GAME}/draws/${contest}`))

// Stats only change when a new contest arrives, so they're cached like draws (docs/web.md §4).
// The full URL is the key: one entry per window and parameter set.
function stats<T>(name: string, query: Query): Promise<T> {
  const path = `/games/${GAME}/stats/${name}`
  return cached(buildUrl(path, query), () => request<T>(path, query))
}

/** `window` is what `windowQuery` (lib/statsQuery) builds: {}, { last } or { from, to }. */
export const getFrequency = (window: Query) => stats<Frequency>('frequency', window)
export const getGaps = (window: Query) => stats<Gaps>('gaps', window)
// No window: the API fixes it at 100 so the browser can cache it (Cache-Control + ETag).
export const getHeat = () => stats<Heat>('heat', {})
export const getCombinations = (window: Query, size: 2 | 3, top = 20) =>
  stats<Combinations>('pairs', { ...window, size, top })
export const getTogether = (window: Query, balls: number[], jackpot: boolean, page: number, limit = 20) =>
  stats<Together>('together', { ...window, balls: balls.join(','), jackpot, page, limit })

// Oraculoto's own bets (docs/api.md §11). Never cached: a bet appears after the draw that the
// session cache is keyed on, so a cached "no bet yet" would outlive the bet.
export const getOraculotoBets = (page = 1, limit = 20) =>
  request<Page<OraculotoBet>>(`/games/${GAME}/oraculoto`, { page, limit })
/** Its bet on one contest; 404 (`not_found`) when it has none. Never cached, for the same reason. */
export const getOraculotoBet = (contest: number) => request<OraculotoBet>(`/games/${GAME}/oraculoto/${contest}`)
