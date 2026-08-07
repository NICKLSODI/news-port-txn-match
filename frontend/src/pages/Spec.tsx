import { useReference, useSpecGaps } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { num, LEVEL_COLOR, LEVEL_ORDER } from '../lib/format'
import { Code, Empty, Head, Loading, Scroll, Stat, Td, Th } from '../components/ui'

export default function Spec() {
  const { t, isTh } = useI18n()
  const { data: gaps } = useSpecGaps()
  const { data: ref } = useReference()

  if (!gaps || !ref) return <Loading rows={10} />
  const inv = ref.content_inventory.filter((c) => c.decision === 'ทำ')

  return (
    <div>
      <header>
        <h1 className="text-h1 font-semibold text-ink">{t('nav.spec')}</h1>
        <p className="mt-0.5 max-w-[68ch] text-small text-ink-2">
          {isTh
            ? 'ระบบสร้างตามเอกสาร STEP1–STEP8 รวม 136 กฎ หน้านี้แสดงกฎที่ใช้จริง และจุดที่เอกสารไม่ครบหรือไม่ตรงกับข้อมูลจริง'
            : 'Built from STEP1–STEP8 (136 rules). This page shows the rules in force and where the docs fall short of the real data.'}
        </p>
      </header>

      <div className="mt-8 flex flex-wrap gap-x-12 gap-y-5 border-b border-rule pb-6">
        <Stat label={isTh ? 'ช่องว่างที่พบ' : 'Gaps found'} value={gaps.n} />
        <Stat label={isTh ? 'หมวดข่าวในขอบเขต' : 'Subcategories in scope'} value={inv.length} />
        <Stat label="Coverage List" value={ref.coverage_list_size} sub={`${ref.sectors.length} sectors`} />
        <Stat
          label={isTh ? 'DR แปลงเป็นหุ้นแม่' : 'DR resolved'}
          value={ref.dr_resolved}
          sub={`${ref.dr_pending} ${isTh ? 'ยังแปลงไม่ได้' : 'unresolved'}`}
        />
      </div>

      <div className="mt-9 grid gap-x-12 gap-y-9 lg:grid-cols-2">
        <section>
          <Head
            note={
              isTh
                ? 'ลูกค้าเข้าหลายระดับ ใช้ระดับสูงสุดเป็นฐาน แล้วบวกโบนัส'
                : 'The highest level becomes the base, plus a multi-hit bonus'
            }
          >
            {t('spec.levels')}
          </Head>
          <ul className="border-t border-rule">
            {LEVEL_ORDER.map((l) => (
              <li key={l} className="flex items-center gap-3 border-b border-rule py-2">
                {/* deslop-ignore-next-line 19 */}
                <span className="size-2 rounded-full" style={{ background: LEVEL_COLOR[l] }} />
                <span className="flex-1 text-small text-ink-2">{t(`lvl.${l}`)}</span>
                <span className="tnum text-body font-semibold text-ink">{ref.levels[l]}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="min-w-0">
          <Head
            note={
              isTh
                ? 'ทุกตัวเป็นข้อเท็จจริงที่ตรวจสอบได้ — ไม่มี sentiment'
                : 'Every factor is a verifiable fact — no sentiment anywhere'
            }
          >
            {t('spec.formula')}
          </Head>
          <pre className="overflow-x-auto border-t border-rule pt-3 text-micro leading-relaxed text-ink-2">
{`score = base_weight(L1..L6)
      × (1 + log_scale(holding_value))   R6.8
      × importance / 3                   R6.9
      × urgency_factor                   R6.10
      × recency_factor                   R6.11
      × (1 + 0.1 × (n_hits - 1))`}
          </pre>
          <p className="mt-2 text-small text-ink-2">
            {isTh
              ? 'คะแนนต่ำกว่าเกณฑ์ไม่แสดง (R6.14) · ไม่จำกัดจำนวน แต่เรียงลำดับ (R6.15)'
              : 'Below the threshold means hidden (R6.14) · no cap, only ranking (R6.15)'}
          </p>
        </section>
      </div>

      {/* ---------------- ช่องว่าง ---------------- */}
      <section className="mt-12">
        <Head note={t('spec.gaps.note')}>{t('spec.gaps')}</Head>
        <ul className="border-t border-rule">
          {gaps.gaps.map((g) => (
            <li key={g.id} className="grid gap-x-6 gap-y-1 border-b border-rule py-4 sm:grid-cols-[130px_1fr]">
              <div>
                <div className="tnum text-small font-semibold" style={{ color: 'var(--serious)' }}>
                  {g.id}
                </div>
                <div className="text-micro text-ink-3">{g.ref}</div>
              </div>
              <div className="min-w-0">
                <p className="max-w-[80ch] text-body leading-relaxed text-ink">{isTh ? g.th : g.en}</p>
                <p className="mt-1.5 max-w-[80ch] text-small leading-relaxed text-ink-2">
                  <span className="text-ink-3">{t('spec.assumed')}: </span>
                  {g.assumed}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <div className="mt-12 grid gap-x-12 gap-y-9 lg:grid-cols-2">
        <section>
          <Head
            note={
              isTh
                ? 'R3.37 — ภาษาไทยไม่เว้นวรรค ห้ามใช้คำสั้น'
                : 'R3.37 — Thai has no word spacing, so short keywords are banned'
            }
          >
            {isTh ? 'คำค้น macro ที่ทดสอบผ่านแล้ว' : 'Macro keywords that passed testing'}
          </Head>
          <ul className="border-t border-rule">
            {Object.entries(ref.macro_topics).map(([topic, words]) => (
              <li key={topic} className="border-b border-rule py-2">
                <div className="text-small font-medium text-ink">{topic}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {words.map((w) => (
                    <Code key={w}>{w}</Code>
                  ))}
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-small text-ink-2">
            <span className="text-ink-3">{isTh ? 'ห้ามใช้เด็ดขาด: ' : 'Banned: '}</span>
            <span style={{ color: 'var(--critical)' }}>{ref.macro_banned.join(' · ')}</span>
          </p>
        </section>

        <section className="min-w-0">
          <Head note={isTh ? 'ความถี่จาก STEP2 (ชิ้นต่อสัปดาห์)' : 'Cadence from STEP2 (items per week)'}>
            {isTh ? 'บัญชีเนื้อหาที่อยู่ในขอบเขต' : 'Content inventory in scope'}
          </Head>
          {inv.length === 0 ? (
            <Empty />
          ) : (
            <Scroll className="max-h-[440px] overflow-y-auto">
              <table className="w-full min-w-[380px] border-collapse">
                <thead>
                  <tr>
                    <Th>{isTh ? 'หมวด' : 'Subcategory'}</Th>
                    <Th right>/wk</Th>
                    <Th right>ticker</Th>
                  </tr>
                </thead>
                <tbody>
                  {inv
                    .sort((a, b) => (b.per_week ?? 0) - (a.per_week ?? 0))
                    .map((c) => (
                      <tr key={`${c.category}-${c.subcategory}`} className="hover:bg-wash">
                        <Td>
                          <span className="font-medium text-ink">{c.name || c.subcategory}</span>
                          <div className="tnum text-micro text-ink-3">{c.subcategory}</div>
                        </Td>
                        <Td right className="text-ink-2">
                          {c.per_week !== null ? num(c.per_week, 2) : '—'}
                        </Td>
                        <Td right className="text-ink-3">
                          {c.has_ticker_pct || '—'}
                        </Td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </Scroll>
          )}
        </section>
      </div>
    </div>
  )
}
