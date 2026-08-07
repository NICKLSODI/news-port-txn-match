import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useActions, useAiHealth, useHealth } from '../lib/api'
import type { AiResult } from '../lib/api'
import type { Alert } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { dayMonth, num, time } from '../lib/format'
import { Button, Spinner } from './ui'

/**
 * เมนูแบ่งสองกลุ่ม — ของที่ RM ใช้ทุกวัน กับของที่ผู้ดูแลระบบเข้านาน ๆ ครั้ง
 * เดิมเรียงเก้ารายการติดกันหมด ทำให้หน้าที่ใช้บ่อยกับหน้าที่ตั้งค่าดูสำคัญเท่ากัน
 */
const NAV = [
  { to: '/', key: 'nav.rm' },           // เริ่มวันที่นี่ — วันนี้ต้องคุยเรื่องอะไรกับใคร
  { to: '/stock', key: 'nav.stock' },
  { to: '/today', key: 'nav.today' },
  { to: '/news', key: 'nav.news' },
  { to: '/dividends', key: 'nav.dividends' },
  { to: '/customers', key: 'nav.customers' },
] as const

const NAV_ADMIN = [
  { to: '/upload', key: 'nav.upload' },
  { to: '/reports', key: 'nav.reports' },
  { to: '/spec', key: 'nav.spec' },
  { to: '/settings', key: 'nav.settings' },
] as const

function useTheme() {
  const [theme, setTheme] = useState<'light' | 'dark' | null>(() => {
    try {
      return (localStorage.getItem('mp-theme') as 'light' | 'dark') || null
    } catch {
      return null
    }
  })
  useEffect(() => {
    const el = document.documentElement
    if (theme) el.setAttribute('data-theme', theme)
    else el.removeAttribute('data-theme')
    try {
      if (theme) localStorage.setItem('mp-theme', theme)
      else localStorage.removeItem('mp-theme')
    } catch {}
  }, [theme])
  const isDark =
    theme === 'dark' || (theme === null && window.matchMedia?.('(prefers-color-scheme: dark)').matches)
  return { isDark, toggle: () => setTheme(isDark ? 'light' : 'dark') }
}

const ALERT_TONE: Record<Alert['level'], string> = {
  high: 'var(--critical)',
  medium: 'var(--serious)',
  low: 'var(--warning)',
  info: 'var(--warning)',
}

/**
 * แถบเตือน — ของใหม่ที่ระบบอ่านไม่ออกเคยไปโผล่แค่ในหน้ารายงานที่ต้องเปิดหาเอง
 * หมวดข่าวใหม่จึงหายเงียบได้เป็นเดือน แถบนี้ทำให้ต้องเห็นก่อนถึงจะทำงานต่อได้
 */
function Alerts({ items }: { items: Alert[] }) {
  const { isTh } = useI18n()
  const [hidden, setHidden] = useState<string[]>([])
  const show = items.filter((a) => !hidden.includes(a.kind))
  if (!show.length) return null

  return (
    <div className="border-b border-rule">
      {show.map((a) => (
        <div
          key={a.kind}
          className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2 sm:px-8"
          style={{ borderLeft: `3px solid ${ALERT_TONE[a.level]}` }}
        >
          <span
            className="text-small font-semibold"
            style={{ color: ALERT_TONE[a.level] }}
          >
            {isTh ? a.th : a.en}
          </span>
          {a.to ? (
            <Link to={a.to} className="text-micro text-ink-2 underline hover:text-ink">
              {isTh ? 'ไปดู' : 'Open'}
            </Link>
          ) : null}
          <button
            type="button"
            onClick={() => setHidden((v) => [...v, a.kind])}
            className="tap ml-auto text-micro text-ink-3 hover:text-ink-2"
          >
            {isTh ? 'ซ่อน' : 'Dismiss'}
          </button>
        </div>
      ))}
    </div>
  )
}

export default function Layout() {
  const { t, lang, setLang } = useI18n()
  const { isDark, toggle } = useTheme()
  const { data: h } = useHealth()
  const a = useActions()
  const fetching = a.fetchNews.isPending
  const reading = a.aiRead.isPending
  // นับเฉพาะข่าวของวันล่าสุด = ชุดเดียวกับที่ปุ่มนี้สั่งอ่าน และถามซ้ำระหว่างกำลังอ่าน
  const ai = useAiHealth('today', reading)
  const aiDone = a.aiRead.data as AiResult | undefined
  const AI_BATCH = 8
  // Data Book ออกเดือนละครั้ง — ปุ่มโผล่เฉพาะตอนที่ยังไม่ได้ดึงของเดือนปัจจุบัน
  // ไม่งั้นปุ่มที่กดแล้วไม่มีอะไรเกิดขึ้นจะกินที่บนแถบตลอดทั้งเดือน
  const divPending = a.fetchDividends.isPending
  const divMonth = (h?.dividends_ingested_at ?? '').slice(0, 7)
  const divStale = divMonth !== new Date().toISOString().slice(0, 7)
  const loc = useLocation()
  const [open, setOpen] = useState(false)
  useEffect(() => setOpen(false), [loc.pathname])

  const navLink = (n: { to: string; key: string }) => (
    <NavLink
      key={n.to}
      to={n.to}
      end={n.to === '/'}
      className={({ isActive }) =>
        // หน้ารายละเอียดหุ้น /stock/<ตัว> ให้ไฮไลต์เมนู "หาจากหุ้น" ด้วย
        // ไม่งั้นเปิดหน้าหุ้นตัวหนึ่งแล้วเมนูไม่ไฮไลต์อะไรเลย ดูเหมือนหลุดออกจากระบบ
        `tap flex items-center gap-2 rounded-in px-3 py-[7px] text-body ${
          isActive
            ? 'bg-wash font-semibold text-ink'
            : 'text-ink-2 hover:text-ink'
        }`
      }
    >
      <span className="flex-1">{t(n.key)}</span>
      {n.to === '/reports' && h && h.weak_evidence > 0 ? (
        <span className="tnum text-micro text-ink-3">{num(h.weak_evidence)}</span>
      ) : null}
    </NavLink>
  )

  const lag = h?.customer_data_lag_days
  const stale = lag !== null && lag !== undefined && lag > 7
  // แถบวันที่ข้อมูลบนหัวจอบอกเรื่องเดียวกับ alert ตัว stale อยู่แล้ว ไม่ต้องซ้ำสองที่
  const alerts = (h?.alerts ?? []).filter((a) => a.kind !== 'stale_customer_data')

  return (
    <div className="min-h-full lg:grid lg:grid-cols-[210px_1fr]">
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-[210px] flex-col border-r border-rule bg-surface transition-transform lg:static lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="px-5 pt-6 pb-7">
          <div className="text-h2 leading-tight font-semibold text-ink">{t('app.title')}</div>
          <div className="mt-0.5 text-micro text-ink-3">{t('app.subtitle')}</div>
        </div>

        <nav className="flex-1 px-2">
          {NAV.map(navLink)}

          {/* ส่งอีเมลเป็น "การกระทำ" ไม่ใช่หน้าไว้ดู และเป็นปลายทางของงานทั้งวัน
              (ใส่ข้อมูล -> ดูคิว -> ส่งให้ทีม) จึงแยกออกมาเป็นปุ่มของตัวเอง
              เคยอยู่ปนกับหน้าตั้งค่าที่เข้านาน ๆ ครั้ง ทำให้หาไม่เจอทั้งที่ต้องใช้ทุกวัน */}
          <NavLink
            to="/mail"
            className={({ isActive }) =>
              `tap mt-4 flex items-center gap-2 rounded-in border px-3 py-2.5 text-body ${
                isActive ? 'font-semibold' : ''
              }`
            }
            style={({ isActive }) => ({
              borderColor: 'var(--accent)',
              background: isActive ? 'var(--accent)' : 'var(--accent-wash)',
              color: isActive ? 'var(--accent-ink)' : 'var(--accent)',
            })}
          >
            <span aria-hidden>✉</span>
            <span className="flex-1">{t('nav.mail')}</span>
          </NavLink>

          <p className="mt-6 mb-1 border-t border-rule px-3 pt-4 text-micro text-ink-3">
            {t('nav.admin')}
          </p>
          {NAV_ADMIN.map(navLink)}
        </nav>

        <div className="border-t border-rule px-5 py-4">
          <p className="text-micro leading-relaxed text-ink-3">{t('msg.notSentToClient')}</p>
        </div>
      </aside>

      {open ? (
        <button
          type="button"
          aria-label="close"
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-20 bg-black/25 lg:hidden"
        />
      ) : null}

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-rule bg-paper px-4 py-2 sm:px-8">
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="tap rounded-in border border-rule px-2 py-1 text-small text-ink-2 lg:hidden"
          >
            {t('nav.menu')}
          </button>

          {h?.customer_data_as_of ? (
            <p
              className="min-w-0 truncate text-micro"
              style={{ color: stale ? 'var(--serious)' : 'var(--ink-3)' }}
              title={`holdings as of ${h.holdings_as_of}`}
            >
              {t('msg.dataLag')} {h.customer_data_as_of}
              {lag ? ` · ${lag} ${t('msg.daysAgo')}` : ''}
            </p>
          ) : null}

          <div className="ml-auto flex items-center gap-3">
            <div className="flex flex-col items-end gap-0.5">
              <Button variant="primary" disabled={fetching} onClick={() => a.fetchNews.mutate(1)}>
                {fetching ? (
                  <span className="inline-flex items-center gap-1.5">
                    <Spinner />
                    {t('set.running')}
                  </span>
                ) : (
                  t('a.refreshNews')
                )}
              </Button>
              <span className="text-micro whitespace-nowrap text-ink-3" title={h?.news_ingested_at ?? undefined}>
                {h?.news_ingested_at
                  ? `${lang === 'th' ? 'ดึงล่าสุด' : 'last fetched'} ${dayMonth(h.news_ingested_at, lang)} ${time(h.news_ingested_at)}`
                  : lang === 'th'
                    ? 'ยังไม่เคยดึงข่าว'
                    : 'never fetched'}
              </span>
            </div>
            {divStale ? (
              <div className="flex flex-col items-end gap-0.5">
                <Button disabled={divPending} onClick={() => a.fetchDividends.mutate()}>
                  {divPending ? (
                    <span className="inline-flex items-center gap-1.5">
                      <Spinner />
                      {lang === 'th' ? 'กำลังดึง Data Book…' : 'fetching Data Book…'}
                    </span>
                  ) : lang === 'th' ? (
                    'ดึงตารางปันผลเดือนนี้'
                  ) : (
                    "fetch this month's dividends"
                  )}
                </Button>
                <span className="text-micro whitespace-nowrap text-ink-3">
                  {a.fetchDividends.error ? (
                    <span style={{ color: 'var(--critical)' }}>{String(a.fetchDividends.error)}</span>
                  ) : h?.dividends_ingested_at ? (
                    lang === 'th'
                      ? `ของเดือน ${divMonth} · มีรายงานใหม่แล้ว`
                      : `have ${divMonth} · newer report out`
                  ) : lang === 'th' ? (
                    'ยังไม่เคยดึง'
                  ) : (
                    'never fetched'
                  )}
                </span>
              </div>
            ) : null}
            {ai.data?.available ? (
              <div className="flex flex-col items-end gap-0.5">
                <Button disabled={reading} onClick={() => a.aiRead.mutate({ limit: AI_BATCH, date: 'today' })}>
                  {reading ? (
                    <span className="inline-flex items-center gap-1.5">
                      <Spinner />
                      {lang === 'th' ? 'AI กำลังอ่าน…' : 'AI reading…'}
                    </span>
                  ) : lang === 'th' ? (
                    'ให้ AI อ่านข่าววันนี้'
                  ) : (
                    "AI-read today's news"
                  )}
                </Button>
                {/* ระหว่างกำลังอ่านต้องโชว์ตัวนับสด ไม่ใช่สรุปของรอบก่อน — react-query
                    เก็บผลรอบเดิมไว้ตอน mutation รอบใหม่กำลังทำงาน ถ้าไม่แยกเคสจะเห็น
                    เลขเดิมค้างทั้งที่กำลังอ่านอยู่ */}
                <span className="text-micro whitespace-nowrap text-ink-3">
                  {reading || !aiDone
                    ? lang === 'th'
                      ? `อ่านข่าววันนี้แล้ว ${num(ai.data.read)}/${num(ai.data.readable)}`
                      : `read ${num(ai.data.read)}/${num(ai.data.readable)} today`
                    : lang === 'th'
                      ? `อ่านไป ${num(aiDone.done)} · เพิ่มหุ้น ${num(aiDone.entities_added)} · รวมวันนี้ ${num(ai.data.read)}/${num(ai.data.readable)}`
                      : `+${num(aiDone.done)} · ${num(aiDone.entities_added)} added · ${num(ai.data.read)}/${num(ai.data.readable)} today`}
                </span>
              </div>
            ) : null}
            <div className="flex items-center gap-4 text-micro">
            <div className="flex items-center gap-1.5">
              {(['th', 'en'] as const).map((l) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => setLang(l)}
                  aria-pressed={lang === l}
                  className={`tap uppercase ${lang === l ? 'font-semibold text-ink' : 'text-ink-3 hover:text-ink-2'}`}
                >
                  {l}
                </button>
              ))}
            </div>
            <button type="button" onClick={toggle} className="tap text-ink-3 hover:text-ink-2">
              {isDark ? t('theme.light') : t('theme.dark')}
            </button>
            </div>
          </div>
        </header>

        <Alerts items={alerts} />

        <main className="min-w-0 flex-1 px-4 py-7 sm:px-8 sm:py-9">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
