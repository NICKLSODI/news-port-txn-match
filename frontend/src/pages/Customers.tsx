import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCustomers, useHealth, useRms } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { num, thb } from '../lib/format'
import { HBars } from '../components/charts'
import { Button, Empty, Head, Loading, Scroll, Seg, Segmented, Td, Th } from '../components/ui'

const PAGE = 60
const TIERS = ['vip', 'large', 'mid', 'small'] as const

export default function Customers() {
  const { t, lang, isTh } = useI18n()
  const { data: h } = useHealth()
  const { data: rms } = useRms()
  const [persona, setPersona] = useState<string>()
  const [rm, setRm] = useState<string>()
  const [tier, setTier] = useState<string>()
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<'value' | 'matches' | 'recent'>('value')
  const [limit, setLimit] = useState(PAGE)
  const { data, isLoading } = useCustomers({ persona, rm, tier, q: q.length >= 2 ? q : undefined, sort, limit })

  const personas = Object.entries(h?.persona_counts ?? {}).sort((a, b) => b[1] - a[1])

  return (
    <div>
      <header className="flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <h1 className="text-h1 font-semibold text-ink">{t('nav.customers')}</h1>
          <p className="mt-0.5 max-w-[62ch] text-small text-ink-2">
            {isTh
              ? 'แสดงเป็นรหัสลูกค้า ไม่มีชื่อหรือเลขบัญชีในระบบนี้'
              : 'Shown as customer codes — no names or account numbers in this system'}
          </p>
        </div>
        <p className="tnum text-h1 font-semibold text-ink">{num(data?.total)}</p>
      </header>

      <div className="mt-8 grid gap-x-12 gap-y-8 lg:grid-cols-[260px_1fr]">
        <div>
          <Head>{isTh ? 'แบ่งตามสิ่งที่ถือเป็นหลัก' : 'Grouped by what they mainly hold'}</Head>
          <div className="border-t border-rule">
            <HBars
              items={personas.map(([k, v]) => ({ key: k, label: t(`persona.${k}`, k), value: v }))}
              activeKey={persona}
              onPick={(k) => setPersona(persona === k ? undefined : k)}
            />
          </div>

          <div className="mt-8">
            <Head>{isTh ? 'ตัวกรอง' : 'Filters'}</Head>
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value)
                setLimit(PAGE)
              }}
              placeholder={isTh ? 'รหัสลูกค้า หรือ ticker ที่ถือ' : 'customer key or held ticker'}
              className="mb-3 w-full rounded-out border border-rule bg-surface px-3 py-1.5 text-small text-ink outline-none placeholder:text-ink-3 focus:border-rule-strong"
            />
            <div className="space-y-2">
              <Segmented>
                <Seg active={!rm} onClick={() => setRm(undefined)}>
                  {t('k.rm')}
                </Seg>
                {rms?.map((r) => (
                  <Seg key={r.rm_id} active={rm === r.rm_id} onClick={() => setRm(r.rm_id)}>
                    {r.rm_id}
                  </Seg>
                ))}
              </Segmented>
              <Segmented>
                <Seg active={!tier} onClick={() => setTier(undefined)}>
                  {t('a.all')}
                </Seg>
                {TIERS.map((x) => (
                  <Seg key={x} active={tier === x} onClick={() => setTier(tier === x ? undefined : x)}>
                    {t(`tier.${x}`)}
                  </Seg>
                ))}
              </Segmented>
            </div>
          </div>
        </div>

        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-h2 font-semibold text-ink">
              {persona ? t(`persona.${persona}`, persona) : t('a.all')}
            </h2>
            <Segmented>
              {(['value', 'matches', 'recent'] as const).map((s) => (
                <Seg key={s} active={sort === s} onClick={() => setSort(s)}>
                  {s === 'value' ? t('k.portfolio') : s === 'matches' ? t('k.matches') : t('k.lastTrade')}
                </Seg>
              ))}
            </Segmented>
          </div>

          {isLoading ? (
            <Loading rows={12} />
          ) : !data?.items.length ? (
            <Empty />
          ) : (
            <>
              <Scroll>
                <table className="w-full min-w-[720px] border-collapse">
                  <thead>
                    <tr>
                      <Th>{t('k.customers')}</Th>
                      <Th>{t('k.persona')}</Th>
                      <Th right>{t('k.portfolio')}</Th>
                      <Th right>{t('k.holdings')}</Th>
                      <Th right>{t('k.watchlist')}</Th>
                      <Th>{isTh ? 'พฤติกรรม' : 'Activity'}</Th>
                      <Th right>{t('k.matches')}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((c) => (
                      <tr key={c.customer_key} className="hover:bg-wash">
                        <Td>
                          <Link
                            to={`/customers/${c.customer_key}`}
                            className="tnum font-medium text-ink hover:underline"
                          >
                            {c.customer_key}
                          </Link>
                          <div className="text-micro text-ink-3">
                            {c.rm_id} · {t(`ac.${c.dominant_asset_class}`, c.dominant_asset_class)}
                          </div>
                        </Td>
                        <Td className="text-ink-2">{t(`persona.${c.persona}`, c.persona)}</Td>
                        <Td right>{thb(c.portfolio_value, lang)}</Td>
                        <Td right className="text-ink-2">
                          {c.n_holdings}
                        </Td>
                        <Td right className="text-ink-2">
                          {c.n_watchlist}
                        </Td>
                        <Td className="text-ink-2">
                          {t(`freq.${c.trade_frequency}`)}
                          {c.days_since_last_trade < 9999 ? (
                            <span className="tnum ml-1.5 text-micro text-ink-3">{c.days_since_last_trade}d</span>
                          ) : null}
                        </Td>
                        <Td right className="font-semibold">
                          {num(c.n_matches)}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Scroll>
              {data.total > data.items.length ? (
                <p className="mt-6 text-center">
                  <Button onClick={() => setLimit(limit + PAGE)}>
                    {t('a.showMore')} · {num(data.total - data.items.length)}
                  </Button>
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
