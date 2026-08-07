import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useDividendStyles, useDividends, useRms } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { num, pct, thb } from '../lib/format'
import { HBars } from '../components/charts'
import { Empty, Figure, Head, Loading, Scroll, Seg, Segmented, Stat, Td, Th } from '../components/ui'

/**
 * ปันผล — สองมุมในหน้าเดียว
 *
 * ภาพรวมทั้งฐานเป็นค่าเริ่มต้น แล้วค่อยกรองลง RM รายคน (คนนอกทีมดูภาพรวม
 * RM ในทีมกรองเฉพาะของตัวเอง) เรียงทุกตารางด้วย "เงินบาท" ไม่ใช่จำนวนคน
 * — ลูกค้าคนเดียวที่ได้ปันผลล้านนึงสำคัญกว่าสิบคนที่ได้คนละพัน
 */
export default function DividendsPage() {
  const { isTh, lang } = useI18n()
  const [rm, setRm] = useState<string | undefined>()
  const { data: rms } = useRms()
  const { data, isLoading } = useDividends(undefined, rm)
  const { data: st } = useDividendStyles(rm)

  if (isLoading) return <Loading rows={10} />
  if (!data?.month) {
    return (
      <Empty>
        <p>
          {isTh
            ? 'ยังไม่มีตารางปันผล — กดปุ่ม "ดึงตารางปันผลเดือนนี้" บนแถบด้านบน'
            : 'No dividend table yet — use the fetch button in the top bar.'}
        </p>
      </Empty>
    )
  }

  const styleBars = st
    ? (Object.keys(st.labels) as (keyof typeof st.labels)[])
        .filter((k) => st.counts[k])
        .map((k) => ({
          key: k,
          label: isTh ? st.labels[k].th : st.labels[k].en,
          value: st.counts[k] ?? 0,
          note: k === 'unknown' && isTh ? 'ข้อมูลปันผลไม่พอ' : undefined,
        }))
    : []

  return (
    <div>
      <header className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
        <div>
          <h1 className="text-h1 font-semibold text-ink">{isTh ? 'ตามรอยหุ้นปันผล' : 'Dividend tracker'}</h1>
          <p className="mt-0.5 text-body text-ink-2">
            INVX Data Book · {data.month}
            {data.as_of ? <span className="text-ink-3">{isTh ? ` · ข้อมูล ณ ${data.as_of}` : ` · as of ${data.as_of}`}</span> : null}
          </p>
        </div>
        <Segmented>
          <Seg active={!rm} onClick={() => setRm(undefined)}>
            {isTh ? 'ทั้งหมด' : 'All'}
          </Seg>
          {rms?.map((r) => (
            <Seg key={r.rm_id} active={rm === r.rm_id} onClick={() => setRm(r.rm_id)}>
              {r.rm_id}
            </Seg>
          ))}
        </Segmented>
      </header>

      <div className="mt-8 flex flex-wrap items-end gap-x-12 gap-y-6 border-b border-rule pb-6">
        <Figure
          value={thb(data.total_dividend, lang)}
          label={isTh ? 'เงินปันผลที่ลูกค้าจะได้รอบนี้' : 'dividends due to customers this round'}
        />
        <div className="flex flex-wrap gap-x-10 gap-y-4">
          <Stat
            label={isTh ? 'หุ้นในรายงาน' : 'stocks in report'}
            value={num(data.items.length)}
            sub={isTh ? `ลูกค้าถือจริง ${data.held_count}` : `${data.held_count} held`}
          />
          {st ? (
            <Stat
              label={isTh ? 'พอร์ตที่วัดสไตล์ได้' : 'measurable portfolios'}
              value={num(st.measurable)}
              sub={isTh ? `จาก ${num(st.customers)} คน` : `of ${num(st.customers)}`}
            />
          ) : null}
          {st ? (
            <Stat
              label={isTh ? 'ค่ากลาง yield พอร์ต' : 'median portfolio yield'}
              value={`${st.median_yield.toFixed(1)}%`}
            />
          ) : null}
        </div>
      </div>

      {styleBars.length ? (
        <section className="mt-9">
          <Head
            note={
              isTh
                ? `วัดได้เฉพาะพอร์ตที่มีข้อมูลปันผลเกิน ${pct(st?.coverage_min ?? 0.3, 0)} — Data Book ครอบคลุมแค่หุ้นไทย`
                : `only portfolios with over ${pct(st?.coverage_min ?? 0.3, 0)} dividend coverage`
            }
          >
            {isTh ? 'สไตล์พอร์ตของลูกค้า' : 'Portfolio styles'}
          </Head>
          <div className="border-t border-rule">
            <HBars
              items={styleBars}
              max={Math.max(1, ...styleBars.map((b) => b.value))}
              format={(v) => num(v)}
              color="var(--s3)"
            />
          </div>
        </section>
      ) : null}

      <div className="mt-12 grid gap-x-12 gap-y-9 lg:grid-cols-2">
        <section className="min-w-0">
          <Head note={isTh ? 'เรียงตามเงินที่ลูกค้าจะได้' : 'ranked by dividend to customers'}>
            {isTh ? 'หุ้นปันผลเดือนนี้' : 'Dividend stocks'}
          </Head>
          <Scroll className="max-h-[520px] overflow-y-auto">
            <table className="w-full min-w-[520px] border-collapse">
              <thead>
                <tr>
                  <Th>{isTh ? 'หุ้น' : 'stock'}</Th>
                  <Th right>{isTh ? 'คน' : 'held by'}</Th>
                  <Th right>{isTh ? 'ปันผลรอบนี้' : 'this round'}</Th>
                  <Th right>69F</Th>
                  <Th>XD</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((d) => (
                  <tr key={d.entity} className="hover:bg-wash">
                    <Td>
                      <Link to={`/stock/${encodeURIComponent(d.entity)}`} className="tap">
                        <span className="tnum font-medium text-ink hover:underline">{d.entity}</span>
                      </Link>
                      <div className="text-micro text-ink-3">
                        {d.rating}
                        {d.remark === 'Estimated' ? (isTh ? ' · คาดการณ์' : ' · estimated') : ''}
                      </div>
                    </Td>
                    <Td right>{d.customers || '—'}</Td>
                    <Td right>
                      <span className="tnum font-medium text-ink">
                        {d.dividend ? thb(d.dividend, lang) : '—'}
                      </span>
                    </Td>
                    <Td right>{d.yield_forecast}%</Td>
                    <Td>{d.xd_date}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        </section>

        <section className="min-w-0">
          <Head note={isTh ? 'กดเพื่อดูพอร์ตและเหตุผล' : 'open for portfolio and reasoning'}>
            {isTh ? 'ลูกค้าที่ได้ปันผลมากสุด' : 'Top customers by dividend'}
          </Head>
          <Scroll className="max-h-[520px] overflow-y-auto">
            <table className="w-full min-w-[440px] border-collapse">
              <thead>
                <tr>
                  <Th>{isTh ? 'ลูกค้า' : 'customer'}</Th>
                  <Th right>{isTh ? 'ปันผลรอบนี้' : 'this round'}</Th>
                  <Th right>yield</Th>
                </tr>
              </thead>
              <tbody>
                {st?.top.map((r) => (
                  <tr key={r.customer_key} className="hover:bg-wash">
                    <Td>
                      <Link to={`/customers/${encodeURIComponent(r.customer_key)}`} className="tap">
                        <span className="tnum font-medium text-ink hover:underline">{r.customer_key}</span>
                      </Link>
                      <div className="text-micro text-ink-3">
                        {isTh ? st.labels[r.style].th : st.labels[r.style].en} · {r.rm_id}
                      </div>
                    </Td>
                    <Td right>
                      <span className="tnum font-medium text-ink">{thb(r.interim, lang)}</span>
                    </Td>
                    <Td right>
                      {r.yield_portfolio?.toFixed(1)}%
                      <div className="text-micro text-ink-3">{pct(r.coverage, 0)}</div>
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
