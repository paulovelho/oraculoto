// Response shapes from docs/api.md. Money is a decimal string, dates are YYYY-MM-DD,
// timestamps are ISO 8601 UTC with a Z.

export type Money = string
export type IsoDate = string

export interface GameHealth {
  game: string
  latest_contest: number | null
  latest_date: IsoDate | null
  last_crawl: string | null
  stale: boolean
}

export interface Health {
  database: string
  games: GameHealth[]
}

export interface Game {
  slug: string
  name: string
  balls_drawn: number
  ball_min: number
  ball_max: number
  prize_tiers: number[]
  bet_min_numbers: number
  bet_max_numbers: number
}

// One contest, as built (docs/api.md §4). Unknown values are null, never 0.
export interface PrizeTier {
  hits: number
  winners: number | null
  prize_per_winner: Money | null
}

export interface WinnerLocation {
  city: string | null
  uf: string | null
  is_online: boolean
  /** Null in every xlsx row: the spreadsheet lists places, not counts. */
  winners: number | null
  raw: string
}

export interface Draw {
  contest: number
  date: IsoDate
  /** Ascending. */
  balls: number[]
  /** Null unless every position is known (never for xlsx rows). */
  draw_order: number[] | null
  prizes: PrizeTier[]
  winner_locations: WinnerLocation[]
  total_collected: Money | null
  rollover_amount: Money | null
  next_estimated_prize: Money | null
  special_accumulated: Money | null
  notes: string | null
  is_special: boolean | null
  source: string
}

// Stats (docs/api.md §4). Every response carries the window it actually covered: null bounds and
// 0 draws when it's empty, which is not an error. Floats are plain numbers (rounded by the API).
export interface StatsWindow {
  from: number | null
  to: number | null
  draws: number
}

export interface Frequency {
  window: StatsWindow
  /** draws × balls_drawn / pool: what each ball would get in a fair draw. */
  expected: number
  /** Every ball in range, most frequent first. */
  items: { ball: number; times: number }[]
}

export interface BallGap {
  ball: number
  /** Null when the ball wasn't drawn in the window. */
  last_seen: number | null
  current_gap: number
  /** Only runs between two appearances; null with fewer than two. */
  longest_gap: number | null
}

export interface Gaps {
  window: StatsWindow
  expected_gap: number
  /** Longest current absence first. */
  items: BallGap[]
}

/** Fixed at the last 100 contests (docs/api.md §4): it ignores the stats window. */
export interface Heat {
  window: StatsWindow
  history: StatsWindow
  version: number
  /** Hottest first. heat = recent − what the ball's own long-run rate predicts for the window. */
  items: { ball: number; heat: number; recent: number; overall: number }[]
}

export interface Combinations {
  window: StatsWindow
  size: number
  expected: number
  items: { balls: number[]; times: number }[]
}

export interface ContestRef {
  contest: number
  date: IsoDate
}

export interface Together {
  window: StatsWindow
  balls: number[]
  jackpot: boolean
  expected: number
  last: ContestRef | null
  items: ContestRef[]
  page: number
  limit: number
  total: number
}

/** Paged lists (docs/api.md §3). */
export interface Page<T> {
  items: T[]
  page: number
  limit: number
  total: number
}

/** What one bet won in one tier (scored like a ticket, docs/api.md §6). */
export interface BetWin {
  hits: number
  combinations: number
  prize_per_winner: Money | null
  amount: Money | null
}

/**
 * Oraculoto's own bet on one contest (docs/api.md §11). Nulls and no prizes unless `drawn`, except
 * `date`: on a `pending` bet it's the announced draw date (null if Caixa hasn't announced it).
 */
export interface OraculotoBet {
  contest: number
  /** Ascending. */
  numbers: number[]
  source: string
  created_at: string
  /** `missing`: the contest is past but its draw isn't in the database. */
  status: 'pending' | 'drawn' | 'missing'
  date: IsoDate | null
  hits: number | null
  matched: number[] | null
  prizes: BetWin[]
  total: Money | null
}
