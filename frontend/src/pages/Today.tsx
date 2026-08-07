import { useState } from 'react'
import { useActions, useDates, useHealth, useRms, useToday } from '../lib/api'
import type { Article } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { fullDate, num } from '../lib/format'
import ArticleCard from '../components/ArticleCard'
import BriefGroup from '../components/BriefGroup'
import { DayColumns } from '../components/charts'
import { Button, Empty, Figure, Loading, Seg, Segmented, Stat } from '../components/ui'

const SLOTS = ['morning', 'intraday', 'evening'] as const

/**
 * ยุบข้อย่อยของสรุปเช้า/เย็นที่มาจากฉบับเดียวกันให้เป็นก้อนเดียว
 * ข่าวรายตัวไม่ถูกแตะ — คืนลำดับเดิมโดยแทนที่ตำแหน่งของข้อแรกในกลุ่ม
 */
type Block = { kind: 'one'; item: Article } | { kind: 'brief'; items: Article[] }

function groupBrief(items: Article[]): Block[] {
  const out: Block[] = []
  const at = new Map<string, number>()
  for (const a of items) {
    const parent = a.record_type === 'segment' ? a.parent_article_id : null
    if (!parent) {
      out.push({ kind: 'one', item: a })
      continue
    }
    const i = at.get(parent)
    if (i === undefined) {
      at.set(parent, out.length)
      out.push({ kind: 'brief', items: [a] })
    } else {
      const b = out[i]
      if (b.kind === 'brief') b.items.push(a)
    }
  }
  // กลุ่มที่มีข้อเดียวไม่ต้องยุบ แสดงเป็นการ์ดปกติ
  return out.map((b) => (b.kind === 'brief' && b.items.length === 1
    ? { kind: 'one' as const, item: b.items[0] }
    : b))
}

export default function Today() {
  const { t, lang } = useI18n()
  const [date, setDate] = useState<string | undefined>()
  const [rm, setRm] = useState<string | undefined>()
  const { data: h } = useHealth()
  const { data: dates } = useDates()
  const { data, isLoading } = useToday(date, rm)
  const { data: rms } = useRms()
  const a = useActions()

  // ปุ่มสั่งงาน (ดึงข่าว / ให้ AI อ่าน) ย้ายไปอยู่บนแถบด้านบนแล้ว หน้านี้เหลือแค่ดูของวัน
  // แต่ยังต้องรายงานผลตอนกำลังอ่านอยู่ เพราะคนกดจากแถบบนแล้วมองผลที่หน้านี้
  const reading = a.aiRead.isPending
  const aiDone = a.aiRead.data as import('../lib/api').AiResult | undefined

  const day = data?.date
  const isToday = data?.is_today ?? true
  const items = SLOTS.flatMap((s) => data?.buckets[s] ?? [])
  const nArticles = items.length
  const nSegments = items.filter((a) => a.record_type === 'segment').length

  const shift = (days: number) => {
    if (!day) return
    const d = new Date(`${day}T00:00:00`)
    d.setDate(d.getDate() + days)
    setDate(d.toISOString().slice(0, 10))
  }

  return (
    <div>
      {/* ---------------- หัวเรื่อง ---------------- */}
      <header className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
        <div>
          <h1 className="text-h1 font-semibold text-ink">
            {isToday ? t('nav.today') : t('d.notToday')}
          </h1>
          <p className="mt-0.5 text-body text-ink-2">{day ? fullDate(day, lang) : '—'}</p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {!isToday ? (
            <Button onClick={() => setDate(undefined)}>{t('d.backToToday')}</Button>
          ) : null}
          <Segmented>
            <Seg onClick={() => shift(-1)}>‹</Seg>
            <Seg onClick={() => shift(1)}>›</Seg>
          </Segmented>
          <input
            type="date"
            value={day ?? ''}
            max={data?.today}
            onChange={(e) => setDate(e.target.value || undefined)}
            className="tnum rounded-out border border-rule bg-surface px-2.5 py-1.5 text-small text-ink outline-none focus:border-rule-strong"
          />
        </div>
      </header>

      {reading || aiDone || a.aiRead.error ? (
        <p className="mt-3 text-small text-ink-2">
          {reading ? (
            lang === 'th' ? (
              `Claude Code บนเครื่องกำลังอ่านข่าวทีละชิ้น (ราว 15-25 วินาทีต่อชิ้น)…`
            ) : (
              'Claude Code on this machine is reading article by article…'
            )
          ) : a.aiRead.error ? (
            <span style={{ color: 'var(--critical)' }}>{String(a.aiRead.error)}</span>
          ) : aiDone?.problem ? (
            <span style={{ color: 'var(--critical)' }}>{aiDone.problem}</span>
          ) : (
            <>
              {lang === 'th' ? 'AI อ่านไปแล้ว ' : 'AI read '}
              <b className="tnum">{num(aiDone?.done ?? 0)}</b>
              {lang === 'th' ? ' ชิ้น · เพิ่มหุ้นที่จับคู่ได้ ' : ' · instruments added '}
              <b className="tnum">{num(aiDone?.entities_added ?? 0)}</b>
              {aiDone?.rematch ? (
                <>
                  {lang === 'th' ? ' · จับคู่เพิ่ม ' : ' · new matches '}
                  <b className="tnum">{num(aiDone.rematch.matches)}</b>
                </>
              ) : null}
              {aiDone?.dropped ? (
                <span className="text-ink-3">
                  {lang === 'th'
                    ? ` · ข้อเสนอที่ตรวจไม่ผ่านและถูกทิ้ง ${num(aiDone.dropped)}`
                    : ` · ${num(aiDone.dropped)} unverified suggestions dropped`}
                </span>
              ) : null}
            </>
          )}
        </p>
      ) : null}

      {/* ---------------- ตัวเลขของวัน ---------------- */}
      <div className="mt-8 flex flex-wrap items-end gap-x-12 gap-y-6">
        <Figure
          value={num(data?.total_matches ?? 0)}
          label={lang === 'th' ? 'รายชื่อที่ควรติดต่อวันนี้' : 'names to contact today'}
        />
        <div className="flex flex-wrap gap-x-10 gap-y-4">
          <Stat
            label={t('k.articles')}
            value={num(nArticles)}
            sub={nSegments ? `${num(nSegments)} ${t('k.segments')}` : undefined}
          />
          <Stat label={t('k.customers')} value={num(h?.customers)} />
        </div>
      </div>

      {/* ---------------- แถบปริมาณรายวัน ---------------- */}
      <div className="mt-9 border-t border-rule pt-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-small text-ink-2">
            {lang === 'th' ? 'ย้อนดูวันก่อนหน้า' : 'Look back at earlier days'}
          </p>
          <Segmented>
            <Seg active={!rm} onClick={() => setRm(undefined)}>
              {t('a.all')}
            </Seg>
            {rms?.map((r) => (
              <Seg key={r.rm_id} active={rm === r.rm_id} onClick={() => setRm(r.rm_id)}>
                {r.rm_id}
              </Seg>
            ))}
          </Segmented>
        </div>
        {dates ? <DayColumns data={[...dates].reverse()} active={day} onPick={setDate} /> : null}
      </div>

      {/* ---------------- จังหวะของวัน ---------------- */}
      {isLoading ? (
        <div className="mt-9">
          <Loading rows={6} />
        </div>
      ) : nArticles === 0 ? (
        <div className="mt-4 border-t border-rule">
          <Empty>
            <p>{isToday ? t('msg.empty.today') : t('msg.empty.day')}</p>
            {data?.latest_with_news && data.latest_with_news !== day ? (
              <p className="mt-4">
                <Button onClick={() => setDate(data.latest_with_news!)}>
                  {t('d.goLatest')} · {data.latest_with_news}
                </Button>
              </p>
            ) : null}
          </Empty>
        </div>
      ) : (
        /* สามคอลัมน์คือช่วงเวลาจริงตาม STEP7 ไม่ใช่การ์ดฟีเจอร์ที่สลับกันได้ */
        /* deslop-ignore-next-line 28 */
        <div className="mt-10 grid gap-x-10 gap-y-10 lg:grid-cols-3">
          {SLOTS.map((slot) => {
            const list = data?.buckets[slot] ?? []
            return (
              <section key={slot} className="min-w-0">
                <div className="flex items-baseline justify-between gap-2 border-b-2 border-ink pb-1.5">
                  <h2 className="text-h2 font-semibold text-ink">{t(`slot.${slot}`)}</h2>
                  <span className="tnum text-body font-semibold text-ink">{list.length}</span>
                </div>
                <p className="mt-1.5 text-micro text-ink-3">{t(`slot.${slot}.note`)}</p>
                <div className="mt-2">
                  {list.length === 0 ? (
                    <p className="py-6 text-small text-ink-3">{t('msg.empty')}</p>
                  ) : (
                    groupBrief(list).map((b) =>
                      b.kind === 'one' ? (
                        <ArticleCard key={b.item.article_id} a={b.item} />
                      ) : (
                        <BriefGroup key={b.items[0].parent_article_id} items={b.items} />
                      ),
                    )
                  )}
                </div>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
