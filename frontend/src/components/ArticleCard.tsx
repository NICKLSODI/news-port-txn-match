import { Link, useLocation } from 'react-router-dom'
import type { Article } from '../lib/api'
import { jparse, num, time } from '../lib/format'
import { useI18n } from '../lib/i18n'
import { AiDirection, AiRead, Code, Urgency } from './ui'

/**
 * รายการข่าวหนึ่งชิ้น
 *
 * สิ่งที่ RM ต้องเห็นก่อนคือ "ข่าวนี้ควรโทรหากี่คน" กับ "ข่าวเรื่องอะไร"
 * ที่เหลือ (หมวด เวลา ticker) เป็นข้อมูลรอง จึงเล็กและจาง
 * ไม่ใส่ป้ายความสำคัญ ป้ายโหมด ป้ายหมวดเป็นชิป — เคยมีหกป้ายต่อการ์ด อ่านไม่ออกว่าอะไรสำคัญ
 */
export default function ArticleCard({ a }: { a: Article }) {
  const { t, lang } = useI18n()
  const loc = useLocation()
  const entities = jparse<string[]>(a.entity, [])
  const sectors = jparse<string[]>(a.sector, [])
  const macro = jparse<{ topic: string; keyword: string }[]>(a.macro_topic, [])
  const weak = a.auto_grade === 'weak'
  const tags = [...entities.slice(0, 4), ...sectors.slice(0, 2), ...macro.slice(0, 2).map((m) => m.topic)]

  return (
    <Link
      to={`/news/${encodeURIComponent(a.article_id)}`}
      // จำว่ากดมาจากหน้าไหน ปุ่มย้อนกลับบนหน้าข่าวจะพากลับที่เดิม ไม่เด้งไปหน้าข่าวทั้งหมด
      state={{ from: `${loc.pathname}${loc.search}` }}
      className="tap group block border-b border-rule py-3 hover:bg-wash"
    >
      <div className="flex items-baseline gap-2 text-micro text-ink-3">
        <span className="tnum">{time(a.trigger_at)}</span>
        <span className="truncate">{a.subcategory_name || a.subcategory}</span>
        {a.segment_no ? <span className="tnum">#{a.segment_no}</span> : null}
        <span className="ml-auto flex shrink-0 items-center gap-2">
          <AiRead at={a.ai_at} title={lang === 'th' ? 'AI อ่านแล้ว' : 'AI read'} />
          <AiDirection
            direction={a.ai_direction}
            title={(lang === 'th' ? a.ai_reason_th : a.ai_reason) || undefined}
          />
          <Urgency urgency={a.urgency} />
        </span>
      </div>

      <div className="mt-1 flex items-start gap-4">
        <h3 className="min-w-0 flex-1 text-body leading-snug font-medium text-ink group-hover:underline">
          {a.title}
        </h3>
        <span className="shrink-0 text-right">
          {a.n_matches > 0 ? (
            <>
              <span className="tnum block text-h1 leading-none font-semibold text-ink">
                {num(a.n_matches)}
              </span>
              <span className="text-micro text-ink-3">{lang === 'th' ? 'คน' : 'people'}</span>
            </>
          ) : (
            <span className="text-micro text-ink-3">{lang === 'th' ? 'ไม่มีใคร' : 'nobody'}</span>
          )}
          {weak ? (
            <span className="mt-0.5 block text-micro font-medium" style={{ color: 'var(--serious)' }}>
              {t('g.weak')}
            </span>
          ) : null}
        </span>
      </div>

      {tags.length ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {tags.map((x) => (
            <Code key={x}>{x}</Code>
          ))}
          {entities.length > 4 ? (
            <span className="text-micro text-ink-3">+{entities.length - 4}</span>
          ) : null}
        </div>
      ) : null}
    </Link>
  )
}
