import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useDates, useRmEntities, useRmNews, useRmQueue, useRms } from '../lib/api'
import type { RmEntityRow, RmNewsRow, QueueRow } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { num, thb, time } from '../lib/format'
import { Empty, Figure, Loading, Scroll, Seg, Segmented, Td, Th } from '../components/ui'

/**
 * หน้านี้ตอบสามคำถามของ RM ตอนเช้า ตามลำดับที่เขาถามจริง
 *
 *   1. วันนี้ข่าวไปแตะเงินของลูกค้าฉันเท่าไร        -> ตัวเลขบนหัว
 *   2. ควรโทรหาใครก่อน                            -> มุม "ตามลูกค้า" เรียงตามเงิน
 *   3. ข่าวชิ้นนี้ไปโดนใคร                          -> มุม "ตามข่าว" เรียงตามเงิน
 *   4. ข่าววันนี้ทำให้ตัวไหนต้องโทรคุย                -> มุม "ตามหุ้น" เรียงตามเงิน
 *
 * ตัวจัดลำดับหลักคือ "เงินที่ข่าวแตะ" = มูลค่าที่ลูกค้าถือในตัวที่ข่าวพูดถึง
 * ไม่ใช่คะแนน เพราะคะแนนบอกว่าข่าวเกี่ยวกับเขาแรงแค่ไหน แต่ไม่บอกว่าคุยแล้วได้เท่าไร
 * (ลูกค้าคะแนน 51 ที่ถือของตัวนั้น 15 ลบ. คุ้มกว่าคะแนน 540 ที่ถือ 3 แสน)
 * สลับไปเรียงตามคะแนนได้ ถ้าอยากไล่ตามความแรงของข่าว
 */

const DIR_COLOR: Record<string, string> = {
  up: 'var(--pos)',
  down: 'var(--critical)',
  mixed: 'var(--warning)',
  position_dependent: 'var(--warning)',
}
const ARROW: Record<string, string> = { up: '↑', down: '↓', mixed: '↕', position_dependent: '↕' }

/** แถบเทียบเงินกับคนที่มากสุดในลิสต์ — ไล่สายตาจากบนลงล่างได้เร็วกว่าอ่านตัวเลข */
function Bar({ v, max }: { v: number; max: number }) {
  return (
    <span className="mt-1 block h-1 w-full overflow-hidden rounded-in bg-rule">
      <span
        className="block h-full"
        style={{ width: `${max ? Math.max((v / max) * 100, 1.5) : 0}%`, background: 'var(--s1)' }}
      />
    </span>
  )
}

function EntityChips({ items, lang }: { items: QueueRow['entities']; lang: string }) {
  return (
    <span className="flex flex-wrap gap-1">
      {items.map((e) => (
        <Link
          key={e.entity}
          to={`/stock/${encodeURIComponent(e.entity)}`}
          className="tap rounded-in border border-rule px-1.5 py-0.5 text-micro text-ink-2 hover:border-ink-3 hover:text-ink"
          title={thb(e.value, lang)}
        >
          {e.entity}
          {e.value ? <span className="ml-1 text-ink-3">{thb(e.value, lang)}</span> : null}
        </Link>
      ))}
    </span>
  )
}

/* ------------------------------------------------------------ มุมตามลูกค้า */

function ByCustomer({
  rows,
  sort,
  setSort,
}: {
  rows: QueueRow[]
  sort: string
  setSort: (s: string) => void
}) {
  const { t, isTh, lang } = useI18n()
  const max = Math.max(...rows.map((r) => r.matched_value || 0), 1)

  return (
    <div className="mt-5">
      <div className="mb-2 flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <p className="max-w-[70ch] text-small text-ink-2">
          {isTh
            ? 'เรียงตามเงินที่ข่าววันนี้ไปแตะ — มูลค่าที่ลูกค้าถือใน "ตัวที่ข่าวพูดถึง" ไม่ใช่พอร์ตทั้งใบ'
            : 'Ranked by money the news touches — value held in the instruments the news is about, not the whole portfolio'}
        </p>
        <Segmented>
          <Seg active={sort === 'value'} onClick={() => setSort('value')}>
            {isTh ? 'เรียงตามเงิน' : 'By value'}
          </Seg>
          <Seg active={sort === 'score'} onClick={() => setSort('score')}>
            {isTh ? 'เรียงตามคะแนน' : 'By score'}
          </Seg>
        </Segmented>
      </div>

      <Scroll>
        <table className="w-full min-w-[900px] table-fixed border-collapse">
          <colgroup>
            <col className="w-[3%]" />
            <col className="w-[17%]" />
            <col className="w-[17%]" />
            <col className="w-[22%]" />
            <col className="w-[30%]" />
            <col className="w-[11%]" />
          </colgroup>
          <thead>
            <tr>
              <Th right>#</Th>
              <Th>{t('k.customers')}</Th>
              <Th right>{isTh ? 'เงินที่ข่าวแตะ' : 'Money in play'}</Th>
              <Th>{isTh ? 'หุ้นที่ข่าวพูดถึง' : 'Instruments in the news'}</Th>
              <Th>{isTh ? 'เปิดบทสนทนาด้วย' : 'Open the call with'}</Th>
              <Th right>{t('k.score')}</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.customer_key} className="hover:bg-wash">
                <Td right className="text-ink-3">
                  {i + 1}
                </Td>
                <Td>
                  <Link
                    to={`/customers/${encodeURIComponent(r.customer_key)}`}
                    className="tnum font-medium text-ink hover:underline"
                  >
                    {r.customer_key}
                  </Link>
                  <div className="text-micro text-ink-3">
                    {t(`tier.${r.portfolio_tier}`, r.portfolio_tier)} ·{' '}
                    {t(`persona.${r.persona}`, r.persona)}
                  </div>
                  <div className="text-micro text-ink-3">
                    {isTh ? 'พอร์ต' : 'portfolio'} {thb(r.portfolio_value, lang)}
                    {r.days_since_last_trade != null
                      ? ` · ${isTh ? 'ไม่เทรด' : 'idle'} ${num(r.days_since_last_trade)} ${isTh ? 'วัน' : 'd'}`
                      : ''}
                  </div>
                </Td>
                <Td right>
                  <span className="tnum text-body font-semibold text-ink">
                    {thb(r.matched_value, lang)}
                  </span>
                  <Bar v={r.matched_value} max={max} />
                  <span className="mt-0.5 block text-micro text-ink-3">
                    {num(r.n_entities)} {isTh ? 'ตัว' : 'instruments'}
                  </span>
                </Td>
                <Td>
                  <EntityChips items={r.entities} lang={lang} />
                </Td>
                <Td>
                  <div className="text-small text-ink-2">
                    {isTh ? r.top_reason_th : r.top_reason_en}
                  </div>
                  {r.top_article_id ? (
                    <Link
                      to={`/news/${encodeURIComponent(r.top_article_id)}`}
                      state={{ from: '/' }}
                      className="tap mt-0.5 line-clamp-2 block text-micro text-ink-3 hover:text-ink hover:underline"
                    >
                      {r.top_title}
                    </Link>
                  ) : null}
                </Td>
                <Td right className="text-body font-semibold">
                  {r.top_score.toFixed(0)}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Scroll>
    </div>
  )
}

/* --------------------------------------------------------------- มุมตามข่าว */

function ByNews({ rows }: { rows: RmNewsRow[] }) {
  const { t, isTh, lang } = useI18n()
  const max = Math.max(...rows.map((r) => r.matched_value || 0), 1)

  return (
    <div className="mt-5">
      <p className="mb-3 max-w-[70ch] text-small text-ink-2">
        {isTh
          ? 'ข่าววันนี้ชิ้นไหนไปแตะเงินของลูกค้าเรามากสุด · แต่ละชิ้นบอกลูกค้ารายใหญ่ที่สุดที่โดนข่าวนั้น'
          : 'Which of today’s articles touch the most client money, with the biggest affected clients per article'}
      </p>
      <ul className="border-t border-rule">
        {rows.map((a) => (
          <li key={a.article_id} className="border-b border-rule py-4">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="min-w-[6.5rem]">
                <span className="tnum text-h2 font-semibold text-ink">
                  {thb(a.matched_value, lang)}
                </span>
                <Bar v={a.matched_value} max={max} />
              </span>
              <span className="text-small text-ink-2">
                {num(a.customers)} {isTh ? 'คนเข้าเกณฑ์' : 'matched'}
                {a.n_hold ? (
                  <span className="text-ink-3">
                    {' '}
                    · {isTh ? 'ถืออยู่จริง' : 'actually holding'} {num(a.n_hold)}
                  </span>
                ) : null}
              </span>
              {a.overall !== 'unknown' ? (
                <span
                  className="text-small font-semibold"
                  style={{ color: DIR_COLOR[a.overall] ?? 'var(--ink-3)' }}
                >
                  {ARROW[a.overall] ?? ''} {t(`ov.${a.overall}`, a.overall)}
                </span>
              ) : (
                <span className="text-micro text-ink-3">
                  {isTh ? 'ข่าวไม่ได้บอกทิศทาง' : 'no stated direction'}
                </span>
              )}
              <span className="ml-auto tnum text-micro text-ink-3">
                {time(a.trigger_at)} · {t('k.score')} {a.top_score.toFixed(0)}
              </span>
            </div>

            <Link
              to={`/news/${encodeURIComponent(a.article_id)}`}
              state={{ from: '/' }}
              className="tap mt-1 block text-body font-medium text-ink hover:underline"
            >
              {a.title}
            </Link>
            {a.why_th ? (
              <p className="mt-0.5 text-small text-ink-2">{isTh ? a.why_th : a.why_en}</p>
            ) : null}

            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
              {a.top_customers.map((cu) => (
                <span key={cu.customer_key} className="flex items-baseline gap-1.5 text-small">
                  <Link
                    to={`/customers/${encodeURIComponent(cu.customer_key)}`}
                    className="tap tnum font-medium text-ink hover:underline"
                  >
                    {cu.customer_key}
                  </Link>
                  <span className="text-micro text-ink-3">
                    {t(`tier.${cu.portfolio_tier}`, cu.portfolio_tier)}
                  </span>
                  <Link
                    to={`/stock/${encodeURIComponent(cu.matched_entity)}`}
                    className="tap text-micro text-ink-2 hover:underline"
                  >
                    {cu.matched_entity}
                  </Link>
                  <span className="tnum font-medium text-ink-2">
                    {cu.holding_value ? thb(cu.holding_value, lang) : '—'}
                  </span>
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* -------------------------------------------------------------- มุมตามหุ้น */

/**
 * ทำเป็นการ์ด ไม่ใช่ตาราง เพราะหนึ่งหุ้นมีของหลายชนิดต้องอ่านพร้อมกัน
 * (เงิน · ทิศทาง · จำนวนคน · ข่าวที่เป็นเหตุ · ชื่อลูกค้ารายใหญ่)
 * ยัดลงตารางแล้วคอลัมน์เยอะจนต้องเลื่อน และสายตาต้องกระโดดไปมา
 */
function ByEntity({ rows }: { rows: RmEntityRow[] }) {
  const { t, isTh, lang } = useI18n()
  const max = Math.max(...rows.map((r) => r.matched_value || 0), 1)

  return (
    <div className="mt-5">
      <p className="mb-4 max-w-[74ch] text-small text-ink-2">
        {isTh
          ? 'ข่าววันนี้ทำให้ตัวไหนกลายเป็นเรื่องที่ต้องโทรคุย · เรียงตามเงินที่ลูกค้าในความดูแลถืออยู่กับตัวนั้น'
          : 'Which instruments today’s news puts on the table, ranked by the money your clients hold in them'}
      </p>

      <div className="grid gap-x-8 gap-y-7 lg:grid-cols-2 2xl:grid-cols-3">
        {rows.map((r) => (
          <section key={r.entity} className="min-w-0 border-t border-rule pt-3">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <Link
                to={`/stock/${encodeURIComponent(r.entity)}`}
                className="tap text-h2 font-semibold text-ink hover:underline"
              >
                {r.entity}
              </Link>
              {/* หุ้นเด่นที่บทความชี้เอง ไม่ใช่ผลจากการตีความของเรา — น้ำหนักต่างกัน */}
              {r.top_pick ? (
                <span
                  className="rounded-full border px-2 py-0.5 text-micro font-semibold"
                  style={{
                    color: 'var(--serious)',
                    borderColor: 'var(--serious)',
                    background: 'var(--wash)',
                  }}
                >
                  {isTh ? 'หุ้นเด่นประจำวัน INVX' : 'INVX Daily Top Pick'}
                </span>
              ) : null}
              {r.coverage === 'brief' ? (
                <span className="rounded-in bg-wash px-1.5 py-0.5 text-micro text-ink-3">
                  {isTh ? 'จากสรุปรายวัน' : 'daily wrap only'}
                </span>
              ) : null}
              {r.overall !== 'unknown' ? (
                <span
                  className="text-small font-semibold"
                  style={{ color: DIR_COLOR[r.overall] ?? 'var(--ink-3)' }}
                >
                  {ARROW[r.overall] ?? ''} {t(`ov.${r.overall}`, r.overall)}
                </span>
              ) : (
                <span className="text-micro text-ink-3">
                  {isTh ? 'ข่าวไม่ได้บอกทิศทาง' : 'no stated direction'}
                </span>
              )}
              <span className="ml-auto tnum text-micro text-ink-3">
                {t('k.score')} {r.top_score.toFixed(0)}
              </span>
            </div>

            <div className="mt-2 flex items-baseline gap-3">
              <span className="tnum text-h1 font-semibold text-ink">
                {thb(r.matched_value, lang)}
              </span>
              <span className="text-small text-ink-2">
                {num(r.customers)} {isTh ? 'คน' : 'clients'}
                {/* L1 = ถือของตัวนั้นจริง ที่เหลือเป็นความเกี่ยวข้องทางอื่น ต้องแยกให้เห็น */}
                {r.n_hold < r.customers ? (
                  <span className="text-ink-3">
                    {' '}
                    ({isTh ? 'ถือจริง' : 'holding'} {num(r.n_hold)})
                  </span>
                ) : null}
              </span>
            </div>
            <Bar v={r.matched_value} max={max} />

            {r.top_level !== 'L1_HOLD' ? (
              <p className="mt-1.5 text-micro text-ink-3">
                {isTh
                  ? 'เข้าเกณฑ์ทางกลุ่ม/ความเกี่ยวข้อง ไม่ใช่ถือตัวนี้ตรง ๆ — มูลค่าคิดจากสัดส่วนพอร์ตที่เกี่ยว'
                  : 'Matched by sector or relation, not a direct holding — value is the related share of portfolio'}
              </p>
            ) : null}

            {r.lead ? (
              <div className="mt-2.5">
                {/* หุ้นที่มาจากสรุปรายวันล้วน พาดหัวเป็นของภาพรวมตลาด ไม่ได้พูดถึงตัวมันเอง
                    ("คาด SET แกว่งตัว…") จึงสลับให้ประโยคของหุ้นตัวนี้ขึ้นก่อน แล้วพาดหัว
                    ลงไปเป็นที่มา — ไม่งั้นทั้งลิสต์อ่านเหมือนข่าวเดียวกันซ้ำสิบกว่าครั้ง */}
                {r.coverage === 'brief' ? (
                  <>
                    {r.lead.why_th ? (
                      <p className="text-small font-medium text-ink-2">
                        {isTh ? r.lead.why_th : r.lead.why_en}
                      </p>
                    ) : (
                      <p className="text-small text-ink-3">
                        {isTh
                          ? 'สรุปรายวันเอ่ยถึงตัวนี้ แต่ไม่ได้ให้คำแนะนำเจาะจง'
                          : 'mentioned in the daily wrap without a specific call'}
                      </p>
                    )}
                    <Link
                      to={`/news/${encodeURIComponent(r.lead.article_id)}`}
                      state={{ from: '/' }}
                      className="tap mt-0.5 line-clamp-1 block text-micro text-ink-3 hover:text-ink hover:underline"
                    >
                      {isTh ? 'จากสรุปรายวัน · ' : 'from the daily wrap · '}
                      {r.lead.title}
                    </Link>
                  </>
                ) : (
                  <>
                    <Link
                      to={`/news/${encodeURIComponent(r.lead.article_id)}`}
                      state={{ from: '/' }}
                      className="tap line-clamp-2 block text-small font-medium text-ink-2 hover:text-ink hover:underline"
                    >
                      {r.lead.title}
                    </Link>
                    {r.lead.why_th ? (
                      <p className="mt-0.5 line-clamp-2 text-micro text-ink-3">
                        {isTh ? r.lead.why_th : r.lead.why_en}
                      </p>
                    ) : null}
                  </>
                )}
                {/* ความเห็นของนักวิเคราะห์บ้านเราเอง — สิ่งที่ RM เอาไปพูดได้จริงก่อนโทร
                    ตัดสั้นตรงนี้เพราะการ์ดเรียงกันหลายสิบใบ กดเข้าข่าวอ่านเต็มได้ */}
                {r.lead.invx_view ? (
                  <p
                    className="mt-1.5 line-clamp-3 rounded-in px-2.5 py-1.5 text-micro leading-relaxed text-ink-2"
                    style={{ background: 'var(--wash)', borderLeft: '2px solid var(--accent)' }}
                  >
                    <b style={{ color: 'var(--accent)' }}>
                      {isTh ? 'มุมมองของ InnovestX · ' : 'InnovestX view · '}
                    </b>
                    {r.lead.invx_view}
                  </p>
                ) : null}
                {r.n_articles > 1 ? (
                  <p className="mt-0.5 text-micro text-ink-3">
                    {isTh ? `รวม ${num(r.n_articles)} ข่าว` : `${num(r.n_articles)} articles`}
                  </p>
                ) : null}
              </div>
            ) : null}

            <ul className="mt-2.5 border-t border-rule">
              {r.top_customers.map((cu) => (
                <li
                  key={cu.customer_key}
                  className="flex items-baseline gap-2 border-b border-rule py-1 last:border-0"
                >
                  <Link
                    to={`/customers/${encodeURIComponent(cu.customer_key)}`}
                    className="tap tnum text-small font-medium text-ink hover:underline"
                  >
                    {cu.customer_key}
                  </Link>
                  <span className="text-micro text-ink-3">
                    {t(`tier.${cu.portfolio_tier}`, cu.portfolio_tier)}
                  </span>
                  <span className="tnum ml-auto text-small text-ink-2">
                    {cu.holding_value ? thb(cu.holding_value, lang) : '—'}
                  </span>
                </li>
              ))}
            </ul>
            {r.customers > r.top_customers.length ? (
              <Link
                to={`/stock/${encodeURIComponent(r.entity)}`}
                className="tap mt-1.5 block text-micro text-ink-3 hover:text-ink hover:underline"
              >
                {isTh
                  ? `ดูอีก ${num(r.customers - r.top_customers.length)} คนในหน้าหุ้น`
                  : `see ${num(r.customers - r.top_customers.length)} more on the instrument page`}
              </Link>
            ) : null}
          </section>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------- หน้า */

export default function RmQueue() {
  const { t, isTh, lang } = useI18n()
  const { data: rms } = useRms()
  const { data: dates } = useDates()
  const [rm, setRm] = useState<string>()
  const [date, setDate] = useState<string>()
  const [view, setView] = useState<'customer' | 'news' | 'entity'>('entity')
  const [sort, setSort] = useState('value')

  const active = rm ?? rms?.[0]?.rm_id
  // วันล่าสุดที่มีข่าว = วันทำงานจริงของ RM ไม่ใช่ "ทุกวันรวมกัน" ซึ่งทำให้ยอดเงินบวม
  const day = date ?? dates?.[0]?.d
  const q = useRmQueue(active, day, sort)
  const n = useRmNews(active, day)
  const en = useRmEntities(active, day)

  const rowsC = q.data?.items ?? []
  const rowsN = n.data?.items ?? []
  const rowsE = en.data?.items ?? []
  const loading =
    view === 'customer' ? q.isLoading : view === 'news' ? n.isLoading : en.isLoading
  const empty =
    view === 'customer' ? !rowsC.length : view === 'news' ? !rowsN.length : !rowsE.length
  const biggest = rowsC.reduce<QueueRow | undefined>(
    (a, r) => (!a || r.matched_value > a.matched_value ? r : a),
    undefined,
  )

  return (
    <div>
      <header>
        <h1 className="text-h1 font-semibold text-ink">{t('nav.rm')}</h1>
        <p className="mt-0.5 max-w-[74ch] text-small text-ink-2">
          {isTh
            ? 'ข่าวของวันไปแตะพอร์ตใครบ้าง แล้วเรียงตามเงินที่อยู่กับข่าวนั้น เพื่อให้โทรตัวใหญ่ก่อน'
            : 'Which portfolios the day’s news touches, ranked by the money involved so the biggest calls come first'}
        </p>
      </header>

      <div className="mt-6 flex flex-wrap items-end justify-between gap-x-8 gap-y-4 border-b border-rule pb-5">
        <div className="flex flex-wrap items-end gap-x-10 gap-y-4">
          <Figure
            value={thb(q.data?.value_total ?? 0, lang)}
            label={isTh ? 'เงินที่ข่าววันนี้แตะ' : 'money the news touches'}
            sub={
              isTh
                ? `${num(q.data?.total ?? 0)} คนควรโทร · ${num(n.data?.total ?? 0)} ข่าว · ${num(
                    en.data?.total ?? 0,
                  )} ตัว`
                : `${num(q.data?.total ?? 0)} to call · ${num(n.data?.total ?? 0)} articles · ${num(
                    en.data?.total ?? 0,
                  )} instruments`
            }
          />
          {/* รายใหญ่สุดต้องเป็นคนเดิมเสมอ ไม่เปลี่ยนตามว่ากำลังเรียงด้วยอะไร */}
          {biggest ? (
            <Figure
              value={thb(biggest.matched_value, lang)}
              label={isTh ? 'รายใหญ่สุดวันนี้' : 'biggest call today'}
              sub={`${biggest.customer_key} · ${biggest.top_entity ?? ''}`}
            />
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* ตามหุ้นมาก่อน — โทรทีละหุ้นได้ประเด็นเดียวคุยได้หลายคน
              เรียงตามลูกค้าต้องเปลี่ยนเรื่องพูดทุกสาย และเป็นมุมเดียวกับที่ส่งในอีเมล */}
          <Segmented>
            <Seg active={view === 'entity'} onClick={() => setView('entity')}>
              {isTh ? 'ตามหุ้น' : 'By instrument'}
            </Seg>
            <Seg active={view === 'customer'} onClick={() => setView('customer')}>
              {isTh ? 'ตามลูกค้า' : 'By client'}
            </Seg>
            <Seg active={view === 'news'} onClick={() => setView('news')}>
              {isTh ? 'ตามข่าว' : 'By article'}
            </Seg>
          </Segmented>
          <Segmented>
            {rms?.map((r) => (
              <Seg key={r.rm_id} active={active === r.rm_id} onClick={() => setRm(r.rm_id)}>
                {r.rm_id}
              </Seg>
            ))}
          </Segmented>
          <Segmented>
            {(dates ?? []).slice(0, 5).map((d) => (
              <Seg key={d.d} active={day === d.d} onClick={() => setDate(d.d)} count={d.articles}>
                {d.d.slice(5)}
              </Seg>
            ))}
            <Seg active={!day} onClick={() => setDate(undefined)}>
              {t('a.all')}
            </Seg>
          </Segmented>
        </div>
      </div>

      {loading ? (
        <div className="mt-5">
          <Loading rows={10} />
        </div>
      ) : empty ? (
        <Empty />
      ) : view === 'customer' ? (
        <ByCustomer rows={rowsC} sort={sort} setSort={setSort} />
      ) : view === 'news' ? (
        <ByNews rows={rowsN} />
      ) : (
        <ByEntity rows={rowsE} />
      )}

      <p className="mt-8 max-w-[86ch] text-micro leading-relaxed text-ink-3">
        {isTh
          ? '"เงินที่ข่าวแตะ" รวมแบบไม่นับซ้ำต่อหุ้น ถ้าวันนั้นมีข่าวถึงหุ้นเดียวกันหลายชิ้น · ' +
            'ยอดนี้อาจมากกว่ามูลค่าพอร์ตของบางคน เพราะพอร์ตเป็นภาพ ณ วัน snapshot ' +
            'ส่วนรายการที่ซื้อหลังวันนั้นถูกนับเป็นการถือครองด้วย (R1.17) · ' +
            'ระดับ L3/L5/L6 คิดมูลค่าจากสัดส่วนพอร์ตที่เกี่ยวข้อง ไม่ใช่หุ้นตัวเดียว'
          : 'Money in play is de-duplicated per instrument · it can exceed a client’s portfolio value because the portfolio is a snapshot while post-snapshot buys still count as holdings (R1.17)'}
      </p>
      <p className="mt-2 text-micro text-ink-3">{t('msg.notSentToClient')}</p>
    </div>
  )
}
