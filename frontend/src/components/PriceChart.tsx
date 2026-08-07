import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import CandleChart from './CandleChart'
import { useChart } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { num, pct } from '../lib/format'

/**
 * กราฟราคา — แท่งเทียน มาจากสองแหล่งตามชนิดของสินทรัพย์ (ดู backend/app/symbols.py)
 *
 *   หุ้นต่างประเทศ + คริปโต  widget ของ TradingView ใช้ข้อมูลของ TradingView เอง
 *   หุ้นไทย                 ข้อมูล Yahoo ผ่านเซิร์ฟเวอร์ของเรา แล้ววาดเองด้วย lightweight-charts
 *
 * ที่ต้องแยกเพราะ embed ฟรีของ TradingView ไม่ให้ข้อมูลตลาด SET
 * ทางฝั่งที่วาดเองได้เปรียบตรงปักหมุดวันที่มีข่าวและลากเส้นเป้าหมาย INVX ได้
 */

const RANGES = ['1mo', '3mo', '6mo', '1y', '2y'] as const

const RANGE_TH: Record<string, string> = {
  '1mo': '1 เดือน',
  '3mo': '3 เดือน',
  '6mo': '6 เดือน',
  '1y': '1 ปี',
  '2y': '2 ปี',
}

export default function PriceChart({ entity, target }: { entity: string; target?: number | null }) {
  const { isTh, lang } = useI18n()
  const nav = useNavigate()
  const dark = useIsDark()
  const [range, setRange] = useState<(typeof RANGES)[number]>('6mo')
  const { data, isLoading } = useChart(entity, range)

  const openNews = useCallback(
    (id: string) => nav(`/news/${encodeURIComponent(id)}`, { state: { from: `/stock/${encodeURIComponent(entity)}` } }),
    [nav, entity],
  )

  if (isLoading) return <div className="h-[400px] animate-pulse rounded-out bg-wash" />

  if (!data || data.provider === 'none' || (data.provider === 'yahoo' && !data.series)) {
    return (
      <p className="border-y border-rule py-4 text-small text-ink-3">
        {data?.note ?? (isTh ? 'ไม่มีกราฟสำหรับตัวนี้' : 'no chart for this instrument')}
      </p>
    )
  }

  /* ---------------- หุ้นต่างประเทศ + คริปโต — widget ของ TradingView ---------------- */
  if (data.provider === 'tradingview' && data.tradingview) {
    const src = `/tradingview.html?symbol=${encodeURIComponent(data.tradingview)}&theme=${
      dark ? 'dark' : 'light'
    }&locale=${lang === 'th' ? 'th' : 'en'}`
    return (
      <div>
        <iframe
          key={src}
          title={`TradingView ${data.tradingview}`}
          src={src}
          className="h-[440px] w-full rounded-out border border-rule"
        />
        <p className="mt-2 text-micro text-ink-3">
          {isTh
            ? `แท่งเทียนรายวันจาก TradingView (${data.tradingview}) — เป็นข้อมูลของ TradingView ไม่ใช่ของระบบนี้ เลื่อนช่วงเวลาได้ที่แถบเครื่องมือในกราฟ`
            : `Daily candles from TradingView (${data.tradingview}) — TradingView’s own data; change the range in the chart toolbar`}
        </p>
      </div>
    )
  }

  /* ---------------- หุ้นไทย — ข้อมูล Yahoo วาดเอง ---------------- */
  const s = data.series!
  const up = (s.change_pct ?? 0) >= 0

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="tnum text-h1 font-semibold text-ink">{num(s.last, 2)}</span>
          <span className="text-micro text-ink-3">{s.currency}</span>
          <span
            className="tnum text-body font-semibold"
            style={{ color: up ? 'var(--pos)' : 'var(--critical)' }}
          >
            {up ? '+' : ''}
            {pct(s.change_pct ?? 0, 1)}
            <span className="ml-1 text-micro font-normal text-ink-3">
              {isTh ? `ใน ${RANGE_TH[range]}` : range}
            </span>
          </span>
          {s.w52_low && s.w52_high ? (
            <span className="tnum text-micro text-ink-3">
              52wk {num(s.w52_low, 2)}–{num(s.w52_high, 2)}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRange(r)}
              className={`tap rounded-in px-2 py-0.5 text-micro ${
                range === r ? 'bg-ink text-paper' : 'text-ink-3 hover:text-ink'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3">
        <CandleChart data={data} target={target} dark={dark} onPickNews={openNews} />
      </div>

      <p className="mt-2 text-micro leading-relaxed text-ink-3">
        {isTh ? (
          <>
            จุดเหนือแท่ง = วันที่มีข่าวถึงตัวนี้ ({num(data.news_marks?.length ?? 0)} วัน) สีบอกทิศทางที่ระบบอ่านได้
            {data.news_marks?.length ? ' · คลิกที่แท่งเพื่อเปิดข่าววันนั้น' : ''}
            {target ? ' · เส้นประ = ราคาเป้าหมาย INVX Research' : ''}
            <br />
            ราคาปิดรายวันจาก Yahoo Finance ผ่านเซิร์ฟเวอร์ของระบบ ({data.symbol}) ·{' '}
            {data.cached ? 'จากข้อมูลที่เก็บไว้' : 'ดึงใหม่'}{' '}
            {data.fetched_at?.replace('T', ' ').slice(0, 16) ?? ''} · ไม่ใช่ราคาเรียลไทม์
            {data.note ? ` · ${data.note}` : ''}
          </>
        ) : (
          <>
            Dots mark days with news ({num(data.news_marks?.length ?? 0)}), coloured by direction · daily
            closes from Yahoo Finance via our server ({data.symbol})
            {data.note ? ` · ${data.note}` : ''}
          </>
        )}
      </p>
    </div>
  )
}

/** ทั้ง widget และกราฟที่วาดเองใช้สีตามธีม ต้องรู้ว่าตอนนี้ธีมไหนและสร้างใหม่เมื่อสลับ */
function useIsDark() {
  const read = () => {
    const set = document.documentElement.getAttribute('data-theme')
    if (set) return set === 'dark'
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
  }
  const [dark, setDark] = useState(read)
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(read()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [])
  return dark
}
