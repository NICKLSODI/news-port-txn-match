import { useState } from 'react'
import { useArticles, useDates, useReference } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { num } from '../lib/format'
import ArticleCard from '../components/ArticleCard'
import { Button, Empty, Loading, Seg, Segmented } from '../components/ui'

const PAGE = 40

export default function News() {
  const { t, isTh } = useI18n()
  const [q, setQ] = useState('')
  const [mode, setMode] = useState<string>()
  const [subcategory, setSub] = useState<string>()
  const [recordType, setRecordType] = useState<string>()
  const [sort, setSort] = useState<'recent' | 'matches' | 'importance'>('recent')
  const [limit, setLimit] = useState(PAGE)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  const { data, isLoading } = useArticles({
    q: q.length >= 2 ? q : undefined,
    mode,
    subcategory,
    record_type: recordType,
    date_from: from || undefined,
    date_to: to || undefined,
    sort,
    limit,
  })
  const { data: ref } = useReference()
  const { data: days } = useDates()

  const subs = (ref?.content_inventory ?? [])
    .filter((c) => c.decision === 'ทำ' && c.role === 'content')
    .sort((a, b) => (b.per_week ?? 0) - (a.per_week ?? 0))
    .slice(0, 12)

  const dirty = q || mode || subcategory || recordType || from || to || sort !== 'recent'

  /** ตั้งช่วงวันที่แบบกดปุ่มเดียว — คนส่วนใหญ่อยากได้ "วันนี้" หรือ "อาทิตย์นี้" ไม่ได้อยากพิมพ์วันที่
   *  อิงวันล่าสุดที่มีข่าวจริง ไม่ใช่วันนี้ตามนาฬิกา — เสาร์อาทิตย์กดแล้วต้องไม่ได้หน้าว่าง */
  const latest = days?.[0]?.d
  const shift = (n: number) => {
    if (!latest) return
    const d = new Date(`${latest}T00:00:00`)
    d.setDate(d.getDate() - n)
    setFrom(d.toISOString().slice(0, 10))
    setTo(latest)
    setLimit(PAGE)
  }
  const rangeIs = (n: number) => {
    if (!latest || to !== latest) return false
    const d = new Date(`${latest}T00:00:00`)
    d.setDate(d.getDate() - n)
    return from === d.toISOString().slice(0, 10)
  }

  return (
    <div>
      <header className="flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <h1 className="text-h1 font-semibold text-ink">{t('nav.news')}</h1>
          <p className="mt-0.5 max-w-[62ch] text-small text-ink-2">
            {isTh
              ? 'เปิดข่าวหนึ่งชิ้นเพื่อดูรายชื่อลูกค้าที่ควรติดต่อ พร้อมเหตุผลรายคน'
              : 'Open an article to see the ranked customer list and the reason for each name'}
          </p>
        </div>
        <p className="tnum text-h1 font-semibold text-ink">{num(data?.total)}</p>
      </header>

      <div className="mt-7 space-y-3 border-y border-rule py-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setLimit(PAGE)
            }}
            placeholder={`${t('a.search')} — ${isTh ? 'ชื่อบทความ หรือ ticker' : 'title or ticker'}`}
            className="min-w-[220px] flex-1 rounded-out border border-rule bg-surface px-3 py-1.5 text-small text-ink outline-none placeholder:text-ink-3 focus:border-rule-strong"
          />
          <Segmented>
            {(['recent', 'matches', 'importance'] as const).map((s) => (
              <Seg key={s} active={sort === s} onClick={() => setSort(s)}>
                {s === 'recent' ? (isTh ? 'ล่าสุด' : 'Newest') : s === 'matches' ? t('k.matches') : t('k.importance')}
              </Seg>
            ))}
          </Segmented>
          <Segmented>
            <Seg active={!mode} onClick={() => setMode(undefined)}>
              {t('a.all')}
            </Seg>
            <Seg active={mode === 'realtime'} onClick={() => setMode('realtime')}>
              {t('mode.realtime')}
            </Seg>
            <Seg active={mode === 'digest'} onClick={() => setMode('digest')}>
              {t('mode.digest')}
            </Seg>
          </Segmented>
          <Segmented>
            <Seg active={recordType === 'segment'} onClick={() => setRecordType(recordType ? undefined : 'segment')}>
              {t('k.segments')}
            </Seg>
          </Segmented>
          {dirty ? (
            <button
              type="button"
              onClick={() => {
                setQ('')
                setMode(undefined)
                setSub(undefined)
                setRecordType(undefined)
                setFrom('')
                setTo('')
                setSort('recent')
                setLimit(PAGE)
              }}
              className="tap text-small text-ink-3 underline hover:text-ink"
            >
              {t('a.clear')}
            </button>
          ) : null}
        </div>

        {/* ---------------- ช่วงวันที่ ---------------- */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="text-small text-ink-3">{isTh ? 'ช่วงวันที่' : 'Date range'}</span>
          <Segmented>
            <Seg active={!from && !to} onClick={() => { setFrom(''); setTo(''); setLimit(PAGE) }}>
              {t('a.all')}
            </Seg>
            <Seg active={rangeIs(0)} onClick={() => shift(0)}>
              {isTh ? 'วันล่าสุด' : 'Latest day'}
            </Seg>
            <Seg active={rangeIs(6)} onClick={() => shift(6)}>
              {isTh ? '7 วัน' : '7 days'}
            </Seg>
            <Seg active={rangeIs(29)} onClick={() => shift(29)}>
              {isTh ? '30 วัน' : '30 days'}
            </Seg>
          </Segmented>
          <div className="flex flex-wrap items-center gap-1.5">
            <input
              type="date"
              value={from}
              max={to || undefined}
              onChange={(e) => { setFrom(e.target.value); setLimit(PAGE) }}
              className="tnum rounded-out border border-rule bg-surface px-2.5 py-1.5 text-small text-ink outline-none focus:border-rule-strong"
            />
            <span className="text-small text-ink-3">–</span>
            <input
              type="date"
              value={to}
              min={from || undefined}
              onChange={(e) => { setTo(e.target.value); setLimit(PAGE) }}
              className="tnum rounded-out border border-rule bg-surface px-2.5 py-1.5 text-small text-ink outline-none focus:border-rule-strong"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {subs.map((s) => (
            <button
              key={s.subcategory}
              type="button"
              onClick={() => setSub(subcategory === s.subcategory ? undefined : s.subcategory)}
              className={`tap text-small ${
                subcategory === s.subcategory ? 'font-semibold text-ink underline' : 'text-ink-3 hover:text-ink'
              }`}
            >
              {s.name || s.subcategory}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="mt-5">
          <Loading rows={8} />
        </div>
      ) : !data?.items.length ? (
        <Empty />
      ) : (
        <>
          <div className="mt-1 grid gap-x-10 xl:grid-cols-2">
            {data.items.map((a) => (
              <ArticleCard key={a.article_id} a={a} />
            ))}
          </div>
          {data.total > data.items.length ? (
            <p className="mt-7 text-center">
              <Button onClick={() => setLimit(limit + PAGE)}>
                {t('a.showMore')} · {num(data.total - data.items.length)}
              </Button>
            </p>
          ) : null}
        </>
      )}
    </div>
  )
}
