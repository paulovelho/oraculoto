import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, buildUrl, request } from './client'

function respond(status: number, body: string) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(body, { status })))
}

afterEach(() => vi.unstubAllGlobals())

describe('buildUrl', () => {
  it('prefixes the API base and drops empty params', () => {
    expect(buildUrl('/health')).toBe('/api/v1/health')
    expect(buildUrl('/x', { a: 1, b: null, c: undefined, d: false })).toBe('/api/v1/x?a=1&d=false')
  })
})

describe('request', () => {
  it('unwraps data on success', async () => {
    respond(200, JSON.stringify({ success: true, data: { contest: 3072 } }))
    await expect(request('/x')).resolves.toEqual({ contest: 3072 })
  })

  it('throws the envelope error with its status and code', async () => {
    respond(404, JSON.stringify({ success: false, error: { code: 'not_found', message: 'no such contest' } }))
    const err = await request('/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 404, code: 'not_found', message: 'no such contest' })
  })

  it('turns a non-JSON body into bad_response', async () => {
    respond(500, '<html>Internal Server Error</html>')
    await expect(request('/x')).rejects.toMatchObject({ status: 500, code: 'bad_response' })
  })

  it('turns a fetch failure into network', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))))
    await expect(request('/x')).rejects.toMatchObject({ status: 0, code: 'network' })
  })
})
