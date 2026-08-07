import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useEntitySearch, useEntityView, useHighlights, useRms } from '../lib/api'
import type { EntityNews, Highlight as HighlightT } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { num, pct, thb, time, dayMonth } from '../lib/format'
import { Empty, Figure, Head, InstrumentLabel, Loading, Row, Scroll, Seg, Segmented, Td, Th } from '../components/ui'
import PriceChart from '../components/PriceChart'

/**
 * มุมมองกลับทางจากหน้าอื่น — เริ่มจาก "หุ้นตัวนี้" ไม่ใช่ "ข่าวชิ้นนี้"
 *
 * คำถามที่หน้านี้ตอบ: ใครถือเยอะสุด · ถือคิดเป็นสัดส่วนเท่าไรของพอร์ตเขา ·
 * วันนี้ข่าวว่าอะไร · สัปดาห์นี้ทิศทางรวมเป็นแบบไหน · ใครเคยเทรดแต่ตอนนี้ไม่ถือ
 */

const ARROW: Record<string, string> = { up: '↑', down: '↓', mixed: '↕', flat: '→' }

function dirColor(d: string) {
  if (d === 'up') return 'var(--pos)'
  if (d === 'down') return 'var(--critical)'
  if (d === 'mixed' || d === 'position_dependent') return 'var(--warning)'
  return undefined
}

function DirBadge({ d, big }: { d: string; big?: boolean }) {
  const { t } = useI18n()
  const c = dirColor(d)
  return (
    <span
      className={`${big ? 'text-h1' : 'text-body'} font-semibold`}
      style={c ? { color: c } : { color: 'var(--ink-3)' }}
    >
      {ARROW[d] ?? ''} {t(`ov.${d}`, d)}
    </span>
  )
}

/* --------------------------------------------------------------------------
   หน้าเริ่มต้น — ยังไม่ได้ค้นอะไร ระบบเสนอเองว่าวันนี้ตัวไหนน่าสนใจ
   ทุกแถวต้องบอกได้ว่าขึ้นมาเพราะอะไร ไม่ใช่คะแนนลอย ๆ
-------------------------------------------------------------------------- */

function HlRow({ h, showPnl }: { h: HighlightT; showPnl?: boolean }) {
  const { isTh, lang } = useI18n()
  return (
    <li className="border-b border-rule py-2.5 last:border-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Link
          to={`/stock/${encodeURIComponent(h.entity)}`}
          className="tap text-body font-semibold text-ink hover:underline"
        >
          {h.entity}
        </Link>
        <DirBadge d={h.overall} />
        <span className="ml-auto flex shrink-0 items-baseline gap-3 text-small">
          {h.matched_today ? (
            <span className="tnum text-ink">
              {num(h.matched_today)}{' '}
              <span className="text-micro text-ink-3">{isTh ? 'คนเข้าเกณฑ์' : 'matched'}</span>
            </span>
          ) : null}
          {h.holders ? (
            <>
              <span className="tnum text-ink-2">
                {num(h.holders)} <span className="text-micro text-ink-3">{isTh ? 'คนถือ' : 'hold'}</span>
              </span>
              {/* มูลค่าคือตัวที่ใช้ตัดสินว่าจะโทรใครก่อน จำนวนคนบอกไม่ได้ */}
              <span className="tnum font-medium text-ink">{thb(h.value, lang)}</span>
            </>
          ) : (
            <span className="text-micro text-ink-3">{isTh ? 'ยังไม่มีใครถือ' : 'nobody holds it'}</span>
          )}
          {showPnl && h.pnl != null ? (
            <span className="tnum" style={{ color: h.pnl < 0 ? 'var(--critical)' : 'var(--pos)' }}>
              {h.pnl >= 0 ? '+' : ''}
              {thb(h.pnl, lang)}
            </span>
          ) : null}
        </span>
      </div>
      {h.why_th ? (
        <p className="mt-0.5 text-small text-ink-2">
          {isTh ? h.why_th : h.why_en}
          {h.phrase ? <span className="ml-1.5 text-ink-3">“{h.phrase.slice(0, 70)}”</span> : null}
        </p>
      ) : (
        <p className="mt-0.5 text-small text-ink-3">
          {isTh
            ? `มีข่าวถึง ${num(h.news_recent)} ชิ้น แต่ข่าวไม่ได้ระบุทิศทาง`
            : `${num(h.news_recent)} article(s), no stated direction`}
        </p>
      )}
      {h.title ? (
        <p className="mt-0.5 truncate text-micro text-ink-3" title={h.title}>
          {h.news_week > h.news_recent
            ? `${h.title} · ${isTh ? `สัปดาห์นี้ ${num(h.news_week)} ข่าว` : `${num(h.news_week)} this week`}`
            : h.title}
        </p>
      ) : null}
    </li>
  )
}

function Highlights() {
  const { t, isTh, lang } = useI18n()
  const [days, setDays] = useState(1)
  // ไม่เลือกผู้ดูแล = ภาพรวมทั้งบริษัท ต้องเป็นค่าเริ่มต้นเพราะคนเปิดดูไม่ได้ดูแลพอร์ตเองก็มี
  const [rm, setRm] = useState<string>()
  const { data: rms } = useRms()
  const { data, isLoading } = useHighlights(days, 7, rm)

  if (isLoading) return <div className="mt-8"><Loading rows={8} /></div>
  if (!data) return <Empty />

  const main = data.with_news_in_portfolio
  const risk = data.negative_and_losing
  const week = data.most_talked_this_week
  const fresh = data.with_news_not_held

  return (
    <div className="mt-9">
      <Head
        note={
          rm
            ? isTh
              ? `นับเฉพาะลูกค้าของ ${rm} เรียงตามมูลค่าที่เขาถือ · ทุกแถวบอกที่มาของทิศทาง`
              : `Only ${rm}’s customers, ranked by the value they hold · every row states its evidence`
            : isTh
              ? 'ทั้งบริษัท เรียงตามจำนวนลูกค้าที่เข้าเกณฑ์ แล้วจึงจำนวนคนถือ · ทุกแถวบอกที่มาของทิศทาง'
              : 'Whole firm, ranked by customers matched from recent news, then holders · every row states its evidence'
        }
        right={
          <span className="flex flex-wrap items-center gap-2">
            <Segmented>
              <Seg active={!rm} onClick={() => setRm(undefined)}>
                {t('k.allRms')}
              </Seg>
              {rms?.map((r) => (
                <Seg key={r.rm_id} active={rm === r.rm_id} onClick={() => setRm(r.rm_id)}>
                  {r.rm_id}
                </Seg>
              ))}
            </Segmented>
            <span className="flex gap-1">
              {[1, 3, 7].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDays(d)}
                  className={`tap rounded-in px-2 py-0.5 text-micro ${
                    days === d ? 'bg-ink text-paper' : 'text-ink-3 hover:text-ink'
                  }`}
                >
                  {d === 1 ? (isTh ? 'วันนี้' : 'today') : `${d}${isTh ? ' วัน' : 'd'}`}
                </button>
              ))}
            </span>
          </span>
        }
      >
        {rm
          ? isTh
            ? `วันนี้ตัวไหนน่าสนใจ — ลูกค้าของ ${rm}`
            : `What looks interesting today — ${rm}`
          : isTh
            ? 'วันนี้ตัวไหนน่าสนใจ'
            : 'What looks interesting today'}
      </Head>

      {main.length === 0 ? (
        <p className="border-t border-rule py-6 text-small text-ink-3">
          {isTh
            ? `ยังไม่มีข่าวที่แตะสินทรัพย์ที่ลูกค้า${rm ? `ของ ${rm}` : ''}ถืออยู่ในช่วงนี้`
            : `no news touching instruments held${rm ? ` by ${rm}’s customers` : ''} in this window`}
        </p>
      ) : (
        <ul className="border-t border-rule">
          {main.map((h) => (
            <HlRow key={h.entity} h={h} />
          ))}
        </ul>
      )}

      <div className="mt-11 grid gap-x-10 gap-y-10 lg:grid-cols-2">
        {risk.length ? (
          <section className="min-w-0">
            <Head
              note={
                isTh
                  ? 'ข่าวไปทางลบ และรวมทั้งกลุ่มลูกค้าถือตัวนี้อยู่ในสถานะขาดทุน — ควรโทรก่อนลูกค้าโทรมา'
                  : 'Negative news on a position that is underwater in aggregate — call before they call you'
              }
            >
              {isTh ? 'ควรโทรก่อน' : 'Call first'}
            </Head>
            <ul className="border-t border-rule">
              {risk.map((h) => (
                <HlRow key={h.entity} h={h} showPnl />
              ))}
            </ul>
          </section>
        ) : null}

        <section className="min-w-0">
          <Head
            note={
              isTh
                ? 'ถูกเขียนถึงหลายชิ้นในเจ็ดวัน แปลว่าเป็นประเด็นที่ยังเดินอยู่'
                : 'Written about repeatedly in seven days — a running story'
            }
          >
            {isTh ? 'ประเด็นที่กำลังเดิน' : 'Running stories'}
          </Head>
          <ul className="border-t border-rule">
            {week.slice(0, 6).map((h) => (
              <HlRow key={h.entity} h={h} />
            ))}
          </ul>
        </section>

        <section className="min-w-0">
          <Head
            note={
              isTh
                ? 'ข่าวพูดถึงแต่ยังไม่มีลูกค้าถือ — ใช้เป็นของเสนอใหม่ได้'
                : 'In the news but nobody holds it — possible new idea'
            }
          >
            {isTh ? 'ยังไม่มีใครถือ' : 'Not held yet'}
          </Head>
          <ul className="border-t border-rule">
            {fresh.slice(0, 6).map((h) => (
              <HlRow key={h.entity} h={h} />
            ))}
          </ul>
        </section>

        <section className="min-w-0">
          <Head
            note={
              rm
                ? isTh
                  ? `ตัวที่ลูกค้าของ ${rm} ถือหนักสุด เรียงตามมูลค่า`
                  : `${rm}’s heaviest positions by value`
                : isTh
                  ? 'ไล่ดูตัวที่พอร์ตรวมถือหนักสุด'
                  : 'The heaviest positions across all portfolios'
            }
          >
            {rm
              ? isTh
                ? `ถือเยอะสุดของ ${rm}`
                : `Most held — ${rm}`
              : isTh
                ? 'ถือเยอะสุดในพอร์ตรวม'
                : 'Most held'}
          </Head>
          <ul className="border-t border-rule">
            {data.most_held.slice(0, 8).map((m) => (
              <li key={m.entity} className="flex items-baseline gap-3 border-b border-rule py-2 last:border-0">
                <Link
                  to={`/stock/${encodeURIComponent(m.entity)}`}
                  className="tap text-body font-medium text-ink hover:underline"
                >
                  {m.entity}
                </Link>
                <span className="tnum ml-auto text-small text-ink-2">
                  {num(m.holders)} <span className="text-micro text-ink-3">{isTh ? 'คน' : ''}</span>
                </span>
                <span className="tnum w-24 text-right text-small text-ink-3">{thb(m.value, lang)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <p className="mt-10 max-w-[80ch] text-micro leading-relaxed text-ink-3">
        {isTh
          ? `ข้อมูล ณ ${data.date} · "คนเข้าเกณฑ์" นับทุกระดับความเกี่ยวข้อง ไม่ใช่แค่คนที่ถือตัวนั้น จึงมากกว่าจำนวนคนถือได้ · ${t('msg.notSentToClient')}`
          : `As of ${data.date} · “matched” counts every relation level, not just holders, so it can exceed the holder count`}
      </p>
    </div>
  )
}

export default function Stock() {
  const { entity } = useParams()
  const nav = useNavigate()
  const { t, isTh, lang } = useI18n()
  const [q, setQ] = useState('')
  const [days, setDays] = useState(7)
  const [showWatchers, setShowWatchers] = useState(false)
  // ตัวกรองผู้ดูแล เป็นสถานะของหน้าจอเท่านั้น ไม่ใช่ตัวตนของผู้ใช้
  // ค่าเริ่มต้นคือไม่กรอง เพราะคนที่ไม่ได้ดูแลพอร์ตเองต้องได้ภาพรวมทันที
  const [rm, setRm] = useState<string>()

  const { data: found } = useEntitySearch(q)
  const { data, isLoading } = useEntityView(entity, days, rm)

  // พิมพ์ชื่อเต็มแล้วกด Enter ไปเลย ไม่ต้องรอกดจากรายการ
  const go = (e: string) => {
    setQ('')
    nav(`/stock/${encodeURIComponent(e)}`)
  }
  useEffect(() => {
    document.title = entity ? `${entity} · INVX` : 'INVX'
    setRm(undefined)          // เปลี่ยนตัวแล้วต้องกลับเป็นภาพรวม ไม่ค้างตัวกรองของตัวก่อน
  }, [entity])

  const news = data?.news ?? []
  const todayNews = news.filter((n) => n.is_today)
  const weekNews = news.filter((n) => !n.is_today)

  const newsRow = (n: EntityNews) => (
    <li key={n.article_id} className="border-b border-rule py-2.5 last:border-0">
      <div className="flex items-baseline gap-2">
        <span className="tnum text-micro text-ink-3">
          {n.is_today ? time(n.trigger_at) : `${dayMonth(n.trigger_at, lang)} ${time(n.trigger_at)}`}
        </span>
        <span className="truncate text-micro text-ink-3">{n.subcategory_name || n.subcategory}</span>
        <span className="ml-auto shrink-0">
          <DirBadge d={n.overall} />
        </span>
      </div>
      <Link
        to={`/news/${encodeURIComponent(n.article_id)}`}
        state={{ from: `/stock/${encodeURIComponent(entity ?? '')}` }}
        className="tap mt-0.5 block text-body leading-snug text-ink hover:underline"
      >
        {n.title}
      </Link>
      {n.signals.length ? (
        <p className="mt-1 text-small text-ink-2">
          {isTh ? n.signals[0].th : n.signals[0].en}
          {n.signals[0].phrase ? (
            <span className="ml-1.5 text-ink-3">“{n.signals[0].phrase.slice(0, 90)}”</span>
          ) : null}
        </p>
      ) : null}
      <p className="mt-1 text-micro text-ink-3">
        {n.n_matches ? (
          <>
            {num(n.n_matches)} {isTh ? 'คนเข้าเกณฑ์จากข่าวนี้' : 'customers matched'}
          </>
        ) : isTh ? (
          'ไม่มีใครเข้าเกณฑ์จากข่าวนี้'
        ) : (
          'nobody matched'
        )}
      </p>
    </li>
  )

  return (
    <div>
      <header>
        <h1 className="text-h1 font-semibold text-ink">{t('nav.stock')}</h1>
        <p className="mt-1 text-body text-ink-2">
          {isTh
            ? 'พิมพ์ชื่อหุ้น กองทุน หรือคริปโต แล้วดูว่าใครถือเยอะสุด และข่าวช่วงนี้ว่าอะไร'
            : 'Type a stock, fund or crypto to see who holds the most of it, and what the news says'}
        </p>
      </header>

      {/* ---------------- ค้นหา ---------------- */}
      <div className="relative mt-6 max-w-lg">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && found?.length) go(found[0].entity)
          }}
          placeholder={isTh ? 'เช่น NVDA, PTT, BTC, SCBWORLD' : 'e.g. NVDA, PTT, BTC'}
          className="w-full rounded-out border border-rule bg-surface px-3 py-2 text-body text-ink outline-none focus:border-rule-strong"
        />
        {q && found?.length ? (
          <ul className="absolute z-10 mt-1 max-h-80 w-full overflow-y-auto rounded-out border border-rule bg-surface shadow-lg">
            {found.map((f) => (
              <li key={f.entity}>
                <button
                  type="button"
                  onClick={() => go(f.entity)}
                  className="tap flex w-full items-baseline gap-3 border-b border-rule px-3 py-2 text-left last:border-0 hover:bg-wash"
                >
                  <span className="font-medium text-ink">{f.entity}</span>
                  <span className="tnum ml-auto text-small text-ink-2">
                    {num(f.holders)} {isTh ? 'คนถือ' : 'holders'}
                  </span>
                  <span className="tnum w-24 text-right text-small text-ink-3">{thb(f.value, lang)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {!entity ? (
        <Highlights />
      ) : isLoading ? (
        <div className="mt-8">
          <Loading rows={8} />
        </div>
      ) : !data ? (
        <Empty />
      ) : (
        <>
          {/* ---------------- สรุปหัวหน้า ---------------- */}
          <div className="mt-9 flex flex-wrap items-end gap-x-12 gap-y-6 border-b border-rule pb-6">
            <div>
              <div className="text-display font-semibold text-ink">{data.entity}</div>
              <div className="mt-1 text-small text-ink-2">
                {data.coverage?.sector ? data.coverage.sector : isTh ? 'ไม่อยู่ในลิสต์บทวิเคราะห์ไทย' : 'not in Thai coverage list'}
              </div>
            </div>
            <Figure
              value={num(data.holders_total)}
              label={isTh ? 'ลูกค้าที่ถืออยู่' : 'customers holding'}
              sub={thb(data.value_total, lang)}
            />
            <div>
              <div className="mt-0.5">
                <DirBadge d={data.direction_today} big />
              </div>
              <div className="mt-1 text-small text-ink-2">
                {isTh ? 'ทิศทางจากข่าววันนี้' : 'direction from today’s news'}
              </div>
            </div>
            <div>
              <div className="flex flex-wrap items-baseline gap-3">
                {(['up', 'down', 'mixed', 'position_dependent'] as const).map((k) =>
                  data.direction_week[k] ? (
                    <span key={k} className="text-body font-semibold" style={{ color: dirColor(k) }}>
                      {ARROW[k] ?? ''} {num(data.direction_week[k])}
                    </span>
                  ) : null,
                )}
                {Object.values(data.direction_week).every((v) => !v) ? (
                  <span className="text-body text-ink-3">—</span>
                ) : null}
              </div>
              <div className="mt-1 text-small text-ink-2">
                {isTh ? `ข่าวย้อนหลัง ${days} วัน` : `last ${days} days`}
              </div>
            </div>
          </div>

          {/* กราฟราคา — วางไว้ใต้สรุปเพราะ RM มองราคาก่อนจะไปดูรายชื่อลูกค้า */}
          <div className="mt-7">
            <PriceChart entity={data.entity} target={data.coverage?.target_price ?? null} />
          </div>

          {data.coverage?.rating ? (
            <dl className="mt-7 max-w-md">
              <Row k={isTh ? 'คำแนะนำ INVX Research' : 'INVX Research rating'} v={data.coverage.rating} />
              {data.coverage.target_price ? (
                <Row k={isTh ? 'ราคาเป้าหมาย' : 'target price'} v={thb(data.coverage.target_price, lang)} />
              ) : null}
              {data.coverage.last_close ? (
                <Row k={isTh ? 'ราคาปิดล่าสุด' : 'last close'} v={thb(data.coverage.last_close, lang)} />
              ) : null}
            </dl>
          ) : null}

          <div className="mt-10 flex flex-col gap-11">
            {/* ---------------- ข่าว ---------------- */}
            <section className="min-w-0">
              <Head
                note={
                  isTh
                    ? 'ทิศทางของแต่ละชิ้นมาจากหลักฐานในบทความ ไม่ใช่การให้คำแนะนำ'
                    : 'Each direction comes from evidence in the article, not from advice'
                }
                right={
                  <span className="flex gap-1">
                    {[1, 7, 14].map((d) => (
                      <button
                        key={d}
                        type="button"
                        onClick={() => setDays(d)}
                        className={`tap rounded-in px-2 py-0.5 text-micro ${
                          days === d ? 'bg-ink text-paper' : 'text-ink-3 hover:text-ink'
                        }`}
                      >
                        {d === 1 ? (isTh ? 'วันนี้' : 'today') : `${d}${isTh ? ' วัน' : 'd'}`}
                      </button>
                    ))}
                  </span>
                }
              >
                {isTh ? 'ข่าวที่พูดถึงตัวนี้' : 'News mentioning it'}
              </Head>
              {news.length === 0 ? (
                <p className="border-t border-rule py-6 text-small text-ink-3">
                  {isTh ? `ไม่มีข่าวถึงตัวนี้ใน ${days} วันที่ผ่านมา` : `no news in the last ${days} days`}
                </p>
              ) : (
                <div className="grid gap-x-10 gap-y-6 xl:grid-cols-2">
                  {todayNews.length ? (
                    <div className="min-w-0">
                      <p className="border-t border-rule pt-2 text-micro text-ink-3">
                        {isTh ? 'วันนี้' : 'today'}
                      </p>
                      <ul>{todayNews.map(newsRow)}</ul>
                    </div>
                  ) : null}
                  {weekNews.length ? (
                    <div className="min-w-0">
                      <p className="border-t border-rule pt-2 text-micro text-ink-3">
                        {isTh ? 'ก่อนหน้านี้' : 'earlier'}
                      </p>
                      <ul>{weekNews.map(newsRow)}</ul>
                    </div>
                  ) : null}
                </div>
              )}
            </section>

            {/* ---------------- แยกตามผู้ดูแล ----------------
                ภาพรวมอีกแบบ: เห็นทุกทีมพร้อมกัน แล้วกดเจาะเป็นทีมเดียวได้
                เรียงตามมูลค่าไม่ใช่จำนวนคน เพราะสองอย่างนี้ชี้คนละคน */}
            <section className="min-w-0">
              <Head
                note={
                  isTh
                    ? 'เรียงตามมูลค่าที่ลูกค้าในความดูแลถือ · กดแถวเพื่อดูเฉพาะลูกค้าของคนนั้น'
                    : 'By value held under each RM · click a row to see only their customers'
                }
              >
                {t('k.byRm')}
              </Head>
              <Scroll>
                <table className="w-full min-w-[520px] table-fixed border-collapse">
                  <colgroup>
                    <col className="w-[26%]" />
                    <col className="w-[32%]" />
                    <col className="w-[14%]" />
                    <col className="w-[28%]" />
                  </colgroup>
                  <thead>
                    <tr>
                      <Th>{t('k.rm')}</Th>
                      <Th right>{isTh ? 'มูลค่าที่ถือ' : 'value held'}</Th>
                      <Th right>{t('k.customers')}</Th>
                      <Th right>{isTh ? 'กำไร/ขาดทุนตัวนี้' : 'P/L on this'}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_rm.map((r) => {
                      const on = rm === r.rm_id
                      return (
                        <tr
                          key={r.rm_id}
                          onClick={() => setRm(on ? undefined : r.rm_id)}
                          aria-pressed={on}
                          className={`cursor-pointer ${on ? 'bg-wash' : 'hover:bg-wash'}`}
                        >
                          <Td>
                            <span className={`font-medium ${on ? 'text-ink' : 'text-ink-2'}`}>
                              {r.rm_id}
                            </span>
                            {on ? (
                              <span className="ml-1.5 text-micro text-ink-3">
                                {isTh ? 'กำลังดู' : 'viewing'}
                              </span>
                            ) : null}
                          </Td>
                          <Td right>
                            <span className="tnum font-medium text-ink">{thb(r.value, lang)}</span>
                            {/* แถบสัดส่วนของมูลค่าทั้งบริษัท — เทียบด้วยตาเร็วกว่าอ่านตัวเลข */}
                            <span className="mt-1 block h-1 w-full overflow-hidden rounded-in bg-rule">
                              <span
                                className="block h-full"
                                style={{
                                  width: `${
                                    data.value_total ? (r.value / data.value_total) * 100 : 0
                                  }%`,
                                  background: 'var(--s1)',
                                }}
                              />
                            </span>
                            {r.share_of_book != null ? (
                              <span className="mt-0.5 block text-micro text-ink-3">
                                {pct(r.share_of_book, 1)} {t('k.shareOfBook')}
                              </span>
                            ) : null}
                          </Td>
                          <Td right>{num(r.customers)}</Td>
                          <Td right>
                            {/* null = ไฟล์พอร์ตไม่ส่งค่านี้มา ไม่ใช่เท่าทุน (H-08 ไม่บังคับ) */}
                            {r.unrealized_pnl == null ? (
                              <span
                                className="text-small text-ink-3"
                                title={
                                  isTh
                                    ? 'ไฟล์พอร์ตไม่ได้ส่งกำไร/ขาดทุนของสินทรัพย์ชนิดนี้มา'
                                    : 'the portfolio file carries no P/L for this asset type'
                                }
                              >
                                {isTh ? 'ไม่มีข้อมูล' : 'n/a'}
                              </span>
                            ) : (
                              <>
                                <span
                                  className="tnum text-small"
                                  style={{
                                    color: r.unrealized_pnl < 0 ? 'var(--critical)' : 'var(--pos)',
                                  }}
                                >
                                  {r.unrealized_pnl >= 0 ? '+' : ''}
                                  {thb(r.unrealized_pnl, lang)}
                                </span>
                                {r.n_with_pnl < r.n_rows ? (
                                  <span className="mt-0.5 block text-micro text-ink-3">
                                    {isTh
                                      ? `จาก ${r.n_with_pnl}/${r.n_rows} รายการ`
                                      : `from ${r.n_with_pnl}/${r.n_rows} rows`}
                                  </span>
                                ) : null}
                              </>
                            )}
                          </Td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </Scroll>
              <p className="mt-2 text-micro text-ink-3">
                {t('k.allRmsTotal')} {num(data.holders_total)} {isTh ? 'คน' : 'customers'} ·{' '}
                {thb(data.value_total, lang)}
                {isTh ? ' · % ของบุ๊กคือสัดส่วนต่อมูลค่าพอร์ตทั้งหมดที่คนนั้นดูแล' : ''}
              </p>
            </section>

            {/* ---------------- ผู้ถือ ---------------- */}
            <section className="min-w-0">
              <Head
                note={
                  rm
                    ? isTh
                      ? `แสดงเฉพาะลูกค้าของ ${rm} · ทั้งบริษัทมี ${num(
                          data.holders_total,
                        )} คน ${thb(data.value_total, lang)}`
                      : `Only ${rm} customers · firm-wide ${num(
                          data.holders_total,
                        )} customers, ${thb(data.value_total, lang)}`
                    : isTh
                      ? 'เรียงตามมูลค่าที่ถือ · สัดส่วนของพอร์ตบอกว่าข่าวชิ้นนี้กระทบเขาแรงแค่ไหน'
                      : 'By value held · the portfolio share shows how much this news matters to them'
                }
                right={
                  rm ? (
                    <button
                      type="button"
                      onClick={() => setRm(undefined)}
                      className="tap rounded-in border border-rule px-2 py-0.5 text-micro text-ink-2 hover:text-ink"
                    >
                      {t('k.showAll')}
                    </button>
                  ) : undefined
                }
              >
                {rm
                  ? isTh
                    ? `ใครถืออยู่ — ลูกค้าของ ${rm}`
                    : `Who holds it — ${rm}`
                  : isTh
                    ? 'ใครถืออยู่'
                    : 'Who holds it'}
              </Head>
              <Scroll>
                <table className="w-full min-w-[560px] table-fixed border-collapse">
                  <colgroup>
                    <col className="w-[30%]" />
                    <col className="w-[12%]" />
                    <col className="w-[19%]" />
                    <col className="w-[16%]" />
                    <col className="w-[23%]" />
                  </colgroup>
                  <thead>
                    <tr>
                      <Th>{t('k.customers')}</Th>
                      <Th>{t('k.rm')}</Th>
                      <Th right>{isTh ? 'มูลค่าที่ถือ' : 'value held'}</Th>
                      <Th right>{isTh ? '% ของพอร์ต' : '% of portfolio'}</Th>
                      <Th right>{isTh ? 'กำไร/ขาดทุนตัวนี้' : 'P/L on this holding'}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.holders.map((h) => (
                      <tr key={h.customer_key}>
                        <Td>
                          <Link
                            to={`/customers/${encodeURIComponent(h.customer_key)}`}
                            className="tap font-medium text-ink hover:underline"
                          >
                            {h.customer_key}
                          </Link>
                          <span className="ml-1.5 text-micro text-ink-3">
                            {t(`persona.${h.persona}`, h.persona)}
                          </span>
                          {h.labels.map((l) => (
                            <span key={l} className="ml-1.5">
                              <InstrumentLabel label={l} />
                            </span>
                          ))}
                        </Td>
                        <Td>{h.rm_id}</Td>
                        <Td right>{thb(h.holding_value, lang)}</Td>
                        <Td right>{h.share_of_portfolio == null ? '—' : pct(h.share_of_portfolio)}</Td>
                        <Td right>
                          {/* กำไร/ขาดทุนของ "ตัวนี้" ไม่ใช่ของทั้งพอร์ต — ไฟล์บางชนิดสินทรัพย์
                              ไม่ส่งค่านี้มา (H-08 ไม่บังคับ) จึงต้องบอกตรง ๆ ว่าไม่มีข้อมูล */}
                          {h.unrealized_pnl == null ? (
                            <span
                              className="text-small text-ink-3"
                              title={
                                isTh
                                  ? 'ไฟล์พอร์ตไม่ได้ส่งกำไร/ขาดทุนของสินทรัพย์ชนิดนี้มา'
                                  : 'the portfolio file carries no P/L for this asset type'
                              }
                            >
                              {isTh ? 'ไม่มีข้อมูล' : 'n/a'}
                            </span>
                          ) : (
                            <span
                              className="tnum text-small"
                              style={{
                                color: h.unrealized_pnl < 0 ? 'var(--critical)' : 'var(--pos)',
                              }}
                              title={
                                isTh
                                  ? `ทั้งพอร์ตของเขา: ${t(`pnl.${h.unrealized_state}`, h.unrealized_state)}`
                                  : `whole portfolio: ${t(`pnl.${h.unrealized_state}`, h.unrealized_state)}`
                              }
                            >
                              {h.unrealized_pnl >= 0 ? '+' : ''}
                              {thb(h.unrealized_pnl, lang)}
                            </span>
                          )}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Scroll>
              {rm ? (
                <p className="mt-2 text-micro text-ink-3">
                  {isTh
                    ? `ลูกค้าของ ${rm} ที่ถือตัวนี้ ${num(data.holders.length)} คน`
                    : `${num(data.holders.length)} customers of ${rm} hold it`}
                </p>
              ) : data.holders_total > data.holders.length ? (
                <p className="mt-2 text-micro text-ink-3">
                  {isTh
                    ? `แสดง ${num(data.holders.length)} จาก ${num(data.holders_total)} คน`
                    : `showing ${num(data.holders.length)} of ${num(data.holders_total)}`}
                </p>
              ) : null}

              {data.watchers.length ? (
                <div className="mt-6 border-t border-rule pt-3">
                  <button
                    type="button"
                    onClick={() => setShowWatchers((v) => !v)}
                    className="tap text-small text-ink-2 hover:text-ink"
                  >
                    {showWatchers ? '−' : '+'}{' '}
                    {isTh
                      ? `เคยเทรดใน 90 วันแต่ตอนนี้ไม่ถือ ${data.watchers.length} คน${
                          rm ? ` (เฉพาะของ ${rm})` : ''
                        }`
                      : `${data.watchers.length} traded it recently but hold none now${
                          rm ? ` (${rm} only)` : ''
                        }`}
                  </button>
                  {showWatchers ? (
                    <ul className="mt-2 border-t border-rule">
                      {data.watchers.map((w) => (
                        <li
                          key={w.customer_key}
                          className="flex items-baseline gap-3 border-b border-rule py-1.5 last:border-0"
                        >
                          <Link
                            to={`/customers/${encodeURIComponent(w.customer_key)}`}
                            className="tap text-small font-medium text-ink hover:underline"
                          >
                            {w.customer_key}
                          </Link>
                          <span className="text-micro text-ink-3">{w.rm_id}</span>
                          <span className="text-micro text-ink-3">
                            {t(`persona.${w.persona}`, w.persona)}
                          </span>
                          <span className="tnum ml-auto text-small text-ink-2">
                            {isTh ? 'เทรดล่าสุด' : 'last traded'} {w.last_traded}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : null}
            </section>
          </div>

          <p className="mt-10 max-w-[80ch] text-micro leading-relaxed text-ink-3">
            {isTh
              ? 'ข้อมูลการถือครองเป็นภาพ ณ วันที่ระบุบนแถบด้านบน ลูกค้าอาจซื้อขายไปแล้วหลังจากนั้น · ' +
                'กำไร/ขาดทุนมาจากคอลัมน์ thb_unrealized_avg ในไฟล์พอร์ต (ยังไม่ขาย ณ วัน snapshot ไม่ใช่ราคาเรียลไทม์) ' +
                'ไฟล์ส่งค่านี้มาเฉพาะหุ้นต่างประเทศ ออปชัน และตราสารหนี้ต่างประเทศ — หุ้นไทย กองทุน และคริปโตไม่มีค่ามา จึงขึ้นว่าไม่มีข้อมูล'
              : 'Holdings are a snapshot as of the date in the top bar. P/L comes from the thb_unrealized_avg column ' +
                'in the portfolio file (unrealised at the snapshot date, not live prices) and is only provided for ' +
                'offshore equity, options and offshore bonds — Thai equity, funds and crypto carry no value.'}
          </p>
        </>
      )}
    </div>
  )
}
