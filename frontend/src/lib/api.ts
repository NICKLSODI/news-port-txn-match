import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

const BASE = '/api'

/**
 * id ของข้อย่อยเป็นรูปแบบ "<parent>#<n>" — ถ้าไม่ encode ตัว # จะกลายเป็น fragment
 * เบราว์เซอร์จะตัดทิ้งก่อนส่ง แล้วเซิร์ฟเวอร์คืนบทความแม่มาแทนแบบเงียบ ๆ
 */
const enc = (v: string | undefined) => encodeURIComponent(v ?? '')

async function get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  }
  const url = `${BASE}${path}${qs.size ? `?${qs}` : ''}`
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

async function put<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

/* ------------------------------------------------------------------ types */

/** สิ่งที่ระบบต้องบอกเอง ไม่ใช่รอให้คนไปเปิดหา */
export type Alert = {
  level: 'high' | 'medium' | 'low' | 'info'
  kind: 'unknown_subcategory' | 'new_unmapped' | 'stale_customer_data'
  n: number
  th: string
  en: string
  to?: string
}

export type Health = {
  customers: number
  holdings: number
  transactions: number
  articles: number
  segments: number
  matches: number
  unmapped: number
  weak_evidence: number
  customer_data_as_of: string | null
  customer_data_lag_days: number | null
  holdings_as_of: string | null
  /** ช่วงเวลาที่ไฟล์ธุรกรรมครอบคลุม — คนละเรื่องกับวันที่นำเข้า */
  txn_from: string | null
  txn_to: string | null
  customers_ingested_at: string | null
  news_ingested_at: string | null
  news_api_total: number | null
  dividends_ingested_at: string | null
  matched_at: string | null
  score_threshold: number
  persona_counts: Record<string, number>
  overrides: Record<string, number>
  alerts: Alert[]
}

export type Article = {
  article_id: string
  record_type: 'article' | 'segment'
  parent_article_id: string | null
  segment_no: number | null
  segment_text?: string | null
  title: string
  url: string
  url_full?: string
  summary?: string
  subcategory: string
  subcategory_name: string | null
  content_type: string
  mode: 'realtime' | 'digest'
  importance: number
  urgency: 'now' | 'this_week' | 'low'
  trigger_at: string
  display_at: string | null
  entity: string
  sector: string
  macro_topic: string
  image_url: string | null
  entity_source?: string
  entity_confidence: string
  auto_grade: 'confirmed' | 'auto_verified' | 'weak' | null
  auto_reason_th?: string | null
  auto_reason_en?: string | null
  auto_checks?: string | null
  ai_direction?: 'up' | 'down' | 'mixed' | 'position_dependent' | 'unknown' | null
  ai_at?: string | null
  ai_reason_th?: string | null
  ai_reason?: string | null
  evidence?: string | null
  n_matches: number
  source?: string
  pillar?: string
  category?: string
  product_type?: string
  role?: string
  segments?: Article[]
  level_summary?: { level: string; n: number; avg_score: number }[]
  rm_summary?: { rm_id: string; n: number }[]
  persona_summary?: { persona: string; n: number }[]
  parent?: { article_id: string; title: string; url: string }
}

export type Match = {
  customer_key: string
  rm_id: string
  persona: string
  level: string
  matched_entity: string
  score: number
  reason_th: string
  reason_en: string
  instrument_label: string
  holding_value: number
  evidence: string
  portfolio_value: number
  portfolio_tier: string
  trade_frequency: string
  days_since_last_trade: number
  unrealized_state: string
  n_holdings: number
  n_watchlist: number
}

export type Evidence = {
  hits: { level: string; entity: string; rule: string; th: string; en: string; label: string; why: string }[]
  factors: Record<string, number | string | null>
  customer: Record<string, unknown>
  coverage: { sector?: string; rating?: string; esg?: string; last_close?: number; target_price?: number }
}

export type Customer = {
  customer_key: string
  rm_id: string
  persona: string
  dominant_asset_class: string
  portfolio_value: number
  portfolio_tier: string
  trade_frequency: string
  days_since_last_trade: number
  txn_count: number
  unrealized_state: string
  n_holdings: number
  n_watchlist: number
  n_matches?: number
  asset_mix?: string
  sector_exposure?: string
  holdings?: string
  watchlist?: string
  labels?: string
  holding_rows?: {
    product_code: string
    asset_class: string
    entity: string | null
    entity_kind: string
    instrument_label: string
    map_rule: string
    holding_value: number | null
    unrealized_pnl: number | null
    as_of_date: string
  }[]
  recent_txn?: {
    txn_date: string
    txn_type: string
    txn_direction: string
    product_code: string
    entity: string | null
    asset_class: string
    txn_units: number | null
    txn_value: number | null
  }[]
  style?: PortfolioStyle | null
  dividend_rows?: {
    entity: string
    holding_value: number
    yield_interim: number
    yield_forecast: number
    xd_date: string
    pay_date: string
    rating: string
    remark: 'Official' | 'Estimated'
    dividend: number
  }[]
  matches?: (Pick<Match, 'level' | 'score' | 'matched_entity' | 'reason_th' | 'reason_en'> & {
    article_id: string
    title: string
    url: string
    subcategory: string
    trigger_at: string
    importance: number
    urgency: string
  })[]
}

export type Today = {
  date: string
  today: string
  is_today: boolean
  latest_with_news: string | null
  rm_id: string | null
  counts: Record<string, number>
  total_matches: number
  buckets: Record<'morning' | 'intraday' | 'evening', Article[]>
}

export type Signal = {
  tier: number
  kind: string
  direction: 'up' | 'down' | 'flat'
  th: string
  en: string
  phrase?: string
  on?: string[]
  entity?: string
  rating?: string
  target_price?: number | null
  upside?: number | null
  source_th: string
  source_en: string
}

export type TalkPoint = { kind: string; th: string; en: string; source_th: string; source_en: string }

export type Briefing = {
  article_id: string
  overall: 'up' | 'down' | 'mixed' | 'flat' | 'position_dependent' | 'unknown'
  strongest_tier: number | null
  signals: Signal[]
  two_sided: { topic: string; affects: string[] }[]
  talking_points: TalkPoint[]
  /** AI-02 — ทำไม AI ถึงไม่สรุปทิศทาง (ว่าง = กฎเป็นคนสรุปไม่ได้เอง ไม่เกี่ยวกับ AI) */
  no_call_th: string
  /** รหัสเหตุผล — ใช้แปล i18n ฝั่งอังกฤษ ("" = ยังไม่ได้อ่าน หรือกฎสรุปไม่ได้เอง) */
  no_call_code: string
  /** ส่วน "มุมมองของ InnovestX" จากตัวบทความ ("" = บทความนี้ไม่มีส่วนนี้) */
  invx_view: string
  /** ส่วนเดียวกันแยกเป็นข้อ ๆ ตามที่บทความแบ่งไว้เอง — ว่างได้ถ้าเนื้อหาเป็นย่อหน้าเดียว */
  invx_points: string[]
}

export const useBriefing = (id?: string) =>
  useQuery({
    queryKey: ['briefing', id],
    queryFn: () => get<Briefing>(`/articles/${enc(id)}/briefing`),
    enabled: !!id,
    ...stale,
  })

export type SpecGap = { id: string; ref: string; th: string; en: string; assumed: string }

/* ------------------------------------------------------------------ hooks */

const stale = { staleTime: 60_000 }

export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: () => get<Health>('/health'), ...stale })

export const useToday = (date?: string, rm?: string) =>
  useQuery({ queryKey: ['today', date, rm], queryFn: () => get<Today>('/today', { date, rm }), ...stale })

export const useDates = () =>
  useQuery({
    queryKey: ['dates'],
    queryFn: () => get<{ d: string; articles: number; matches: number }[]>('/dates', { limit: 40 }),
    ...stale,
  })

export const useArticles = (p: Record<string, unknown>) =>
  useQuery({
    queryKey: ['articles', p],
    queryFn: () => get<{ total: number; items: Article[] }>('/articles', p),
    ...stale,
  })

export const useArticle = (id?: string) =>
  useQuery({ queryKey: ['article', id], queryFn: () => get<Article>(`/articles/${enc(id)}`), enabled: !!id, ...stale })

export const useArticleMatches = (id?: string, p: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: ['matches', id, p],
    queryFn: () => get<{ total: number; items: Match[] }>(`/articles/${enc(id)}/matches`, p),
    enabled: !!id,
    ...stale,
  })

export const useRms = () =>
  useQuery({
    queryKey: ['rms'],
    queryFn: () =>
      get<{ rm_id: string; customers: number; aum_mb: number; matches: number; articles: number }[]>('/rms'),
    ...stale,
  })

/** หนึ่งคนที่ควรโทร — "เงินที่ข่าวแตะ" คือมูลค่าที่เขาถือในตัวที่ข่าวพูดถึง */
export type QueueRow = {
  customer_key: string
  matched_value: number
  top_score: number
  n_entities: number
  persona: string
  portfolio_value: number
  portfolio_tier: string
  days_since_last_trade: number
  unrealized_state: string
  n_holdings: number
  share_of_portfolio: number | null
  entities: { entity: string; value: number }[]
  top_article_id: string | null
  top_title: string | null
  top_trigger_at: string | null
  top_reason_th: string | null
  top_reason_en: string | null
  top_entity: string | null
  top_level: string | null
  top_entity_value: number
}

export type Queue = {
  rm_id: string
  date: string | null
  sort: string
  total: number
  value_total: number
  items: QueueRow[]
}

/** ข่าวหนึ่งชิ้นในมุม "ข่าวนี้ไปแตะเงินใคร" */
export type RmNewsRow = {
  article_id: string
  title: string
  url: string
  trigger_at: string
  subcategory: string
  subcategory_name: string | null
  record_type: 'article' | 'segment'
  parent_article_id: string | null
  segment_no: number | null
  customers: number
  matched_value: number
  top_score: number
  n_hold: number
  overall: string
  strongest_tier: number | null
  why_th: string | null
  why_en: string | null
  top_customers: {
    customer_key: string
    matched_entity: string
    level: string
    score: number
    holding_value: number
    portfolio_tier: string
    persona: string
    portfolio_value: number
  }[]
}

export type RmNews = {
  rm_id: string
  date: string | null
  total: number
  value_total: number
  items: RmNewsRow[]
}

// sort=value (ค่าเริ่มต้น) = โทรคนที่มีเงินอยู่กับข่าวมากสุดก่อน · sort=score = ตามความแรงของข่าว
export const useRmQueue = (rm?: string, date?: string, sort = 'value') =>
  useQuery({
    queryKey: ['queue', rm, date, sort],
    queryFn: () => get<Queue>(`/rm/${enc(rm)}/queue`, { date, sort }),
    enabled: !!rm,
    ...stale,
  })

/** หนึ่งหุ้นในมุม "ข่าววันนี้ทำให้ตัวไหนต้องโทรคุย" */
export type RmEntityRow = {
  entity: string
  matched_value: number
  customers: number
  n_hold: number
  top_score: number
  top_level: string
  n_articles: number
  overall: string
  directions: Record<string, number>
  lead: {
    article_id: string
    title: string
    trigger_at: string
    overall: string
    why_th: string | null
    why_en: string | null
    /** ส่วน "มุมมองของ InnovestX" ของข่าวชิ้นนี้ ("" = ไม่มี) */
    invx_view: string
  } | null
  /** บทความชี้เองว่าเป็นหุ้นเด่นประจำวัน (GAP-23) */
  top_pick: boolean
  /** own = มีข่าวเจาะตัวเอง · brief = ถูกเอ่ยในสรุปรายวันเท่านั้น */
  coverage: 'own' | 'brief'
  top_customers: {
    customer_key: string
    holding_value: number
    level: string
    score: number
    portfolio_tier: string
    persona: string
    portfolio_value: number
  }[]
}

export type RmEntities = {
  rm_id: string
  date: string | null
  total: number
  value_total: number
  items: RmEntityRow[]
}

export const useRmEntities = (rm?: string, date?: string) =>
  useQuery({
    queryKey: ['rmentities', rm, date],
    queryFn: () => get<RmEntities>(`/rm/${enc(rm)}/entities`, { date }),
    enabled: !!rm,
    ...stale,
  })

export const useRmNews = (rm?: string, date?: string) =>
  useQuery({
    queryKey: ['rmnews', rm, date],
    queryFn: () => get<RmNews>(`/rm/${enc(rm)}/news`, { date }),
    enabled: !!rm,
    ...stale,
  })

export const useCustomers = (p: Record<string, unknown>) =>
  useQuery({
    queryKey: ['customers', p],
    queryFn: () => get<{ total: number; items: Customer[] }>('/customers', p),
    ...stale,
  })

export const useCustomer = (key?: string) =>
  useQuery({ queryKey: ['customer', key], queryFn: () => get<Customer>(`/customers/${enc(key)}`), enabled: !!key, ...stale })

export type Severity = 'high' | 'medium' | 'low'

export type UnmappedItem = {
  id: number
  bucket: string
  raw: string
  rule: string
  reason: string
  n: number
  sample_ref: string
  first_seen: string | null
  last_seen: string | null
  /** ผลกระทบจริง — คำนวณจากพอร์ต ไม่ใช่จำนวนครั้งที่เจอ */
  customers: number
  value_mb: number
  txn_rows: number
  severity: Severity
  impact_th: string
  impact_en: string
  is_new: boolean
}

export type UnmappedReport = {
  by_bucket: { bucket: string; distinct_n: number; total: number }[]
  by_severity: { severity: Severity; distinct_n: number; total: number; value_mb: number; new_n: number }[]
  new_days: number
  items: UnmappedItem[]
}

export const useUnmapped = (bucket?: string, severity?: string) =>
  useQuery({
    queryKey: ['unmapped', bucket, severity],
    queryFn: () => get<UnmappedReport>('/reports/unmapped', { bucket, severity }),
    ...stale,
  })

export type GradedArticle = {
  article_id: string
  record_type: string
  segment_no: number | null
  title: string
  url: string
  subcategory: string
  subcategory_name: string | null
  entity: string
  entity_source: string
  entity_confidence: string
  auto_grade: 'confirmed' | 'auto_verified' | 'weak' | null
  auto_reason_th: string | null
  auto_reason_en: string | null
  auto_checks: string | null
  evidence: string | null
  trigger_at: string
  n_matches: number
}

export type GradeCheck = { check: string; ok: boolean; th: string; en: string; rule: string }

export const useVerification = (grade?: string) =>
  useQuery({
    queryKey: ['verification', grade],
    queryFn: () =>
      get<{
        counts: { grade: string; n: number; matches: number }[]
        items: GradedArticle[]
      }>('/reports/verification', { grade }),
    ...stale,
  })

export const useCoverage = () =>
  useQuery({
    queryKey: ['coverage'],
    queryFn: () =>
      get<{
        by_persona: { persona: string; customers: number; never_matched: number; aum_mb: number }[]
        by_asset_class: {
          asset_class: string
          customers: number
          instruments: number
          value_mb: number
          covered: number
        }[]
        top_uncovered: { entity: string; asset_class: string; customers: number; value_mb: number }[]
      }>('/reports/coverage'),
    ...stale,
  })

export const useRelated = () =>
  useQuery({
    queryKey: ['related'],
    queryFn: () =>
      get<{
        seed_groups: { group: string; members: string[] }[]
        learned: { a: string; b: string; n: number; article_ids: string }[]
      }>('/reports/related', { min_count: 2 }),
    ...stale,
  })

export const useSpecGaps = () =>
  useQuery({ queryKey: ['gaps'], queryFn: () => get<{ gaps: SpecGap[]; n: number }>('/spec-gaps'), staleTime: Infinity })

export const useReference = () =>
  useQuery({
    queryKey: ['reference'],
    queryFn: () =>
      get<{
        levels: Record<string, number>
        personas: Record<string, { th: string; en: string }>
        sectors: string[]
        coverage_list_size: number
        dr_resolved: number
        dr_pending: number
        content_inventory: {
          category: string
          subcategory: string
          name: string
          per_week: number | null
          has_ticker_pct: string
          product_type: string
          role: string
          decision: string
        }[]
        macro_topics: Record<string, string[]>
        macro_banned: string[]
      }>('/reference'),
    staleTime: Infinity,
  })

/* ------------------------------------------------- มุมมองรายสินทรัพย์ */

export type EntityHit = { entity: string; holders: number; value: number }

export type EntityNews = {
  article_id: string
  title: string
  url: string
  subcategory: string
  subcategory_name: string | null
  trigger_at: string
  record_type: 'article' | 'segment'
  parent_article_id: string | null
  segment_no: number | null
  n_matches: number
  auto_grade: string | null
  is_today: boolean
  overall: string
  strongest_tier: number | null
  signals: { tier: number; kind: string; direction: string; th: string; en: string; phrase?: string }[]
}

export type EntityView = {
  entity: string
  coverage: { sector?: string; rating?: string; target_price?: number; last_close?: number } | null
  holders: {
    customer_key: string
    rm_id: string
    persona: string
    portfolio_value: number
    portfolio_tier: string
    unrealized_state: string
    days_since_last_trade: number
    n_holdings: number
    holding_value: number
    unrealized_pnl: number
    labels: string[]
    product_codes: string
    share_of_portfolio: number | null
  }[]
  holders_total: number
  value_total: number
  /** ตัวกรองที่ใช้อยู่ — null = ภาพรวมทั้งบริษัท */
  rm: string | null
  /** แยกตามผู้ดูแล เรียงตามมูลค่า · ยอดในนี้เป็นของทั้งบริษัทเสมอ ไม่ถูกกรองด้วย rm */
  by_rm: {
    rm_id: string
    customers: number
    value: number
    unrealized_pnl: number | null
    n_with_pnl: number
    n_rows: number
    book_value: number | null
    share_of_book: number | null
  }[]
  watchers: {
    customer_key: string
    rm_id: string
    persona: string
    portfolio_value: number
    days_since_last_trade: number
    last_traded: string
  }[]
  news: EntityNews[]
  news_days: number
  direction_today: string
  direction_week: Record<string, number>
}

/** สินทรัพย์ที่ควรสนใจวันนี้ — ทุกแถวต้องบอกได้ว่าขึ้นมาเพราะอะไร */
export type Highlight = {
  entity: string
  holders: number
  value: number
  pnl: number | null
  matched_today: number
  news_recent: number
  news_week: number
  overall: string
  best_tier: number
  why_th: string | null
  why_en: string | null
  phrase: string | null
  article_id: string | null
  title: string | null
  directions: Record<string, number>
}

export type Highlights = {
  date: string
  days: number
  week: number
  rm: string | null
  with_news_in_portfolio: Highlight[]
  with_news_not_held: Highlight[]
  negative_and_losing: Highlight[]
  most_talked_this_week: Highlight[]
  most_held: { entity: string; holders: number; value: number; pnl: number | null }[]
}

// rm ที่ส่งเข้ามาเป็นตัวกรองของหน้าจอ ไม่ส่ง = ภาพรวมทั้งบริษัท
export const useHighlights = (days = 1, week = 7, rm?: string) =>
  useQuery({
    queryKey: ['highlights', days, week, rm],
    queryFn: () => get<Highlights>('/entities/highlights', { days, week, rm }),
    ...stale,
  })

export const useEntitySearch = (q: string) =>
  useQuery({
    queryKey: ['entities', q],
    queryFn: () => get<EntityHit[]>('/entities', { q, limit: 15 }),
    enabled: q.trim().length >= 1,
    ...stale,
  })

export const useEntityView = (entity?: string, days = 7, rm?: string) =>
  useQuery({
    queryKey: ['entity', entity, days, rm],
    queryFn: () => get<EntityView>(`/entities/${enc(entity)}`, { days, rm }),
    enabled: !!entity,
    ...stale,
  })

export type Bar = { d: string; o: number; h: number; l: number; c: number; v: number }

export type ChartData = {
  entity: string
  provider: 'tradingview' | 'yahoo' | 'none'
  range: string
  tradingview: string | null
  symbol: string | null
  note: string | null
  cached?: boolean
  fetched_at?: string | null
  series?: {
    bars: Bar[]
    last: number
    currency: string | null
    exchange: string | null
    change_pct: number | null
    day_change_pct: number | null
    w52_low: number | null
    w52_high: number | null
  } | null
  news_marks?: { d: string; n: number; dirs: Record<string, number>; title: string; article_id: string }[]
}

// ฝั่งเซิร์ฟเวอร์ cache 30 นาทีอยู่แล้ว และเป็นราคาปิดรายวัน ไม่ต้องดึงบ่อย
export const useChart = (entity?: string, range = '6mo') =>
  useQuery({
    queryKey: ['chart', entity, range],
    queryFn: () => get<ChartData>(`/entities/${enc(entity)}/chart`, { range }),
    enabled: !!entity,
    staleTime: 5 * 60_000,
    retry: 0,
  })

/* ------------------------------------------------------------------ upload */

export type CheckNote = { code: string; th: string; en: string; detail?: Record<string, unknown> | null }

export type FileReport = {
  kind: 'portfolio' | 'txn'
  filename: string
  size: number
  rows: number
  sheet: string | null
  all_sheets?: string[]
  columns: string[]
  errors: CheckNote[]
  warnings: CheckNote[]
  stats: {
    customers?: number
    rms?: number
    date_min?: string
    date_max?: string
    blank_product_code?: number
    blank_customer_key?: number
  }
  ok?: boolean
}

export type UploadReport = {
  ok: boolean
  portfolio: FileReport
  txn: FileReport
  cross: {
    ok?: boolean
    errors: CheckNote[]
    warnings: CheckNote[]
    stats: {
      customers_portfolio?: number
      customers_txn?: number
      customers_both?: number
      only_portfolio?: number
      only_txn?: number
      date_gap_days?: number
    }
  }
}

export type UploadResult = {
  report: UploadReport
  installed: {
    archived: string[]
    removed_stale: string[]
    archive_dir: string | null
    portfolio: string
    txn: string
    problems: { file: string; step: string; error: string }[]
  }
  ingested: {
    customers: number
    holdings_rows: number
    txn_rows: number
    skipped_cash_rows_R1_6: number
    skipped_no_customer_key_R1_3: Record<string, number>
    data_as_of: string
    unknown_enums: string[]
    persona_counts: Record<string, number>
  }
  matched?: { articles_matched: number; matches: number }
}

/** อัปโหลดผ่าน XHR เพราะต้องรายงานความคืบหน้า — ไฟล์ TXN จริงหลายสิบเมกะไบต์ */
export function postFiles<T>(
  path: string,
  files: { portfolio: File; txn: File },
  opts: { match?: boolean; onProgress?: (pct: number) => void } = {},
): Promise<T> {
  const fd = new FormData()
  fd.append('portfolio', files.portfolio)
  fd.append('txn', files.txn)
  if (opts.match !== undefined) fd.append('match', String(opts.match))

  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}${path}`)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) opts.onProgress?.(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      let body: unknown = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        body = xhr.responseText
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(body as T)
      // 422 ของ FastAPI ห่อรายละเอียดไว้ใน detail — คลี่ report ออกมาให้หน้าจอใช้ได้
      const detail = (body as { detail?: unknown })?.detail
      const err = new Error(
        typeof detail === 'string'
          ? detail
          : ((detail as { message?: string })?.message ?? `${xhr.status} ${xhr.statusText}`),
      ) as Error & { report?: UploadReport; status?: number }
      err.status = xhr.status
      err.report = (detail as { report?: UploadReport })?.report
      reject(err)
    }
    xhr.onerror = () => reject(new Error('เชื่อมต่อเซิร์ฟเวอร์ไม่ได้'))
    xhr.send(fd)
  })
}

/** สถานะของ Claude Code บนเครื่อง — ไม่มีก็ซ่อนปุ่ม ไม่ต้องให้คนกดแล้วเจอ error */
export type AiHealth = {
  /** วันที่ตัวเลขนับอยู่ (null = นับทั้งคลัง) */
  date?: string | null
  available: boolean
  bin: string | null
  model: string
  readable: number
  read: number
  with_direction: number
}

export type AiResult = {
  tried: number
  done: number
  problems: number
  entities_added: number
  dropped: number
  directions: Record<string, number>
  items: { article_id: string; title: string; added: string[]; direction: string }[]
  rematch?: { matches: number }
  problem?: string
}

/**
 * @param date  'today' = นับเฉพาะข่าวของวันล่าสุดที่มีในฐาน (ชุดเดียวกับที่ปุ่มสั่งอ่าน)
 * @param live  true ระหว่างที่ AI กำลังอ่าน — ถามซ้ำทุก 3 วิให้ตัวเลขขยับระหว่างรอ
 *              งานนี้ใช้เวลา 15-25 วินาทีต่อชิ้น ถ้าไม่ขยับเลยคนกดจะคิดว่าค้าง
 */
export const useAiHealth = (date?: string, live = false) =>
  useQuery({
    queryKey: ['aihealth', date],
    queryFn: () => get<AiHealth>('/ai/health', { date }),
    refetchInterval: live ? 3_000 : false,
    ...(live ? {} : stale),
  })

/* ---------------------------------------------------------------- ปันผล */

export type Dividend = {
  entity: string
  price: number
  rating: string
  dps: number
  /** % ของงวดนี้งวดเดียว — ใช้คิดเงินบาทที่ลูกค้าจะได้รอบนี้ */
  yield_interim: number
  xd_date: string
  pay_date: string
  period: string
  /** % ทั้งปี (69F) — ใช้ดูสไตล์พอร์ตและคัดกรอง ไม่ใช่เงินรอบนี้ */
  yield_forecast: number
  remark: 'Official' | 'Estimated'
  customers: number
  held_value: number
  dividend: number
}

export type DividendTable = {
  month: string | null
  as_of: string | null
  months: string[]
  total_dividend: number
  held_count: number
  items: Dividend[]
}

export type DividendIngest = {
  report_month: string
  title: string
  as_of: string | null
  stored: number
  rejected: number
  rejected_rows: { entity: string; why: string }[]
  at: string
}

export const useDividends = (month?: string, rm?: string) =>
  useQuery({
    queryKey: ['dividends', month, rm],
    queryFn: () => get<DividendTable>('/dividends', { month, rm }),
    ...stale,
  })

export type StyleKey = 'income' | 'div_trader' | 'growth' | 'speculate' | 'unknown'

export type PortfolioStyle = {
  customer_key: string
  rm_id: string
  persona: string
  trade_frequency: string
  portfolio_value: number
  covered: number
  total: number
  /** ปันผลทั้งปีที่พอร์ตนี้ควรได้ (คิดจาก 69F) */
  annual: number
  /** ปันผลงวดนี้งวดเดียว — ตัวเลขที่ RM เอาไปบอกลูกค้าได้เลย */
  interim: number
  coverage: number
  yield_portfolio: number | null
  style: StyleKey
  median_yield: number
  month: string
}

export type StyleSummary = {
  month: string | null
  median_yield: number
  coverage_min: number
  labels: Record<StyleKey, { th: string; en: string }>
  counts: Partial<Record<StyleKey, number>>
  customers: number
  measurable: number
  total_interim: number
  top: PortfolioStyle[]
}

/* ----------------------------------------------------------- อีเมลถึง RM */

export type MailConfig = {
  recipients: string[]
  sent_at: string | null
  /** เครื่องนี้สั่ง Outlook ได้ไหม (Windows + PowerShell) */
  available: boolean
  /** Outlook เปิดค้างอยู่แล้วหรือยัง — ยังไม่เปิดก็ส่งได้ ระบบเปิดให้เอง แค่ช้ากว่า */
  running: boolean
  version?: string | null
  /** เหตุผลที่ยังส่งไม่ได้เลย — null คือพร้อม */
  blocked: string | null
  rms: string[]
}

export type MailFile = {
  rm_id: string
  /** ไฟล์อ่าน (.html) หน้าตาเหมือนหน้าจอในเว็บ — ทีมละหนึ่งไฟล์ */
  report: string
  rows: number
  entities: number
  value_total: number
}

/** อีเมลฉบับเดียวถึงทั้งทีม ของละเอียดอยู่ในไฟล์แนบแยกรายทีม */
export type MailPreview = {
  date: string
  subject: string
  html: string
  recipients: string[]
  files: MailFile[]
}

export type MailSendResult = {
  at: string
  date: string
  to: string[]
  subject: string
  files: string[]
}

export const useMailConfig = () =>
  useQuery({ queryKey: ['mailcfg'], queryFn: () => get<MailConfig>('/mail/config'), ...stale })

export const useMailPreview = (date?: string) =>
  useQuery({
    queryKey: ['mailpreview', date],
    queryFn: () => get<MailPreview>('/mail/preview', { date }),
    ...stale,
  })

/** ลิงก์เปิดไฟล์แนบมาดูก่อน — ไฟล์เดียวกับที่จะถูกแนบไปจริง */
export const mailFileUrl = (rm: string, date?: string) =>
  `${BASE}/mail/file?rm=${encodeURIComponent(rm)}${date ? `&date=${date}` : ''}`

export function useMailActions() {
  const qc = useQueryClient()
  return {
    save: useMutation({
      mutationFn: (v: { recipients: string[] }) => put<MailConfig>('/mail/config', v),
      onSuccess: () => qc.invalidateQueries({ queryKey: ['mailcfg'] }),
    }),
    send: useMutation({
      mutationFn: (v: { to: string[]; rm_ids: string[]; date?: string }) =>
        post<MailSendResult>('/mail/send', v),
      onSuccess: () => qc.invalidateQueries({ queryKey: ['health'] }),
    }),
  }
}

export const useDividendStyles = (rm?: string) =>
  useQuery({
    queryKey: ['divstyles', rm],
    queryFn: () => get<StyleSummary>('/dividends/styles', { rm }),
    ...stale,
  })

export function useActions() {
  const qc = useQueryClient()
  const done = () => qc.invalidateQueries()
  return {
    fetchNews: useMutation({ mutationFn: (pages: number) => post('/ingest/news', { pages }), onSuccess: done }),
    // อ่านด้วย Claude Code บนเครื่อง ช้าราว 15-25 วินาทีต่อชิ้น จึงส่งจำนวนไปทีละล็อต
    // date: 'today' ให้ backend หาข่าวของวันล่าสุดที่มีจริงเอง แทนการอ่านย้อนหลังตามลำดับเก่าสุดก่อน
    aiRead: useMutation({
      mutationFn: (arg: number | { limit: number; date?: string }) => {
        const { limit, date } = typeof arg === 'number' ? { limit: arg, date: undefined } : arg
        return post<AiResult>('/ai/enrich', { limit, date })
      },
      onSuccess: done,
    }),
    // Data Book ออกเดือนละครั้ง ปุ่มนี้จึงกดเดือนละครั้งพอ — ระบบไปหา PDF เดือนล่าสุดเอง
    fetchDividends: useMutation({ mutationFn: () => post<DividendIngest>('/ingest/dividends'), onSuccess: done }),
    reingest: useMutation({ mutationFn: () => post('/ingest/customers'), onSuccess: done }),
    rematch: useMutation({ mutationFn: () => post('/match', {}), onSuccess: done }),
  }
}
