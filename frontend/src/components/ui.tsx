import type { CSSProperties, ReactNode } from 'react'
import { useI18n } from '../lib/i18n'
import { LEVEL_COLOR } from '../lib/format'

/* --------------------------------------------------------------------------
   หนึ่ง region หนึ่งพื้นผิว — ข้างในแบ่งด้วยระยะกับเส้น ไม่ใช่กล่องซ้อนกล่อง
-------------------------------------------------------------------------- */
export function Panel({
  children,
  className = '',
  pad = 'p-4 sm:p-5',
}: {
  children: ReactNode
  className?: string
  pad?: string | false
}) {
  return (
    <section
      className={`rounded-out border border-rule bg-surface ${pad || ''} ${className}`}
    >
      {children}
    </section>
  )
}

/** หัวข้อกลุ่ม — ชิดกับเนื้อหาของตัวเอง (8px) ห่างจากกลุ่มอื่น (32px+) */
export function Head({
  children,
  note,
  right,
  className = '',
}: {
  children: ReactNode
  note?: ReactNode
  right?: ReactNode
  className?: string
}) {
  return (
    <div className={`mb-2 flex flex-wrap items-end justify-between gap-x-4 gap-y-1 ${className}`}>
      <div className="min-w-0">
        <h2 className="text-h2 font-semibold text-ink">{children}</h2>
        {note ? <p className="mt-0.5 max-w-[62ch] text-small text-ink-2">{note}</p> : null}
      </div>
      {right}
    </div>
  )
}

/** ตัวเลขเดียวที่สำคัญที่สุดของหน้า — ใหญ่พอที่จะบอกว่ามันสำคัญ */
export function Figure({
  value,
  label,
  sub,
  tone,
}: {
  value: ReactNode
  label: ReactNode
  sub?: ReactNode
  tone?: 'warning' | 'critical'
}) {
  return (
    <div>
      <div
        className="tnum text-display font-semibold text-ink"
        style={tone ? { color: `var(--${tone})` } : undefined}
      >
        {value}
      </div>
      <div className="mt-1 text-body text-ink">{label}</div>
      {sub ? <div className="mt-0.5 text-small text-ink-3">{sub}</div> : null}
    </div>
  )
}

/** ตัวเลขประกอบ — วางเรียงกันในบรรทัดเดียว ไม่ต้องมีกล่องของตัวเอง */
export function Stat({ label, value, sub }: { label: ReactNode; value: ReactNode; sub?: ReactNode }) {
  return (
    <div>
      <div className="tnum text-h1 font-semibold text-ink">{value}</div>
      <div className="mt-0.5 text-small text-ink-2">{label}</div>
      {sub ? <div className="text-micro text-ink-3">{sub}</div> : null}
    </div>
  )
}

/* --------------------------------------------------------------------------
   ป้าย — ใช้เฉพาะที่มีสถานะจริง ไม่ใช่เครื่องประดับ
-------------------------------------------------------------------------- */

export function Tag({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span title={title} className="text-micro text-ink-3">
      {children}
    </span>
  )
}

/** รหัสสินทรัพย์ — ตัวเลขเรียงตรง อ่านเทียบกันได้ */
export function Code({ children }: { children: ReactNode }) {
  return (
    <span className="tnum rounded-in bg-wash px-1 py-px text-micro font-medium text-ink-2">
      {children}
    </span>
  )
}

export function LevelDot({ level }: { level: string }) {
  // deslop-ignore-next-line 19 — จุด 8px แบนล้วน สีเข้ารหัสระดับ ไม่ใช่การตกแต่ง
  return <span className="inline-block size-2 rounded-full" style={{ background: LEVEL_COLOR[level] }} />
}

export function LevelBadge({ level }: { level: string }) {
  const { t } = useI18n()
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-small text-ink-2">
      <LevelDot level={level} />
      {t(`lvl.${level}`)}
    </span>
  )
}

/** ความเร่งด่วน — แสดงเฉพาะตอนเร่งจริง ที่เหลือเงียบไว้ */
export function Urgency({ urgency }: { urgency: string }) {
  const { t } = useI18n()
  if (urgency !== 'now') return null
  return (
    <span className="text-micro font-semibold" style={{ color: 'var(--critical)' }}>
      {t('u.now')}
    </span>
  )
}

/** จุดบอกว่า AI อ่านชิ้นนี้แล้ว — ไม่บอกผล แค่บอกสถานะอ่าน เงียบถ้ายังไม่อ่าน */
export function AiRead({ at, title }: { at?: string | null; title?: string }) {
  if (!at) return null
  return (
    <span className="text-micro text-ink-3" title={title}>
      ✨
    </span>
  )
}

/** สัญลักษณ์ผล AI วิเคราะห์ทิศทาง — โชว์เฉพาะขึ้น/ลงชัดเจน ที่เหลือ (mixed/unknown) เงียบไว้ตามหลักการเดียวกับ Urgency */
export function AiDirection({ direction, title }: { direction?: string | null; title?: string }) {
  if (direction !== 'up' && direction !== 'down') return null
  return (
    <span
      className="text-micro font-semibold"
      style={{ color: direction === 'up' ? 'var(--good)' : 'var(--critical)' }}
      title={title}
    >
      {direction === 'up' ? '▲' : '▼'}
    </span>
  )
}

/**
 * เกรดคุณภาพหลักฐาน (GAP-21) — ไม่ใช่สถานะรออนุมัติ ทุกบทความจับคู่ไปแล้ว
 * ใช้สีเฉพาะตอนหลักฐานบาง ที่เหลืออ่านเป็นข้อความเงียบ ๆ
 */
export function Grade({ grade }: { grade: string }) {
  const { t } = useI18n()
  const weak = grade === 'weak'
  return (
    <span
      className={`text-small ${weak ? 'font-semibold' : 'font-medium text-ink-2'}`}
      style={weak ? { color: 'var(--serious)' } : undefined}
      title={t(`g.${grade}.note`, '')}
    >
      {t(`g.${grade}`, grade)}
    </span>
  )
}

/** ป้ายเตือนชนิดสินทรัพย์ — R3.27 / R4.12 / R4.22 / R4.28 / R4.31 */
export function InstrumentLabel({ label }: { label?: string | null }) {
  const { t } = useI18n()
  if (!label) return null
  return (
    <span className="text-micro font-medium" style={{ color: 'var(--serious)' }}>
      {t(`lbl.${label}`, label)}
    </span>
  )
}

/* --------------------------------------------------------------------------
   ตัวกรอง — segmented control ไม่ใช่ปุ่มกลมลอย
-------------------------------------------------------------------------- */

/**
 * กล่องกับเส้นขอบอยู่บนกล่องเดียวกัน เส้นจึงวิ่งรอบมุมโค้งได้ (tell 22)
 * ตัวคั่นภายในเป็น border-l ของลูก ไม่ใช่พื้นหลังสีเทาที่จะโผล่ตอนขึ้นบรรทัดใหม่
 */
export function Segmented({ children }: { children: ReactNode }) {
  return (
    <div className="inline-flex flex-wrap items-stretch overflow-hidden rounded-out border border-rule bg-surface">
      {children}
    </div>
  )
}

export function Seg({
  active,
  onClick,
  children,
  count,
}: {
  active?: boolean
  onClick?: () => void
  children: ReactNode
  count?: number
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`tap inline-flex items-center gap-1.5 border-l border-rule px-2.5 py-1.5 text-small font-medium first:border-l-0 ${
        active ? 'bg-ink text-paper' : 'text-ink-2 hover:bg-wash hover:text-ink'
      }`}
    >
      {children}
      {count !== undefined ? <span className="tnum opacity-60">{count}</span> : null}
    </button>
  )
}

export function Button({
  children,
  onClick,
  variant = 'quiet',
  disabled,
  title,
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'quiet'
  disabled?: boolean
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`tap rounded-out px-3 py-1.5 text-small font-medium disabled:opacity-40 ${
        variant === 'primary'
          ? 'bg-accent text-accent-ink hover:brightness-110'
          : 'border border-rule bg-surface text-ink-2 hover:bg-wash hover:text-ink'
      }`}
    >
      {children}
    </button>
  )
}

/* -------------------------------------------------------------------------- */

/** วงหมุน — งานที่กินเวลาหลายวินาทีต้องมีอะไรขยับ ไม่ใช่ปุ่มค้างเงียบ */
export function Spinner({ className = 'size-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`mp-spin ${className}`} fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.2" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

export function Empty({ children }: { children?: ReactNode }) {
  const { t } = useI18n()
  return <div className="py-14 text-center text-body text-ink-3">{children ?? t('msg.empty')}</div>
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-px" aria-busy>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-9 bg-wash" style={{ opacity: 1 - i * 0.12 }} />
      ))}
    </div>
  )
}

/* --------------------------------------------------------------------------
   ตาราง — เส้นวิ่งสุดขอบ ไม่มีมุมกลม (มุมกลมกับเส้นคั่นอยู่ด้วยกันไม่ได้)
-------------------------------------------------------------------------- */

export function Th({
  children,
  right,
  className = '',
}: {
  children?: ReactNode
  right?: boolean
  className?: string
}) {
  return (
    <th
      scope="col"
      className={`sticky top-0 z-1 border-b border-rule bg-surface px-3 pb-1.5 text-micro font-medium whitespace-nowrap text-ink-3 ${
        right ? 'text-right' : 'text-left'
      } ${className}`}
    >
      {children}
    </th>
  )
}

export function Td({
  children,
  right,
  className = '',
  style,
}: {
  children: ReactNode
  right?: boolean
  className?: string
  style?: CSSProperties
}) {
  return (
    <td
      style={style}
      className={`border-b border-rule px-3 py-2 align-middle text-small ${
        right ? 'tnum text-right' : ''
      } ${className}`}
    >
      {children}
    </td>
  )
}

export function Scroll({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`overflow-x-auto ${className}`}>{children}</div>
}

export function Row({ k, v }: { k: ReactNode; v: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-rule py-1.5 last:border-0">
      <dt className="text-small text-ink-2">{k}</dt>
      <dd className="tnum text-small font-medium text-ink">{v}</dd>
    </div>
  )
}
