import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import type { Article } from '../lib/api'
import { num, time } from '../lib/format'
import { useI18n } from '../lib/i18n'

/**
 * สรุปเช้า/เย็นหนึ่งฉบับ = การ์ดใบเดียว
 *
 * spec บังคับให้ซอย Brief เป็นข้อย่อยแล้วจับคู่ที่ระดับข้อ (R3.1-R3.5) — ยังทำอยู่
 * แต่ "ซอยเพื่อจับคู่" กับ "ซอยเพื่อแสดง" ไม่ใช่เรื่องเดียวกัน ของจริงในคลังคือ
 * ข้อย่อยของ brief 213 ข้อ จับคู่ได้แค่ 43 ข้อ (20%) อีก 80% กินที่หน้าวันนี้
 * วันละ 6-13 การ์ดโดยไม่ส่งใครเลย ดันข่าวรายตัวที่มีคนรอโทรตกลงไปข้างล่าง
 *
 * จึงยุบเป็นใบเดียว เรียงข้อที่มีคนขึ้นก่อน ข้อที่ไม่มีใครพับไว้ให้กดดู
 * ไม่ทิ้งข้อ macro เพราะ RM ยังต้องรู้ว่าน้ำมันร่วงหรือเยนถูกแทรกแซง
 */
export default function BriefGroup({ items }: { items: Article[] }) {
  const { t, isTh } = useI18n()
  const loc = useLocation()
  const [open, setOpen] = useState(false)

  const head = items[0]
  const total = items.reduce((s, a) => s + (a.n_matches || 0), 0)
  const withMatch = items.filter((a) => (a.n_matches || 0) > 0).sort((x, y) => y.n_matches - x.n_matches)
  const without = items.filter((a) => !a.n_matches)

  const row = (a: Article) => (
    <li key={a.article_id} className="border-b border-rule last:border-0">
      <Link
        to={`/news/${encodeURIComponent(a.article_id)}`}
        state={{ from: `${loc.pathname}${loc.search}` }}
        className="tap flex items-start gap-3 py-2 hover:bg-wash"
      >
        <span className="tnum mt-px w-4 shrink-0 text-micro text-ink-3">{a.segment_no}</span>
        <span className="min-w-0 flex-1 text-small leading-snug text-ink">{a.title}</span>
        <span className="shrink-0 text-right">
          {a.n_matches ? (
            <>
              <span className="tnum text-body font-semibold text-ink">{num(a.n_matches)}</span>
              <span className="ml-1 text-micro text-ink-3">{isTh ? 'คน' : ''}</span>
            </>
          ) : (
            <span className="text-micro text-ink-3">{isTh ? 'ไม่มีใคร' : 'none'}</span>
          )}
        </span>
      </Link>
    </li>
  )

  return (
    <section className="border-b border-rule py-3">
      <div className="flex items-baseline gap-2">
        <span className="tnum text-micro text-ink-3">{time(head.trigger_at)}</span>
        <h3 className="min-w-0 flex-1 truncate text-body font-semibold text-ink">
          {head.subcategory_name || head.subcategory}
          <span className="ml-1.5 text-micro font-normal text-ink-3">
            {items.length} {isTh ? 'ข้อ' : 'items'}
          </span>
        </h3>
        <span className="shrink-0 text-right">
          <span className="tnum text-body font-semibold text-ink">{num(total)}</span>
          <span className="ml-1 text-micro text-ink-3">{t('k.matches')}</span>
        </span>
      </div>

      <ul className="mt-1.5 border-t border-rule">{withMatch.map(row)}</ul>

      {without.length ? (
        <>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="tap mt-1.5 text-micro text-ink-3 hover:text-ink"
          >
            {open ? '−' : '+'}{' '}
            {isTh
              ? `ไม่มีใครเข้าเกณฑ์ ${without.length} ข้อ`
              : `${without.length} item${without.length > 1 ? 's' : ''} matched nobody`}
          </button>
          {open ? <ul className="mt-1 border-t border-rule">{without.map(row)}</ul> : null}
        </>
      ) : null}
    </section>
  )
}
