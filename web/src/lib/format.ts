// docs/web.md §5: strings in, strings out. No parseFloat for money, no new Date() for dates.

const THOUSANDS = /\B(?=(\d{3})+(?!\d))/g

/** "38295.72" → "R$ 38.295,72". Returns "—" for null or anything that isn't a plain decimal. */
export function formatMoney(value: string | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim())
  if (!match) return '—'
  const [, sign, int = '0', frac = ''] = match
  const cents = (frac + '00').slice(0, 2)
  const grouped = int.replace(/^0+(?=\d)/, '').replace(THOUSANDS, '.')
  return `${sign ? '-' : ''}R$ ${grouped},${cents}`
}

/** "2026-10-20" → "20/10/2026". Returns "—" for null or anything that isn't YYYY-MM-DD. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return '—'
  const [, y, m, d] = match
  return `${d}/${m}/${y}`
}

/** 50063860 → "50.063.860". For integers only. */
export function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isInteger(value)) return '—'
  const sign = value < 0 ? '-' : ''
  return sign + String(Math.abs(value)).replace(THOUSANDS, '.')
}

/** Ball numbers are always shown with two digits, like on the ticket. */
export function formatBall(n: number): string {
  return String(n).padStart(2, '0')
}

/** 307.2 → "307,2", 26.03 → "26,03", 9 → "9". For the API's rounded floats (expected counts). */
export function formatDecimal(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const [int = '0', frac = ''] = Math.abs(value).toFixed(digits).split('.')
  const trimmed = frac.replace(/0+$/, '')
  const sign = value < 0 && (/[1-9]/.test(int) || trimmed) ? '-' : ''
  return sign + int.replace(THOUSANDS, '.') + (trimmed ? `,${trimmed}` : '')
}
