import { useBriefing } from '../lib/api'
import type { Signal } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Code, Head } from './ui'

const TIER_KEY: Record<number, string> = { 1: 'b.tier1', 2: 'b.tier2', 3: 'b.tier3' }

const ARROW: Record<string, string> = { up: '↑', down: '↓', flat: '→' }

function dirColor(d: string): string | undefined {
  if (d === 'up') return 'var(--pos)'
  if (d === 'down') return 'var(--critical)'
  return undefined
}

/**
 * GAP-22 — ทิศทางข่าวและประเด็นที่ควรคุย
 *
 * STEP7 ข้อ 6 ห้ามบอกว่าข่าวดีหรือร้าย เจ้าของงานสั่งให้ใส่กลับ
 * จอนี้จึงไม่แสดง "ความรู้สึก" แต่แสดงสามอย่างที่ต่างกันชัดเจน และบอกที่มาทุกบรรทัด
 *   ชั้น 1 คำแนะนำที่ INVX ประกาศเอง       — น้ำหนักสูงสุด
 *   ชั้น 2 ผลเทียบกับที่คาด                — ข้อเท็จจริง
 *   ชั้น 3 โทนของพาดหัว                    — ติดป้ายว่าเป็นการอ่านถ้อยคำ พร้อมวลีที่ทำให้ติด
 * ถ้าบทความพูดสองทาง จะไม่ยุบเป็นค่าเดียว
 */
export default function Briefing({ articleId }: { articleId: string }) {
  const { t, isTh } = useI18n()
  const { data } = useBriefing(articleId)
  if (!data) return null

  const byTier = [1, 2, 3]
    .map((tier) => ({ tier, items: data.signals.filter((s) => s.tier === tier) }))
    .filter((g) => g.items.length)

  const points = data.talking_points.filter((p) => p.kind !== 'headline')
  const overallColor = dirColor(data.overall)
  // AI-02 — "ไม่ตีความ" ต้องบอกได้ว่าเพราะอะไร เหมือนตอนที่ตีความได้
  // ประโยคไทยมาจาก backend ตรง ๆ (มีรายชื่อตัวย่อที่ถูกทิ้งต่อท้ายด้วย) ฝั่งอังกฤษแปลจากรหัส
  const noCall =
    data.overall === 'unknown' && data.no_call_th
      ? isTh
        ? data.no_call_th
        : t(data.no_call_code ? `ai.reason.${data.no_call_code}` : 'ai.notRead', data.no_call_th)
      : null

  return (
    <section className="mt-10">
      <Head>{t('b.title')}</Head>

      <div className="border-y border-rule py-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span
            className="text-h2 font-semibold"
            style={overallColor ? { color: overallColor } : undefined}
          >
            {ARROW[data.overall] ?? ''} {t(`ov.${data.overall}`, data.overall)}
          </span>
          {data.two_sided.map((x) => (
            <span key={x.topic} className="text-small text-ink-2">
              {x.topic} · {x.affects.slice(0, 3).join(', ')}
            </span>
          ))}
        </div>
        {noCall ? <p className="mt-1 text-small text-ink-3">{noCall}</p> : null}
      </div>

      {/* ความเห็นของนักวิเคราะห์บ้านเราเอง — วางก่อนสัญญาณและประเด็นที่ควรคุย
          เพราะอีกสองอย่างนั้นระบบอ่านออกมาจากถ้อยคำ ส่วนอันนี้คนของเราเขียนเอง
          ข่าวหาอ่านที่ไหนก็ได้ แต่มุมมองของบ้านเราหาที่อื่นไม่ได้ */}
      {data.invx_view ? (
        <div
          className="mt-6 rounded-out p-4"
          style={{ background: 'var(--wash)', borderLeft: '3px solid var(--accent)' }}
        >
          <p className="text-micro font-semibold" style={{ color: 'var(--accent)' }}>
            {isTh ? 'มุมมองของ InnovestX' : 'InnovestX view'}
          </p>
          {/* ต้นฉบับเขียนเป็นข้อ ๆ (ภาพรวม / คุณภาพงบ / เทียบคู่แข่ง / ข้อควรระวัง)
              แสดงตามที่นักวิเคราะห์แบ่งไว้ ไม่ยุบเป็นย่อหน้าเดียวจนอ่านไม่ออกว่ามีกี่ประเด็น */}
          {data.invx_points.length > 1 ? (
            <ul className="mt-1.5 space-y-1.5">
              {data.invx_points.map((p, i) => (
                <li key={i} className="flex gap-2 text-body leading-relaxed text-ink">
                  <span style={{ color: 'var(--accent)' }}>•</span>
                  <span className="min-w-0">{p}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1.5 text-body leading-relaxed whitespace-pre-line text-ink">
              {data.invx_view}
            </p>
          )}
        </div>
      ) : null}

      <div className="mt-6 grid gap-x-12 gap-y-8 lg:grid-cols-2">
        {byTier.length ? (
          <div>
            <h3 className="mb-2 text-small font-semibold text-ink">{t('b.signals')}</h3>
            {byTier.map((g) => (
              <div key={g.tier} className="mb-4 last:mb-0">
                <p className="mb-1 text-micro text-ink-3">{t(TIER_KEY[g.tier])}</p>
                <ul className="border-t border-rule">
                  {g.items.map((s, i) => (
                    <SignalRow key={i} s={s} />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : null}

        <div className="min-w-0">
          <h3 className="mb-2 text-small font-semibold text-ink">{t('b.points')}</h3>
          <ul className="border-t border-rule">
            {points.map((p, i) => (
              <li key={i} className="border-b border-rule py-2">
                <p
                  className="text-small leading-relaxed"
                  style={{ color: p.kind === 'disclaimer' ? 'var(--ink-3)' : 'var(--ink-2)' }}
                >
                  {isTh ? p.th : p.en}
                </p>
                {(isTh ? p.source_th : p.source_en) ? (
                  <p className="mt-0.5 text-micro text-ink-3">{isTh ? p.source_th : p.source_en}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

function SignalRow({ s }: { s: Signal }) {
  const { isTh } = useI18n()
  const color = dirColor(s.direction)
  return (
    <li className="flex items-start gap-2 border-b border-rule py-2">
      <span
        className="mt-px w-3 shrink-0 text-center text-small font-semibold"
        style={color ? { color } : { color: 'var(--ink-3)' }}
      >
        {ARROW[s.direction] ?? '·'}
      </span>
      <span className="min-w-0">
        <span className="block text-small text-ink-2">{isTh ? s.th : s.en}</span>
        {(isTh ? s.source_th : s.source_en) || s.phrase ? (
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-micro text-ink-3">{isTh ? s.source_th : s.source_en}</span>
            {s.phrase ? <Code>{s.phrase}</Code> : null}
          </span>
        ) : null}
      </span>
    </li>
  )
}
