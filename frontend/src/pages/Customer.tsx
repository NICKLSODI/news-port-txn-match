import { Link, useParams } from 'react-router-dom'
import { useCustomer } from '../lib/api'
import type { Customer, PortfolioStyle, StyleKey } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jparse, num, pct, thb, dayMonth } from '../lib/format'
import { HBars } from '../components/charts'
import {
  Code,
  Empty,
  Figure,
  Head,
  InstrumentLabel,
  LevelBadge,
  Loading,
  Row,
  Scroll,
  Stat,
  Td,
  Th,
} from '../components/ui'

/** สไตล์พอร์ต — ป้ายอย่างเดียวไม่พอ ต้องมีตัวเลขที่ทำให้ได้ป้ายนั้นอยู่ข้าง ๆ เสมอ
 *
 *  เซลล์ต้องเถียงกับลูกค้าได้ว่าทำไมถึงเสนอแบบนี้ ป้ายที่อธิบายที่มาไม่ได้คือกล่องดำ
 *  ที่ไม่มีใครกล้าใช้ — และเมื่อข้อมูลไม่พอ ต้องพูดว่าไม่พอ ไม่ใช่เดาให้ดูสมบูรณ์
 */
function StyleBlock({ s, rows }: { s: PortfolioStyle; rows: NonNullable<Customer['dividend_rows']> }) {
  const { lang, isTh } = useI18n()
  const label = STYLE_TH[s.style]
  const unknown = s.style === 'unknown'

  return (
    <section className="mt-9 border-t border-rule pt-6">
      <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
        <div className="min-w-0">
          <p className="text-micro text-ink-3">{isTh ? 'สไตล์พอร์ต' : 'Portfolio style'}</p>
          <p className="mt-0.5 text-h2 font-semibold text-ink">{isTh ? label.th : label.en}</p>
          <p className="mt-1 max-w-[46ch] text-small text-ink-2">{isTh ? label.useTh : label.useEn}</p>
        </div>
        {!unknown ? (
          <div className="flex flex-wrap gap-x-10 gap-y-4">
            <Stat
              label={isTh ? 'ปันผลทั้งปีของพอร์ต' : 'portfolio yield'}
              value={`${s.yield_portfolio?.toFixed(1)}%`}
              sub={isTh ? `ค่ากลาง ${s.median_yield.toFixed(1)}%` : `median ${s.median_yield.toFixed(1)}%`}
            />
            <Stat
              label={isTh ? 'วัดจากพอร์ตส่วนที่มีข้อมูล' : 'coverage'}
              value={pct(s.coverage, 0)}
              sub={thb(s.covered, lang)}
            />
            <Stat label={isTh ? 'ความถี่เทรด' : 'trading'} value={t2(s.trade_frequency, isTh)} />
          </div>
        ) : null}
      </div>

      {unknown ? (
        <p className="mt-4 text-small text-ink-3">
          {isTh
            ? `มีข้อมูลปันผลแค่ ${pct(s.coverage, 0)} ของพอร์ต ต่ำกว่าเกณฑ์ที่จะสรุปได้ — INVX Data Book ครอบคลุมเฉพาะหุ้นไทย พอร์ตที่เป็นหุ้นนอกหรือกองทุนจึงยังวัดไม่ได้`
            : `Only ${pct(s.coverage, 0)} of this portfolio has dividend data — the INVX Data Book covers Thai stocks only.`}
        </p>
      ) : rows.length ? (
        <>
          <p className="mt-5 text-small text-ink-2">
            {isTh ? 'เงินปันผลที่จะได้รอบนี้ ' : 'Dividend due this round '}
            <b className="tnum text-ink">{thb(s.interim, lang)}</b>
            <span className="text-ink-3">
              {isTh ? ` · จากหุ้น ${rows.length} ตัว` : ` · from ${rows.length} holdings`}
            </span>
          </p>
          <Scroll className="mt-2 max-h-[260px] overflow-y-auto">
            <table className="w-full min-w-[520px] border-collapse">
              <thead>
                <tr>
                  <Th>{t2('entity', isTh)}</Th>
                  <Th right>{isTh ? 'ถือ' : 'held'}</Th>
                  <Th right>{isTh ? 'ปันผลรอบนี้' : 'this round'}</Th>
                  <Th right>69F</Th>
                  <Th>XD</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.entity} className="hover:bg-wash">
                    <Td>
                      <span className="tnum font-medium text-ink">{r.entity}</span>
                      <div className="text-micro text-ink-3">
                        {r.rating}
                        {/* Estimated คือ "คาดว่า" ยังไม่ประกาศ — ห้ามให้อ่านเหมือนตัวเลขที่ยืนยันแล้ว */}
                        {r.remark === 'Estimated' ? (isTh ? ' · คาดการณ์' : ' · estimated') : ''}
                      </div>
                    </Td>
                    <Td right>{thb(r.holding_value, lang)}</Td>
                    <Td right>
                      <span className="tnum font-medium text-ink">{thb(r.dividend, lang)}</span>
                    </Td>
                    <Td right>{r.yield_forecast}%</Td>
                    <Td>{r.xd_date}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        </>
      ) : null}
    </section>
  )
}

const STYLE_TH: Record<StyleKey, { th: string; en: string; useTh: string; useEn: string }> = {
  income: {
    th: 'นักลงทุนปันผล', en: 'Income investor',
    useTh: 'เสนอหุ้นปันผลได้เต็มปาก สนใจกระแสเงินสดมากกว่าราคาขึ้นลง',
    useEn: 'Dividend ideas land well — cares about cash flow over price moves.',
  },
  div_trader: {
    th: 'เก็บปันผลแบบเทรด', en: 'Dividend trader',
    useTh: 'สนใจจังหวะ XD มากกว่าตัวหุ้น — บอกวันหมดสิทธิ์ก่อนบอกพื้นฐาน',
    useEn: 'Cares about XD timing more than the name — lead with the deadline.',
  },
  growth: {
    th: 'ถือยาวหวังราคา', en: 'Growth holder',
    useTh: 'อย่ายัดข้อเสนอปันผล เขาถือยาวเพื่อส่วนต่างราคา',
    useEn: 'Do not push dividend pitches — holds long for capital gain.',
  },
  speculate: {
    th: 'เก็งกำไร', en: 'Speculative',
    useTh: 'ข้อเสนอปันผลมักถูกเมิน คุยเรื่องจังหวะและข่าวได้ผลกว่า',
    useEn: 'Dividend pitches get ignored — news and timing work better.',
  },
  unknown: {
    th: 'ยังบอกไม่ได้', en: 'Not enough data',
    useTh: 'ยังไม่มีข้อมูลปันผลของสิ่งที่เขาถือมากพอจะสรุปสไตล์',
    useEn: 'Not enough dividend data on what this customer holds.',
  },
}

/** คำแปลสั้น ๆ ที่ยังไม่มีใน i18n — ไม่ยัดเข้าไฟล์กลางเพราะใช้ที่เดียว */
function t2(k: string, isTh: boolean): string {
  const m: Record<string, [string, string]> = {
    very_active: ['เทรดบ่อยมาก', 'very active'],
    active: ['เทรดบ่อย', 'active'],
    passive: ['เทรดน้อย', 'passive'],
    inactive: ['ไม่เทรดแล้ว', 'inactive'],
    entity: ['หุ้น', 'stock'],
  }
  const v = m[k]
  return v ? (isTh ? v[0] : v[1]) : k
}

export default function CustomerPage() {
  const { key } = useParams()
  const { t, lang, isTh } = useI18n()
  const { data: c, isLoading } = useCustomer(key)

  if (isLoading) return <Loading rows={10} />
  if (!c) return <Empty />

  const mix = jparse<Record<string, number>>(c.asset_mix, {})
  const sect = jparse<Record<string, number>>(c.sector_exposure, {})
  const watch = jparse<Record<string, string>>(c.watchlist, {})

  return (
    <div>
      <Link to="/customers" className="tap text-small text-ink-3 hover:text-ink">
        ← {t('nav.customers')}
      </Link>

      <header className="mt-5">
        <h1 className="tnum text-h1 font-semibold text-ink">{c.customer_key}</h1>
        <p className="mt-1 flex flex-wrap gap-x-3 text-small text-ink-2">
          <span>{t(`persona.${c.persona}`, c.persona)}</span>
          <span>{t(`tier.${c.portfolio_tier}`)}</span>
          <span>{t(`freq.${c.trade_frequency}`)}</span>
          <span>{t(`pnl.${c.unrealized_state}`)}</span>
          <span>{c.rm_id}</span>
        </p>
      </header>

      <div className="mt-7 flex flex-wrap items-end gap-x-12 gap-y-6 border-b border-rule pb-6">
        <Figure value={thb(c.portfolio_value, lang)} label={t('k.portfolio')} />
        <div className="flex flex-wrap gap-x-10 gap-y-4">
          <Stat label={t('k.holdings')} value={num(c.n_holdings)} />
          <Stat label={t('k.watchlist')} value={num(c.n_watchlist)} />
          <Stat
            label={t('k.lastTrade')}
            value={c.days_since_last_trade < 9999 ? `${c.days_since_last_trade}d` : '—'}
            sub={`${num(c.txn_count)} ${isTh ? 'ธุรกรรม 6 เดือน' : 'txn in 6 months'}`}
          />
        </div>
      </div>

      {c.style ? <StyleBlock s={c.style} rows={c.dividend_rows ?? []} /> : null}

      <div className="mt-9 grid gap-x-12 gap-y-9 lg:grid-cols-2">
        <section>
          <Head>{isTh ? 'สัดส่วนสินทรัพย์' : 'Asset mix'}</Head>
          <div className="border-t border-rule">
            <HBars
              items={Object.entries(mix)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => ({ key: k, label: t(`ac.${k}`, k), value: v }))}
              max={1}
              format={(v) => pct(v, 1)}
            />
          </div>
        </section>

        <section>
          <Head>{isTh ? 'กลุ่มอุตสาหกรรมที่ถือ' : 'Sectors held'}</Head>
          {Object.keys(sect).length ? (
            <div className="border-t border-rule">
              <HBars
                items={Object.entries(sect)
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => ({ key: k, label: k, value: v }))}
                max={Math.max(0.1, ...Object.values(sect))}
                format={(v) => pct(v, 1)}
                color="var(--s3)"
              />
            </div>
          ) : (
            <p className="border-t border-rule py-4 text-small text-ink-3">
              {isTh ? 'ไม่มีหุ้นไทยที่อยู่ใน Coverage List' : 'No Thai holdings in the coverage list'}
            </p>
          )}
        </section>
      </div>

      <section className="mt-12">
        <Head right={<span className="tnum text-body font-semibold text-ink">{num(c.matches?.length)}</span>}>
          {isTh ? 'ข่าวที่ระบบเสนอให้ติดต่อ' : 'Articles the system surfaced'}
        </Head>
        {!c.matches?.length ? (
          <Empty />
        ) : (
          <Scroll>
            <table className="w-full min-w-[700px] border-collapse">
              <thead>
                <tr>
                  <Th>{t('k.articles')}</Th>
                  <Th>{t('k.level')}</Th>
                  <Th>{t('k.reason')}</Th>
                  <Th right>{t('k.date')}</Th>
                  <Th right>{t('k.score')}</Th>
                </tr>
              </thead>
              <tbody>
                {c.matches.map((m) => (
                  <tr key={m.article_id} className="hover:bg-wash">
                    <Td className="max-w-[340px]">
                      <Link
                        to={`/news/${encodeURIComponent(m.article_id)}`}
                        className="line-clamp-2 font-medium text-ink hover:underline"
                      >
                        {m.title}
                      </Link>
                      <div className="text-micro text-ink-3">{m.subcategory}</div>
                    </Td>
                    <Td>
                      <LevelBadge level={m.level} />
                    </Td>
                    <Td className="max-w-[300px] text-ink-2">{isTh ? m.reason_th : m.reason_en}</Td>
                    <Td right className="text-ink-3">
                      {dayMonth(m.trigger_at, lang)}
                    </Td>
                    <Td right className="font-semibold">
                      {m.score.toFixed(0)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        )}
      </section>

      <div className="mt-12 grid gap-x-12 gap-y-9 lg:grid-cols-2">
        <section className="min-w-0">
          <Head>{t('k.holdings')}</Head>
          <Scroll className="max-h-[420px] overflow-y-auto">
            <table className="w-full min-w-[360px] border-collapse">
              <thead>
                <tr>
                  <Th>{t('k.entity')}</Th>
                  <Th right>{t('k.value')}</Th>
                </tr>
              </thead>
              <tbody>
                {c.holding_rows?.map((hd, i) => (
                  <tr key={`${hd.product_code}-${i}`} className="hover:bg-wash">
                    <Td>
                      <span className="tnum font-medium text-ink">{hd.entity ?? '—'}</span>
                      {hd.entity !== hd.product_code ? (
                        <span className="tnum ml-1.5 text-micro text-ink-3">{hd.product_code}</span>
                      ) : null}
                      <div className="flex flex-wrap items-center gap-x-2">
                        <span className="text-micro text-ink-3">
                          {t(`ac.${hd.asset_class}`, hd.asset_class)}
                        </span>
                        <InstrumentLabel label={hd.instrument_label} />
                      </div>
                    </Td>
                    <Td right>{thb(hd.holding_value, lang)}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        </section>

        <div className="min-w-0 space-y-9">
          <section>
            <Head
              note={isTh ? 'เคยเทรดใน 90 วัน ตอนนี้ไม่ถือแล้ว' : 'traded within 90 days, no longer held'}
              right={<span className="tnum text-body font-semibold text-ink">{num(Object.keys(watch).length)}</span>}
            >
              {t('k.watchlist')}
            </Head>
            {Object.keys(watch).length ? (
              <dl className="border-t border-rule">
                {Object.entries(watch)
                  .sort((a, b) => b[1].localeCompare(a[1]))
                  .slice(0, 12)
                  .map(([k, v]) => (
                    <Row key={k} k={<Code>{k}</Code>} v={v} />
                  ))}
              </dl>
            ) : (
              <p className="border-t border-rule py-4 text-small text-ink-3">{t('msg.empty')}</p>
            )}
          </section>

          <section className="min-w-0">
            <Head>{isTh ? 'ธุรกรรมล่าสุด' : 'Recent transactions'}</Head>
            <Scroll className="max-h-[300px] overflow-y-auto">
              <table className="w-full min-w-[380px] border-collapse">
                <thead>
                  <tr>
                    <Th>{t('k.date')}</Th>
                    <Th>{t('k.entity')}</Th>
                    <Th>{isTh ? 'ประเภท' : 'Type'}</Th>
                    <Th right>{t('k.value')}</Th>
                  </tr>
                </thead>
                <tbody>
                  {c.recent_txn?.map((x, i) => (
                    <tr key={i} className="hover:bg-wash">
                      <Td className="tnum text-ink-3">{x.txn_date}</Td>
                      <Td className="tnum">{x.entity ?? x.product_code}</Td>
                      <Td>
                        <span
                          className="text-micro font-medium"
                          style={{
                            color:
                              x.txn_direction === 'INCREASE'
                                ? 'var(--pos)'
                                : x.txn_direction === 'DECREASE'
                                  ? 'var(--critical)'
                                  : 'var(--ink-3)',
                          }}
                        >
                          {x.txn_type}
                        </span>
                      </Td>
                      <Td right>{thb(x.txn_value, lang)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Scroll>
          </section>
        </div>
      </div>
    </div>
  )
}
