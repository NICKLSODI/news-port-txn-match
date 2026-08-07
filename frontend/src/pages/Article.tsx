import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useArticle, useArticleMatches } from '../lib/api'
import type { Article, Evidence, GradeCheck, Match } from '../lib/api'
import { jparse, num, thb, time, fullDate, LEVEL_COLOR } from '../lib/format'
import { useI18n } from '../lib/i18n'
import { LevelStack } from '../components/charts'
import Briefing from '../components/Briefing'
import {
  Button,
  Code,
  Grade,
  Empty,
  Figure,
  Head,
  InstrumentLabel,
  LevelBadge,
  LevelDot,
  Loading,
  Row,
  Scroll,
  Seg,
  Segmented,
  Td,
  Th,
  Urgency,
} from '../components/ui'

const PAGE = 100

/**
 * บอกเหตุผลที่ข่าวชิ้นนี้ไม่มีใครเข้าเกณฑ์ — ไม่ใช่ปล่อยให้เดาว่าระบบพัง
 *
 * ข่าวสรุปรวมจับคู่ได้ถึง L4 (R6.13) ข้อที่เป็นประเด็นภาพรวมล้วน ๆ จึงไม่ถึงใคร
 * และ R6.14 ตั้งเกณฑ์คะแนนไว้กันข่าว macro เหมาะกับลูกค้าทุกคนแบบไร้ความหมาย
 */
function noMatchReason(a: Article | undefined, isTh: boolean): string {
  if (!a) return ''
  const ents = jparse<string[]>(a.entity, [])
  const secs = jparse<string[]>(a.sector, [])
  const macro = jparse<{ topic: string }[]>(a.macro_topic, [])

  if (!ents.length && !secs.length && macro.length) {
    const topics = macro.map((m) => m.topic).join(' · ')
    return isTh
      ? `ข้อนี้เป็นประเด็นภาพรวม (${topics}) ไม่ได้เอ่ยชื่อหุ้นหรือกองทุน — ข่าวสรุปรวมจับคู่ได้ถึงระดับ “ถือหุ้นที่เกี่ยวข้องกัน” เท่านั้น (R6.13) ประเด็นภาพรวมจึงไม่ส่งถึงใคร กันไม่ให้ข่าวเดียวเด้งหาลูกค้าทุกคน (R6.14)`
      : `This item is a macro topic (${topics}) with no company or fund named. A digest matches only down to “holds a related stock” (R6.13), so macro alone reaches nobody — that keeps one story from pinging every customer (R6.14).`
  }
  if (!ents.length && !secs.length) {
    return isTh
      ? 'ระบบอ่านไม่พบชื่อหุ้น กองทุน หรือประเด็นที่เชื่อมกับพอร์ตลูกค้าได้ในข้อนี้ — ไม่มั่นใจแล้วไม่เดา'
      : 'No company, fund or topic in this item could be linked to a portfolio — when unsure, the system does not guess.'
  }
  return isTh
    ? `มีสินทรัพย์ที่อ่านออก แต่ไม่มีลูกค้าคนไหนได้คะแนนถึงเกณฑ์ ${num(50)} (R6.14)`
    : `Instruments were recognised, but no customer scored above the ${num(50)} cut-off (R6.14).`
}

export default function ArticlePage() {
  const { id } = useParams()
  // กดเข้ามาจากหน้าไหน ปุ่มย้อนกลับต้องพากลับหน้านั้น — เดิมเด้งไป /news เสมอ
  // ทำให้เมนูข้างซ้ายสลับไปไฮไลต์ "ข่าวทั้งหมด" ทั้งที่ผู้ใช้มาจากหน้าวันนี้
  const from = (useLocation().state as { from?: string } | null)?.from
  const back = !from || from.startsWith('/news')
    ? { to: '/news', key: 'nav.news' }
    : from.startsWith('/rm') || from === '/'      // หน้าแรกคือ "งานวันนี้ของ RM"
      ? { to: from, key: 'nav.rm' }
      : from.startsWith('/customers')
        ? { to: from, key: 'nav.customers' }
        : from.startsWith('/reports')
          ? { to: from, key: 'nav.reports' }
          : from.startsWith('/stock')
            ? { to: from, key: 'nav.stock' }
            : { to: from, key: 'nav.today' }
  const { t, lang, isTh } = useI18n()
  const { data: a, isLoading } = useArticle(id)
  const [rm, setRm] = useState<string>()
  const [persona, setPersona] = useState<string>()
  const [level, setLevel] = useState<string>()
  const [limit, setLimit] = useState(PAGE)
  const [openRow, setOpenRow] = useState<string>()
  const [copied, setCopied] = useState(false)

  const { data: m, isLoading: mLoading } = useArticleMatches(id, { rm, persona, level, limit })

  if (isLoading) return <Loading rows={10} />
  if (!a) return <Empty />

  const entities = jparse<string[]>(a.entity, [])
  const sectors = jparse<string[]>(a.sector, [])
  const macro = jparse<{ topic: string; keyword: string }[]>(a.macro_topic, [])
  const rows = m?.items ?? []

  const copyList = () => {
    const text = rows
      .map((r, i) => `${i + 1}. ${r.customer_key}\t${r.rm_id}\t${r.score}\t${isTh ? r.reason_th : r.reason_en}`)
      .join('\n')
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    })
  }

  return (
    <div>
      <Link to={back.to} className="tap text-small text-ink-3 hover:text-ink">
        ← {t(back.key)}
      </Link>

      {/* ---------------- บทความ ---------------- */}
      <article className="mt-5 max-w-[74ch]">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-micro text-ink-3">
          <span>{a.subcategory_name || a.subcategory}</span>
          <span>{t(`mode.${a.mode}`)}</span>
          <span className="tnum">
            {fullDate(a.trigger_at, lang)} {time(a.trigger_at)}
          </span>
          {a.record_type === 'segment' ? (
            <span className="tnum">
              {isTh ? 'ข้อ' : 'item'} {a.segment_no}
            </span>
          ) : null}
          <Urgency urgency={a.urgency} />
        </div>

        <h1 className="mt-2 text-h1 leading-tight font-semibold text-ink">{a.title}</h1>

        {a.parent ? (
          <p className="mt-2 text-small text-ink-3">
            {isTh ? 'มาจาก' : 'from'}{' '}
            <Link to={`/news/${encodeURIComponent(a.parent.article_id)}`} className="underline">
              {a.parent.title}
            </Link>
          </p>
        ) : null}

        {a.segment_text ? (
          <p className="mt-3 text-body leading-relaxed text-ink-2">{a.segment_text}</p>
        ) : a.summary ? (
          <p className="mt-3 line-clamp-5 text-body leading-relaxed text-ink-2">{a.summary}</p>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center gap-1">
          {entities.map((e) => (
            <Code key={e}>{e}</Code>
          ))}
          {sectors.map((s) => (
            <Code key={s}>{s}</Code>
          ))}
          {macro.map((x) => (
            <Code key={x.topic}>{x.topic}</Code>
          ))}
        </div>

        <p className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-micro text-ink-3">
          {a.url_full ? (
            <a
              href={a.url_full}
              target="_blank"
              rel="noreferrer"
              className="tap font-medium text-ink underline decoration-rule-strong underline-offset-2 hover:decoration-ink"
            >
              {t('a.openArticle')}
            </a>
          ) : null}
        </p>
      </article>

      {/* ---------------- เกรดจากตัวตรวจอัตโนมัติ (อ่านอย่างเดียว) ---------------- */}
      <GradeBar a={a} />

      <Briefing articleId={a.article_id} />

      {/* ---------------- ข้อย่อยของ Brief ---------------- */}
      {a.segments && a.segments.length > 0 ? (
        <section className="mt-10">
          <Head>{isTh ? `ข่าวนี้มี ${a.segments.length} หัวข้อย่อย` : `${a.segments.length} sub-items`}</Head>
          <ul className="border-t border-rule">
            {a.segments.map((s) => {
              const es = jparse<string[]>(s.entity, [])
              return (
                <li key={s.article_id} className="border-b border-rule">
                  <Link
                    to={`/news/${encodeURIComponent(s.article_id)}`}
                    className="tap flex items-start gap-4 py-2.5 hover:bg-wash"
                  >
                    <span className="tnum mt-0.5 w-4 shrink-0 text-small text-ink-3">{s.segment_no}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-small leading-relaxed text-ink-2">
                        {s.segment_text?.slice(0, 190)}
                        {(s.segment_text?.length ?? 0) > 190 ? '…' : ''}
                      </span>
                      {es.length ? (
                        <span className="mt-1 flex flex-wrap gap-1">
                          {es.map((e) => (
                            <Code key={e}>{e}</Code>
                          ))}
                        </span>
                      ) : null}
                    </span>
                    <span className="tnum shrink-0 text-body font-semibold text-ink">{num(s.n_matches)}</span>
                  </Link>
                </li>
              )
            })}
          </ul>
        </section>
      ) : null}

      {/* ---------------- ผลการจับคู่ ---------------- */}
      <section className="mt-12">
        <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-5">
          <Figure
            value={num(m?.total ?? 0)}
            label={isTh ? 'ลูกค้าที่ควรติดต่อจากข่าวชิ้นนี้' : 'customers to contact for this article'}
            sub={isTh ? 'เรียงจากคนที่ควรโทรก่อน' : 'ordered by who to call first'}
          />
          {a.level_summary && a.level_summary.length > 0 ? (
            <div className="w-full max-w-[420px] min-w-[240px]">
              <LevelStack items={a.level_summary} />
            </div>
          ) : null}
        </div>

        {/* ตัวกรอง */}
        <div className="mt-7 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-rule pt-4">
          <Segmented>
            <Seg active={!level} onClick={() => setLevel(undefined)}>
              {t('a.all')}
            </Seg>
            {a.level_summary?.map((l) => (
              <Seg key={l.level} active={level === l.level} onClick={() => setLevel(l.level)} count={l.n}>
                <LevelDot level={l.level} />
                {t(`lvl.${l.level}`)}
              </Seg>
            ))}
          </Segmented>

          <Segmented>
            <Seg active={!rm} onClick={() => setRm(undefined)}>
              {t('k.rm')}
            </Seg>
            {a.rm_summary?.map((r) => (
              <Seg key={r.rm_id} active={rm === r.rm_id} onClick={() => setRm(r.rm_id)} count={r.n}>
                {r.rm_id}
              </Seg>
            ))}
          </Segmented>

          {a.persona_summary && a.persona_summary.length > 1 ? (
            <Segmented>
              <Seg active={!persona} onClick={() => setPersona(undefined)}>
                {t('k.persona')}
              </Seg>
              {a.persona_summary.map((p) => (
                <Seg
                  key={p.persona}
                  active={persona === p.persona}
                  onClick={() => setPersona(p.persona)}
                  count={p.n}
                >
                  {t(`persona.${p.persona}`, p.persona)}
                </Seg>
              ))}
            </Segmented>
          ) : null}

          <span className="ml-auto">
            <Button onClick={copyList}>{copied ? t('a.copied') : t('a.copy')}</Button>
          </span>
        </div>

        {mLoading ? (
          <div className="mt-4">
            <Loading rows={8} />
          </div>
        ) : rows.length === 0 ? (
          <Empty>
            <p>{t('msg.empty.matches')}</p>
            <p className="mx-auto mt-3 max-w-[54ch] text-small">{noMatchReason(a, isTh)}</p>
          </Empty>
        ) : (
          <>
            <Scroll className="mt-4">
              <table className="w-full min-w-[860px] border-collapse">
                <thead>
                  <tr>
                    <Th className="w-9" right>
                      #
                    </Th>
                    <Th>{t('k.customers')}</Th>
                    <Th>{t('k.level')}</Th>
                    <Th>{t('k.reason')}</Th>
                    <Th right>{t('k.value')}</Th>
                    <Th right>{t('k.portfolio')}</Th>
                    <Th>{t('k.persona')}</Th>
                    <Th right>{t('k.score')}</Th>
                    <Th className="w-8" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <MatchRow
                      key={r.customer_key}
                      r={r}
                      i={i}
                      open={openRow === r.customer_key}
                      onToggle={() => setOpenRow(openRow === r.customer_key ? undefined : r.customer_key)}
                    />
                  ))}
                </tbody>
              </table>
            </Scroll>
            {m && m.total > rows.length ? (
              <p className="mt-5 text-center">
                <Button onClick={() => setLimit(limit + PAGE)}>
                  {t('a.showMore')} · {num(m.total - rows.length)}
                </Button>
              </p>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}

function MatchRow({ r, i, open, onToggle }: { r: Match; i: number; open: boolean; onToggle: () => void }) {
  const { t, lang, isTh } = useI18n()
  const ev = jparse<Evidence>(r.evidence, { hits: [], factors: {}, customer: {}, coverage: {} })
  return (
    <>
      <tr className={open ? 'bg-wash' : 'hover:bg-wash'}>
        <Td right className="text-ink-3">
          {i + 1}
        </Td>
        <Td>
          <Link to={`/customers/${r.customer_key}`} className="tnum font-medium text-ink hover:underline">
            {r.customer_key}
          </Link>
          <div className="text-micro text-ink-3">
            {r.rm_id} · {t(`tier.${r.portfolio_tier}`)}
          </div>
        </Td>
        <Td>
          <LevelBadge level={r.level} />
        </Td>
        <Td className="max-w-[400px]">
          <div className="text-ink-2">{isTh ? r.reason_th : r.reason_en}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2">
            <span className="tnum text-micro text-ink-3">{r.matched_entity}</span>
            <InstrumentLabel label={r.instrument_label} />
            {ev.coverage?.rating ? (
              <span
                className="text-micro text-ink-3"
                title={`Target ${ev.coverage.target_price ?? '—'} · ESG ${ev.coverage.esg ?? '—'}`}
              >
                {ev.coverage.rating}
              </span>
            ) : null}
          </div>
        </Td>
        <Td right>{thb(r.holding_value, lang)}</Td>
        <Td right className="text-ink-2">
          {thb(r.portfolio_value, lang)}
        </Td>
        <Td className="text-ink-2">{t(`persona.${r.persona}`, r.persona)}</Td>
        <Td right className="text-body font-semibold">
          {r.score.toFixed(0)}
        </Td>
        <Td>
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            title={open ? t('a.hideEvidence') : t('a.evidence')}
            className="tap text-ink-3 hover:text-ink"
          >
            {open ? '−' : '+'}
          </button>
        </Td>
      </tr>
      {open ? (
        <tr className="mp-in">
          <td />
          <td colSpan={8} className="border-b border-rule pt-1 pb-5 pl-3">
            <div className="grid max-w-[900px] gap-x-12 gap-y-5 md:grid-cols-2">
              <div>
                <h4 className="mb-1.5 text-small font-semibold text-ink">
                  {isTh ? 'เกี่ยวข้องยังไงบ้าง' : 'How they relate'}
                </h4>
                <ul className="space-y-1">
                  {ev.hits.map((hit, k) => (
                    <li key={k} className="flex items-start gap-2 text-small">
                      {/* deslop-ignore-next-line 19 — จุด 8px แบน ไม่มีวงเรือง */}
                      <span className="mt-1.5 size-2 shrink-0 rounded-full" style={{ background: LEVEL_COLOR[hit.level] }} />
                      <span className="min-w-0">
                        <span className="text-ink-2">{isTh ? hit.th : hit.en}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="mb-1.5 text-small font-semibold text-ink">
                  {isTh ? 'ทำไมอยู่อันดับนี้' : 'Why this rank'}
                </h4>
                <dl>
                  <Row k={isTh ? 'ความเกี่ยวข้อง' : 'relevance'} v={String(ev.factors.base)} />
                  <Row k={isTh ? '× มูลค่าที่ถือ' : '× holding value'} v={String(ev.factors.value_factor)} />
                  <Row
                    k={`× ${t('k.importance')} (${ev.factors.importance})`}
                    v={String(ev.factors.importance_factor)}
                  />
                  <Row
                    k={`× ${t('k.urgency')} (${t(`u.${ev.factors.urgency}`, String(ev.factors.urgency))})`}
                    v={String(ev.factors.urgency_factor)}
                  />
                  <Row
                    k={`× ${isTh ? 'ความสด' : 'recency'}${
                      ev.factors.recency_days !== null ? ` (${ev.factors.recency_days}d)` : ''
                    }`}
                    v={String(ev.factors.recency_factor)}
                  />
                  <Row
                    k={`× ${isTh ? 'โบนัสแตะหลายจุด' : 'multi-hit bonus'} (${ev.factors.n_hits})`}
                    v={String(ev.factors.multi_hit_bonus)}
                  />
                  <Row k={t('k.score')} v={<b>{r.score.toFixed(1)}</b>} />
                </dl>
                <p className="mt-2 flex flex-wrap gap-x-3 text-micro text-ink-3">
                  <span>{t(`freq.${r.trade_frequency}`)}</span>
                  <span>{t(`pnl.${r.unrealized_state}`)}</span>
                  <span>
                    {t('k.holdings')} {r.n_holdings}
                  </span>
                  <span>
                    {t('k.watchlist')} {r.n_watchlist}
                  </span>
                  {r.days_since_last_trade < 9999 ? (
                    <span>
                      {t('k.lastTrade')} {r.days_since_last_trade}d
                    </span>
                  ) : null}
                </p>
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  )
}


/** GAP-21 — ไม่มีปุ่มอนุมัติ แถบนี้บอกแค่ว่าหลักฐานแน่นแค่ไหน และแน่นเพราะอะไร */
function GradeBar({ a }: { a: Article }) {
  const { t, isTh } = useI18n()
  const [open, setOpen] = useState(false)
  const g = a.auto_grade ?? 'unknown'
  // ข่าวที่หลักฐานชัดอยู่แล้วไม่ต้องประกาศอะไร — บอกเฉพาะตอนที่ควรเปิดดู
  if (g !== 'weak') return null
  const checks = jparse<GradeCheck[]>(a.auto_checks ?? null, [])
  const reason = (isTh ? a.auto_reason_th : a.auto_reason_en) ?? ''

  return (
    <div className="mt-6 border-y border-rule py-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Grade grade={g} />
        <p className="min-w-0 flex-1 text-small text-ink-2">{reason}</p>
        {checks.length ? (
          <button type="button" onClick={() => setOpen(!open)} className="tap text-micro text-ink-3 hover:text-ink">
            {t('g.checks')} {checks.length} {open ? '−' : '+'}
          </button>
        ) : null}
      </div>
      {open ? (
        <ul className="mp-in mt-2 space-y-1">
          {checks.map((c, i) => (
            <li key={i} className="flex items-start gap-2 text-small">
              <span
                className="mt-0.5 w-3 shrink-0 text-center text-micro"
                style={{ color: c.ok ? 'var(--pos)' : 'var(--serious)' }}
              >
                {c.ok ? '✓' : '×'}
              </span>
              <span className="text-ink-2">{isTh ? c.th : c.en}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
