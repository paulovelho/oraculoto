import { computed, readonly, ref } from 'vue'
import { getHealth, toApiError, type ApiError, type GameHealth, type Health } from '@/api'
import { setLatestContest } from '@/lib/cache'

// One /health per page load, shared by everything that needs it. The session cache is keyed
// on the latest contest it reports (docs/web.md §4): a retry that sees a newer contest clears it.
const health = ref<Health | null>(null)
const error = ref<ApiError | null>(null)
const loading = ref(false)
let pending: Promise<void> | null = null

export function loadHealth(): Promise<void> {
  pending ??= (async () => {
    loading.value = true
    error.value = null
    try {
      health.value = await getHealth()
      setLatestContest(latestContestOf(health.value))
    } catch (e) {
      error.value = toApiError(e)
    } finally {
      loading.value = false
      pending = null
    }
  })()
  return pending
}

export function useHealth() {
  return {
    health: readonly(health),
    latestContest: computed(() => latestContestOf(health.value)),
    error: readonly(error),
    loading: readonly(loading),
    reload: loadHealth,
  }
}

/** v1 has one game; the badge, the cache key and the "next" links all read this. */
function latestContestOf(h: { games: readonly GameHealth[] } | null): number | null {
  return h?.games.find((g) => g.game === 'megasena')?.latest_contest ?? null
}
