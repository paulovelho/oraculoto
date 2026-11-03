// The session cache from docs/web.md §4: in memory, keyed by the latest contest /health reports.
// Everything stored here only changes when a new contest arrives, so a new latest contest
// throws it all away. Promises are stored, not values, so two components asking for the same
// thing at once share one ~1.3 s call. Failures are never kept.

const store = new Map<string, Promise<unknown>>()
let latestContest: number | null = null

export function cached<T>(key: string, load: () => Promise<T>): Promise<T> {
  const hit = store.get(key)
  if (hit) return hit as Promise<T>
  const promise = load()
  store.set(key, promise)
  promise.catch(() => {
    // Only evict our own entry: a clear() plus a newer call may have replaced it meanwhile.
    if (store.get(key) === promise) store.delete(key)
  })
  return promise
}

/** Seeds an entry with a value already in hand (e.g. draws/latest is also draws/{n}). */
export function prime<T>(key: string, value: T): void {
  if (!store.has(key)) store.set(key, Promise.resolve(value))
}

/**
 * Called with every /health result. Entries stored before the first /health came back are
 * kept: this page load started after they were current. Only a change invalidates.
 */
export function setLatestContest(contest: number | null): void {
  if (contest === null) return
  if (latestContest !== null && contest !== latestContest) store.clear()
  latestContest = contest
}

/** Tests only. */
export function resetCache(): void {
  store.clear()
  latestContest = null
}
