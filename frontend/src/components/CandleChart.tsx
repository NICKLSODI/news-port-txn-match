import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'
import type { ChartData } from '../lib/api'

/**
 * แท่งเทียนจากข้อมูล Yahoo — ใช้กับหุ้นไทย
 *
 * วาดด้วย lightweight-charts (ไลบรารีโอเพนซอร์สของ TradingView สัญญาอนุญาต Apache-2.0)
 * ต่างจาก widget สำเร็จรูปคือป้อนข้อมูลของเราเข้าไปได้ จึงปักหมุดวันที่มีข่าว
 * และลากเส้นราคาเป้าหมายของ INVX Research ทับบนกราฟเดียวกันได้
 */

/** สีหมุด = ทิศทางที่ระบบอ่านได้จากข่าวของวันนั้น (คืนชื่อตัวแปร CSS) */
const markVar = (dirs: Record<string, number>) => {
  const up = dirs.up || 0
  const down = dirs.down || 0
  if (up && !down) return '--pos'
  if (down && !up) return '--critical'
  if (up || down) return '--warning'
  return '--ink-3'
}

/** ไลบรารีรับเฉพาะสีจริง ตัวแปร CSS ส่งเข้าไปตรง ๆ ไม่ได้ */
const cssVar = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888'

export default function CandleChart({
  data,
  target,
  dark,
  onPickNews,
}: {
  data: ChartData
  target?: number | null
  dark: boolean
  onPickNews?: (articleId: string) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const bars = data.series?.bars
  const marks = data.news_marks

  useEffect(() => {
    if (!box.current || !bars?.length) return

    const ink = cssVar('--ink')
    const rule = cssVar('--rule')
    const pos = cssVar('--pos')
    const neg = cssVar('--critical')

    const chart: IChartApi = createChart(box.current, {
      autoSize: true,
      layout: {
        background: { color: 'transparent' },
        textColor: cssVar('--ink-3'),
        fontFamily: getComputedStyle(document.body).fontFamily,
        attributionLogo: false,
      },
      grid: { vertLines: { color: rule }, horzLines: { color: rule } },
      rightPriceScale: { borderColor: rule, scaleMargins: { top: 0.08, bottom: 0.26 } },
      timeScale: { borderColor: rule, rightOffset: 3 },
      crosshair: { vertLine: { color: ink, labelBackgroundColor: ink }, horzLine: { color: ink, labelBackgroundColor: ink } },
      localization: { locale: 'th-TH' },
    })

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: pos,
      downColor: neg,
      wickUpColor: pos,
      wickDownColor: neg,
      borderVisible: false,
      // ราคาเป้าหมายมักอยู่เหนือช่วงราคาจริง ต้องขยายแกนให้ครอบไปถึง
      // ไม่งั้นเส้นเป้าหมายจะหลุดออกนอกกรอบทั้งที่คำอธิบายใต้กราฟบอกว่ามี
      autoscaleInfoProvider: (orig: () => { priceRange: { minValue: number; maxValue: number } | null } | null) => {
        const res = orig()
        if (!res?.priceRange || !target || target <= 0) return res
        return {
          ...res,
          priceRange: {
            minValue: Math.min(res.priceRange.minValue, target),
            maxValue: Math.max(res.priceRange.maxValue, target),
          },
        }
      },
    })
    candles.setData(bars.map((b) => ({ time: b.d as Time, open: b.o, high: b.h, low: b.l, close: b.c })))

    // ปริมาณซื้อขายอยู่แถบล่างของกรอบเดียวกัน — บอกว่าวันที่ราคาขยับมีคนเทรดจริงไหม
    const vol = chart.addSeries(HistogramSeries, {
      priceScaleId: 'vol',
      priceFormat: { type: 'volume' },
      priceLineVisible: false,
      lastValueVisible: false,
    })
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
    vol.setData(
      bars.map((b) => ({
        time: b.d as Time,
        value: b.v,
        color: b.c >= b.o ? `${pos}44` : `${neg}44`,
      })),
    )

    if (target && target > 0) {
      candles.createPriceLine({
        price: target,
        color: cssVar('--s2'),
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'เป้าหมาย INVX',
      })
    }

    if (marks?.length) {
      const byDay = new Set(bars.map((b) => b.d))
      const items: SeriesMarker<Time>[] = marks
        .filter((m) => byDay.has(m.d))
        .map((m) => ({
          time: m.d as Time,
          position: 'aboveBar' as const,
          shape: 'circle' as const,
          color: cssVar(markVar(m.dirs)),
          text: m.n > 1 ? `${m.n}` : '',
        }))
      if (items.length) createSeriesMarkers(candles, items)
    }

    // คลิกที่แท่งซึ่งมีข่าว = เปิดข่าวชิ้นนั้น
    const onClick = (p: MouseEventParams) => {
      if (!p.time || !onPickNews) return
      const hit = marks?.find((m) => m.d === String(p.time))
      if (hit) onPickNews(hit.article_id)
    }
    chart.subscribeClick(onClick)
    chart.timeScale().fitContent()

    return () => {
      chart.unsubscribeClick(onClick)
      chart.remove()
    }
    // dark อยู่ใน deps เพราะสีทั้งชุดอ่านจากตัวแปร CSS ตอนสร้าง ต้องสร้างใหม่เมื่อสลับธีม
  }, [bars, marks, target, dark, onPickNews])

  return <div ref={box} className="h-[400px] w-full" />
}
