export const jparse = <T,>(s: string | null | undefined, d: T): T => {
  if (!s) return d
  try {
    return JSON.parse(s) as T
  } catch {
    return d
  }
}

export function thb(v: number | null | undefined, lang = 'th'): string {
  if (v === null || v === undefined) return '—'
  const a = Math.abs(v)
  const unit = lang === 'th' ? ['ลบ.', 'ล.', 'พ.'] : ['M', 'M', 'K']
  if (a >= 1e6) return `${(v / 1e6).toFixed(a >= 1e8 ? 0 : 2)} ${unit[0]}`
  if (a >= 1e3) return `${(v / 1e3).toFixed(0)} ${unit[2]}`
  return v.toFixed(0)
}

export const num = (v: number | null | undefined, d = 0) =>
  v === null || v === undefined ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })

export const pct = (v: number | null | undefined, d = 0) =>
  v === null || v === undefined ? '—' : `${(v * 100).toFixed(d)}%`

export function time(iso: string | null | undefined): string {
  if (!iso) return '—'
  const m = /T(\d{2}:\d{2})/.exec(iso)
  return m ? m[1] : iso.slice(0, 10)
}

export function dayMonth(iso: string | null | undefined, lang = 'th'): string {
  if (!iso) return '—'
  const d = new Date(iso.slice(0, 10))
  if (Number.isNaN(+d)) return iso.slice(0, 10)
  return d.toLocaleDateString(lang === 'th' ? 'th-TH' : 'en-GB', { day: 'numeric', month: 'short' })
}

export function fullDate(iso: string | null | undefined, lang = 'th'): string {
  if (!iso) return '—'
  const d = new Date(iso.slice(0, 10))
  if (Number.isNaN(+d)) return iso.slice(0, 10)
  return d.toLocaleDateString(lang === 'th' ? 'th-TH' : 'en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

export const LEVEL_COLOR: Record<string, string> = {
  L1_HOLD: 'var(--s1)',
  L2_WATCH: 'var(--s2)',
  L3_SECTOR: 'var(--s3)',
  L4_RELATED: 'var(--s4)',
  L5_ASSET: 'var(--s5)',
  L6_MACRO: 'var(--s6)',
}

export const LEVEL_ORDER = ['L1_HOLD', 'L2_WATCH', 'L3_SECTOR', 'L4_RELATED', 'L5_ASSET', 'L6_MACRO']

export const URGENCY_STATUS: Record<string, string> = {
  now: 'var(--critical)',
  this_week: 'var(--warning)',
  low: 'var(--muted)',
}
