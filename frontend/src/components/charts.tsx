import { useState } from 'react'
import type { ReactNode } from 'react'
import { LEVEL_COLOR, LEVEL_ORDER, num } from '../lib/format'
import { useI18n } from '../lib/i18n'

function Tip({ x, children }: { x: number; children: ReactNode }) {
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute bottom-full z-20 mb-2 -translate-x-1/2 rounded-in border border-rule bg-surface px-2 py-1 text-micro whitespace-nowrap text-ink shadow-[0_1px_2px_rgba(0,0,0,.06),0_4px_10px_-6px_rgba(0,0,0,.12)]"
      style={{ left: x }}
    >
      {children}
    </div>
  )
}

/* --------------------------------------------------------------------------
   สัดส่วนระดับการจับคู่ — แถบเดียว ช่องว่าง 2px คั่นแต่ละช่วง
   สีผูกกับ "ระดับ" ไม่ใช่อันดับ กรองแล้วสีไม่สลับ
-------------------------------------------------------------------------- */
export function LevelStack({ items }: { items: { level: string; n: number }[] }) {
  const { t } = useI18n()
  const [tip, setTip] = useState<{ x: number; body: ReactNode } | null>(null)
  const rows = LEVEL_ORDER.map((l) => ({ level: l, n: items.find((i) => i.level === l)?.n ?? 0 })).filter(
    (r) => r.n > 0,
  )
  const total = rows.reduce((s, r) => s + r.n, 0)
  if (!total) return null

  return (
    <div>
      <div className="relative flex h-1.5 w-full items-stretch gap-[2px]">
        {rows.map((r) => (
          <div
            key={r.level}
            className="min-w-[4px] rounded-[1px]"
            style={{ width: `${(r.n / total) * 100}%`, background: LEVEL_COLOR[r.level] }}
            onMouseEnter={(e) => {
              const b = e.currentTarget.getBoundingClientRect()
              const p = e.currentTarget.parentElement!.getBoundingClientRect()
              setTip({
                x: b.left - p.left + b.width / 2,
                body: `${t(`lvl.${r.level}`)} · ${num(r.n)} · ${((r.n / total) * 100).toFixed(0)}%`,
              })
            }}
            onMouseLeave={() => setTip(null)}
          />
        ))}
        {tip ? <Tip x={tip.x}>{tip.body}</Tip> : null}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {rows.map((r) => (
          <li key={r.level} className="flex items-center gap-1.5 text-small text-ink-2">
            {/* deslop-ignore-next-line 19 — จุดสีขนาด 8px แทนระดับการจับคู่ ไม่มีวงเรือง ไม่กะพริบ (tell 16) */}
            <span className="size-2 rounded-full" style={{ background: LEVEL_COLOR[r.level] }} />
            {t(`lvl.${r.level}`)}
            <span className="tnum font-medium text-ink">{num(r.n)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* --------------------------------------------------------------------------
   แท่งนอน — เทียบขนาด สีเดียว ตัวเลขกำกับปลาย
-------------------------------------------------------------------------- */
export function HBars({
  items,
  max,
  format = (v: number) => num(v),
  color = 'var(--accent)',
  onPick,
  activeKey,
}: {
  items: { key: string; label: ReactNode; value: number; note?: ReactNode }[]
  max?: number
  format?: (v: number) => string
  color?: string
  onPick?: (key: string) => void
  activeKey?: string
}) {
  const top = max ?? Math.max(1, ...items.map((i) => i.value))
  return (
    <ul>
      {items.map((it) => {
        const active = activeKey === it.key
        const Tag = onPick ? 'button' : 'div'
        return (
          <li key={it.key} className="border-b border-rule last:border-0">
            <Tag
              {...(onPick ? { type: 'button' as const, onClick: () => onPick(it.key) } : {})}
              className={`tap grid w-full grid-cols-[minmax(80px,30%)_1fr_auto] items-center gap-3 py-1.5 text-left ${
                onPick ? 'hover:bg-wash' : ''
              } ${active ? 'bg-wash' : ''}`}
            >
              <span className="min-w-0 pl-1">
                <span className="block truncate text-small text-ink-2">{it.label}</span>
                {it.note ? <span className="block truncate text-micro text-ink-3">{it.note}</span> : null}
              </span>
              <span className="flex h-1.5 items-center">
                <span
                  className="h-1.5 min-w-[2px] rounded-[1px]"
                  style={{ width: `${Math.max(1, (it.value / top) * 100)}%`, background: color }}
                />
              </span>
              <span className="tnum pr-1 text-small font-medium text-ink">{format(it.value)}</span>
            </Tag>
          </li>
        )
      })}
    </ul>
  )
}

/* --------------------------------------------------------------------------
   ปริมาณข่าวรายวัน
-------------------------------------------------------------------------- */
export function DayColumns({
  data,
  active,
  onPick,
}: {
  data: { d: string; articles: number; matches: number }[]
  active?: string
  onPick?: (d: string) => void
}) {
  const { t, lang } = useI18n()
  const [tip, setTip] = useState<{ x: number; body: ReactNode } | null>(null)
  const top = Math.max(1, ...data.map((x) => x.articles))
  return (
    <div className="relative flex h-12 items-end gap-[2px]">
      {data.map((x) => {
        const on = active === x.d
        return (
          <button
            key={x.d}
            type="button"
            onClick={() => onPick?.(x.d)}
            aria-label={`${x.d}: ${x.articles}`}
            className="flex h-full flex-1 items-end"
            onMouseEnter={(e) => {
              const b = e.currentTarget.getBoundingClientRect()
              const p = e.currentTarget.parentElement!.getBoundingClientRect()
              setTip({
                x: b.left - p.left + b.width / 2,
                body: (
                  <span className="tnum">
                    {new Date(x.d).toLocaleDateString(lang === 'th' ? 'th-TH' : 'en-GB')} ·{' '}
                    {num(x.articles)} {t('k.articles')} · {num(x.matches)} {t('k.matches')}
                  </span>
                ),
              })
            }}
            onMouseLeave={() => setTip(null)}
          >
            <span
              className="tap w-full rounded-[1px]"
              style={{
                height: `${Math.max(5, (x.articles / top) * 100)}%`,
                background: on ? 'var(--accent)' : 'var(--rule-strong)',
              }}
            />
          </button>
        )
      })}
      {tip ? <Tip x={tip.x}>{tip.body}</Tip> : null}
    </div>
  )
}

/** สัดส่วน 0..1 — บอกความครอบคลุม */
export function Meter({ value, label }: { value: number; label?: ReactNode }) {
  const v = Math.max(0, Math.min(1, value))
  const tone = v >= 0.66 ? 'var(--good)' : v >= 0.33 ? 'var(--warning)' : 'var(--critical)'
  return (
    <span className="flex items-center gap-2">
      <span className="h-1.5 w-16 bg-wash">
        <span className="block h-full" style={{ width: `${v * 100}%`, background: tone }} />
      </span>
      <span className="tnum text-micro text-ink-2">{label ?? `${(v * 100).toFixed(0)}%`}</span>
    </span>
  )
}
