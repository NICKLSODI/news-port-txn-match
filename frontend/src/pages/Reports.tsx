import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCoverage, useRelated, useUnmapped, useVerification } from '../lib/api'
import type { GradeCheck, Severity } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jparse, num } from '../lib/format'
import { HBars, Meter } from '../components/charts'
import { Code, Empty, Grade, Head, Loading, Scroll, Seg, Segmented, Td, Th } from '../components/ui'

const TABS = ['unmapped', 'verification', 'coverage', 'related'] as const
type Tab = (typeof TABS)[number]

export default function Reports() {
  const { t } = useI18n()
  const [tab, setTab] = useState<Tab>('unmapped')
  const { data: un } = useUnmapped()
  const { data: vr } = useVerification()

  const counts: Record<Tab, number | undefined> = {
    // นับเฉพาะที่ต้องลงมือ ไม่ใช่จำนวนครั้งที่เจอทั้งหมด
    unmapped: un?.by_severity.filter((s) => s.severity !== 'low').reduce((a, s) => a + s.distinct_n, 0),
    verification: vr?.counts.find((c) => c.grade === 'weak')?.n,
    coverage: undefined,
    related: undefined,
  }

  return (
    <div>
      <header>
        <h1 className="text-h1 font-semibold text-ink">{t('nav.reports')}</h1>
        <p className="mt-0.5 max-w-[62ch] text-small text-ink-2">{t('rep.unmapped.note')}</p>
      </header>

      <div className="mt-6 mb-7">
        <Segmented>
          {TABS.map((x) => (
            <Seg key={x} active={tab === x} onClick={() => setTab(x)} count={counts[x]}>
              {t(`rep.${x}`)}
            </Seg>
          ))}
        </Segmented>
      </div>

      {tab === 'unmapped' ? <Unmapped /> : null}
      {tab === 'verification' ? <Verification /> : null}
      {tab === 'coverage' ? <Coverage /> : null}
      {tab === 'related' ? <Related /> : null}
    </div>
  )
}

const SEV_COLOR: Record<Severity, string> = {
  high: 'var(--critical)',
  medium: 'var(--serious)',
  low: 'var(--ink-3)',
}

/**
 * เรียงตาม "ผลกระทบ" ไม่ใช่ "จำนวนครั้งที่เจอ"
 *
 * เดิมหน้านี้เรียงตาม n ซึ่งตอบไม่ได้ว่าควรแก้อะไรก่อน — รหัสที่เจอ 84 ครั้ง
 * แต่มีคนถือ 2 คน ไม่ได้สำคัญกว่ารหัสที่เจอ 3 ครั้งแต่มีคนถือ 200 คน
 */
function Unmapped() {
  const { t, isTh } = useI18n()
  const [bucket, setBucket] = useState<string>()
  const [sev, setSev] = useState<Severity>()
  const { data, isLoading } = useUnmapped(bucket, sev)
  if (isLoading) return <Loading rows={8} />
  if (!data?.items.length && !bucket && !sev)
    return <Empty>{isTh ? 'ไม่มีของที่แปลงไม่ได้' : 'Nothing unmapped'}</Empty>

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start gap-x-10 gap-y-4 border-y border-rule py-3">
        {(data?.by_severity ?? []).map((s) => (
          <button
            key={s.severity}
            type="button"
            onClick={() => setSev(sev === s.severity ? undefined : s.severity)}
            className={`tap text-left ${sev === s.severity ? '' : 'opacity-70 hover:opacity-100'}`}
          >
            <span className="tnum block text-h1 font-semibold" style={{ color: SEV_COLOR[s.severity] }}>
              {num(s.distinct_n)}
            </span>
            <span className="block text-small text-ink">{t(`sev.${s.severity}`)}</span>
            <span className="block text-micro text-ink-3">
              {s.value_mb > 0 ? `${num(s.value_mb, 1)} ${isTh ? 'ลบ. ที่กระทบ' : 'M affected'}` : `${num(s.total)} ${isTh ? 'ครั้ง' : 'hits'}`}
              {s.new_n ? ` · ${num(s.new_n)} ${t('rep.new')}` : ''}
            </span>
          </button>
        ))}
      </div>

      <div className="grid gap-x-12 gap-y-8 lg:grid-cols-[220px_1fr]">
        <section>
          <Head>{isTh ? 'แยกตามชนิด' : 'By bucket'}</Head>
          <div className="border-t border-rule">
            <HBars
              items={(data?.by_bucket ?? []).map((b) => ({
                key: b.bucket,
                label: b.bucket,
                value: b.total,
                note: `${b.distinct_n} distinct`,
              }))}
              activeKey={bucket}
              onPick={(k) => setBucket(bucket === k ? undefined : k)}
              color="var(--s2)"
            />
          </div>
        </section>

        <section className="min-w-0">
          <Head note={t('rep.impact.note')}>{isTh ? 'เรียงตามผลกระทบ' : 'Ranked by impact'}</Head>
          <Scroll>
            <table className="w-full min-w-[680px] border-collapse">
              <thead>
                <tr>
                  <Th>{isTh ? 'รหัสดิบ' : 'Raw code'}</Th>
                  <Th>{isTh ? 'กระทบอะไร' : 'What it costs'}</Th>
                  <Th right>{t('k.customers')}</Th>
                  <Th right>AUM</Th>
                  <Th right>{isTh ? 'พบ' : 'Seen'}</Th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((r) => (
                  <tr key={r.id} className="hover:bg-wash">
                    <Td>
                      <span className="tnum font-medium">{r.raw}</span>
                      {r.is_new ? (
                        <span className="ml-1.5 text-micro" style={{ color: 'var(--warning)' }}>
                          {t('rep.new')}
                        </span>
                      ) : null}
                      <div className="tnum text-micro text-ink-3">
                        {r.bucket} · {r.rule}
                      </div>
                    </Td>
                    <Td>
                      <span className="text-small" style={{ color: SEV_COLOR[r.severity] }}>
                        {isTh ? r.impact_th : r.impact_en}
                      </span>
                      <div className="text-micro text-ink-3">{r.reason}</div>
                    </Td>
                    <Td right className="text-ink-2">
                      {r.customers || (r.txn_rows ? `${num(r.txn_rows)} ${isTh ? 'แถว' : 'rows'}` : '—')}
                    </Td>
                    <Td right className="text-ink-2">
                      {r.value_mb ? num(r.value_mb, 2) : '—'}
                    </Td>
                    <Td right className="text-ink-3">
                      {r.n}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        </section>
      </div>
    </div>
  )
}

function Verification() {
  const { t, isTh } = useI18n()
  const [grade, setGrade] = useState<string>()
  const [open, setOpen] = useState<string>()
  const { data, isLoading } = useVerification(grade)
  if (isLoading) return <Loading rows={10} />
  if (!data) return <Empty />

  return (
    <section>
      <Head>{t('rep.verification')}</Head>

      <div className="mb-4 flex flex-wrap items-center gap-x-8 gap-y-3 border-y border-rule py-3">
        {data.counts.map((c) => (
          <button
            key={c.grade}
            type="button"
            onClick={() => setGrade(grade === c.grade ? undefined : c.grade)}
            className={`tap text-left ${grade === c.grade ? '' : 'opacity-70 hover:opacity-100'}`}
          >
            <span className="tnum block text-h1 font-semibold text-ink">{num(c.n)}</span>
            <span className="block">
              <Grade grade={c.grade} />
            </span>
            <span className="block text-micro text-ink-3">
              {num(c.matches)} {t('k.matches')}
            </span>
          </button>
        ))}
      </div>

      <ul className="border-t border-rule">
        {data.items.map((r) => {
          const checks = jparse<GradeCheck[]>(r.auto_checks, [])
          const failed = checks.filter((c) => !c.ok)
          const isOpen = open === r.article_id
          return (
            <li key={r.article_id} className="border-b border-rule py-3">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <Link
                  to={`/news/${encodeURIComponent(r.article_id)}`}
                  className="min-w-0 flex-1 text-body font-medium text-ink hover:underline"
                >
                  {r.title}
                </Link>
                <Grade grade={r.auto_grade ?? 'unknown'} />
                <span className="tnum w-14 text-right text-body font-semibold text-ink">
                  {num(r.n_matches)}
                </span>
              </div>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-micro text-ink-3">
                <span>{r.subcategory_name || r.subcategory}</span>
                <span>
                  {t('k.source')} {r.entity_source}
                </span>
                {jparse<string[]>(r.entity, [])
                  .slice(0, 5)
                  .map((e) => (
                    <Code key={e}>{e}</Code>
                  ))}
              </p>
              <p className="mt-1 text-small text-ink-2">{isTh ? r.auto_reason_th : r.auto_reason_en}</p>
              {checks.length ? (
                <button
                  type="button"
                  onClick={() => setOpen(isOpen ? undefined : r.article_id)}
                  className="tap mt-1 text-micro text-ink-3 hover:text-ink"
                >
                  {t('g.checks')} {checks.length}
                  {failed.length ? ` · ${failed.length} ✕` : ''} {isOpen ? '−' : '+'}
                </button>
              ) : null}
              {isOpen ? (
                <ul className="mp-in mt-1.5 space-y-1">
                  {checks.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 text-small">
                      <span
                        className="mt-0.5 w-3 shrink-0 text-center text-micro"
                        style={{ color: c.ok ? 'var(--pos)' : 'var(--serious)' }}
                      >
                        {c.ok ? '✓' : '×'}
                      </span>
                      <span className="text-ink-2">{isTh ? c.th : c.en}</span>
                      {c.rule ? <span className="tnum text-micro text-ink-3">{c.rule}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          )
        })}
      </ul>
    </section>
  )
}


function Coverage() {
  const { t, isTh } = useI18n()
  const { data, isLoading } = useCoverage()
  if (isLoading) return <Loading rows={8} />
  if (!data) return <Empty />

  return (
    <div className="space-y-12">
      <section>
        <Head note={t('rep.coverage.note')}>{isTh ? 'ต่อกลุ่มลูกค้า' : 'By persona'}</Head>
        <Scroll>
          <table className="w-full min-w-[560px] border-collapse">
            <thead>
              <tr>
                <Th>{t('k.persona')}</Th>
                <Th right>{t('k.customers')}</Th>
                <Th right>{t('rep.neverMatched')}</Th>
                <Th>{t('rep.covered')}</Th>
                <Th right>AUM</Th>
              </tr>
            </thead>
            <tbody>
              {data.by_persona.map((p) => (
                <tr key={p.persona} className="hover:bg-wash">
                  <Td>{t(`persona.${p.persona}`, p.persona)}</Td>
                  <Td right className="text-ink-2">
                    {num(p.customers)}
                  </Td>
                  <Td right style={{ color: p.never_matched ? 'var(--serious)' : undefined }}>
                    {num(p.never_matched)}
                  </Td>
                  <Td>
                    <Meter value={1 - p.never_matched / Math.max(1, p.customers)} />
                  </Td>
                  <Td right className="text-ink-2">
                    {num(p.aum_mb, 1)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </Scroll>
      </section>

      <div className="grid gap-x-12 gap-y-12 lg:grid-cols-2">
        <section className="min-w-0">
          <Head
            note={isTh ? 'สินทรัพย์ที่มีข่าวถึงจริง เทียบกับที่ลูกค้าถือ' : 'Instruments with real news vs instruments held'}
          >
            {isTh ? 'ต่อประเภทสินทรัพย์' : 'By asset class'}
          </Head>
          <Scroll>
            <table className="w-full min-w-[480px] border-collapse">
              <thead>
                <tr>
                  <Th>{isTh ? 'ประเภท' : 'Class'}</Th>
                  <Th right>{t('rep.instruments')}</Th>
                  <Th>{t('rep.covered')}</Th>
                  <Th right>AUM</Th>
                </tr>
              </thead>
              <tbody>
                {data.by_asset_class.map((a) => (
                  <tr key={a.asset_class} className="hover:bg-wash">
                    <Td>{t(`ac.${a.asset_class}`, a.asset_class)}</Td>
                    <Td right className="text-ink-2">
                      {num(a.instruments)}
                    </Td>
                    <Td>
                      <Meter value={a.covered / Math.max(1, a.instruments)} label={`${a.covered}/${a.instruments}`} />
                    </Td>
                    <Td right className="text-ink-2">
                      {num(a.value_mb, 1)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        </section>

        <section className="min-w-0">
          <Head note={isTh ? 'เรียงตามมูลค่า — ช่องว่างด้านเนื้อหา' : 'By value — this is a content gap'}>
            {isTh ? 'ถือมากแต่ไม่มีข่าวถึง' : 'Held but never in the news'}
          </Head>
          <Scroll className="max-h-[420px] overflow-y-auto">
            <table className="w-full min-w-[420px] border-collapse">
              <thead>
                <tr>
                  <Th>{t('k.entity')}</Th>
                  <Th right>{t('k.customers')}</Th>
                  <Th right>AUM</Th>
                </tr>
              </thead>
              <tbody>
                {data.top_uncovered.map((x) => (
                  <tr key={x.entity} className="hover:bg-wash">
                    <Td>
                      <span className="tnum font-medium">{x.entity}</span>
                      <div className="text-micro text-ink-3">{t(`ac.${x.asset_class}`, x.asset_class)}</div>
                    </Td>
                    <Td right className="text-ink-2">
                      {num(x.customers)}
                    </Td>
                    <Td right>{num(x.value_mb, 2)}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        </section>
      </div>
    </div>
  )
}

function Related() {
  const { isTh } = useI18n()
  const { data, isLoading } = useRelated()
  if (isLoading) return <Loading rows={8} />
  if (!data) return <Empty />

  return (
    <div className="grid gap-x-12 gap-y-10 lg:grid-cols-2">
      <section>
        <Head note={isTh ? 'seed จาก STEP4 C2' : 'seeded from STEP4 C2'}>
          {isTh ? 'กลุ่มที่พิสูจน์แล้วจาก 400 บทความ' : 'Groups proven on 400 articles'}
        </Head>
        <ul className="border-t border-rule">
          {data.seed_groups.map((g) => (
            <li key={g.group} className="border-b border-rule py-2.5">
              <div className="text-small font-medium text-ink">{g.group}</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {g.members.map((m) => (
                  <Code key={m}>{m}</Code>
                ))}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="min-w-0">
        <Head
          note={isTh ? 'ใช้จับคู่ L4 เมื่อพบร่วมกัน 3 ครั้งขึ้นไป (R3.31)' : 'Used for L4 once seen together 3+ times (R3.31)'}
        >
          {isTh ? 'ที่ระบบเรียนเองจากข่าวที่ ingest มา' : 'Learned from ingested articles'}
        </Head>
        <Scroll className="max-h-[460px] overflow-y-auto">
          <table className="w-full min-w-[340px] border-collapse">
            <thead>
              <tr>
                <Th>A</Th>
                <Th>B</Th>
                <Th right>{isTh ? 'พบร่วมกัน' : 'Co-mentions'}</Th>
              </tr>
            </thead>
            <tbody>
              {data.learned.map((r) => (
                <tr key={`${r.a}|${r.b}`} className="hover:bg-wash">
                  <Td className="tnum font-medium">{r.a}</Td>
                  <Td className="tnum font-medium">{r.b}</Td>
                  <Td right style={{ color: r.n >= 3 ? 'var(--pos)' : undefined }}>
                    {r.n}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </Scroll>
      </section>
    </div>
  )
}
