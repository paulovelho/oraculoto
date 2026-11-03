import { ref, shallowRef } from 'vue'
import { toApiError, type ApiError } from '@/api'

/**
 * One async data block: data, error, loading, and a `run` that can be called again (on retry, or
 * when a route param changes). Only the latest run may write, so clicking "previous" three times
 * quickly can't leave the page showing the first answer that came back.
 */
export function useLoad<T>(load: () => Promise<T>) {
  const data = shallowRef<T | null>(null)
  const error = shallowRef<ApiError | null>(null)
  const loading = ref(false)
  let seq = 0

  async function run(): Promise<void> {
    const id = ++seq
    data.value = null
    error.value = null
    loading.value = true
    try {
      const value = await load()
      if (id === seq) data.value = value
    } catch (e) {
      if (id === seq) error.value = toApiError(e)
    } finally {
      if (id === seq) loading.value = false
    }
  }

  return { data, error, loading, run }
}
