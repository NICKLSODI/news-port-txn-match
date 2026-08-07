import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { CheckNote, FileReport, UploadReport, UploadResult } from '../lib/api'
import { postFiles } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { num } from '../lib/format'
import { Button, Code, Head, Row, Scroll, Spinner, Stat, Td, Th } from '../components/ui'

const MAX_MB = 80

/* --------------------------------------------------------------------------
   สัญญาข้อมูล STEP1 — คอลัมน์ที่ไฟล์ต้องมี (ชื่อคอลัมน์คือชื่อจริงในไฟล์ต้นทาง)
-------------------------------------------------------------------------- */
type Spec = { id: string; col: string; must: boolean; th: string; en: string }

const SPEC_PORT: Spec[] = [
  { id: 'H-01', col: 'customer_key', must: true, th: 'รหัสลูกค้าที่ปิดบังแล้ว ต้องคงที่ทุกรอบ', en: 'masked customer key, stable across rounds' },
  { id: 'H-02', col: 'account_key', must: true, th: 'รหัสบัญชีที่ปิดบังแล้ว', en: 'masked account key' },
  { id: 'H-03', col: 'm_id', must: true, th: 'รหัส RM (ห้ามเป็นชื่อคน)', en: 'RM code (never a name)' },
  { id: 'H-04', col: 'product_code', must: true, th: 'รหัสสินทรัพย์ — ตัวเชื่อมกับข่าว', en: 'instrument code — the link to news' },
  { id: 'H-06', col: 'product_txt_key', must: true, th: 'ชนิดสินทรัพย์ดิบ ระบบแปลงเป็น asset_class เอง', en: 'raw asset key, mapped to asset_class' },
  { id: 'H-07', col: 'aum', must: true, th: 'มูลค่าที่ถือ (บาท) — ค่าว่างได้ แต่คอลัมน์ต้องมี', en: 'holding value in THB — blanks allowed, column required' },
  { id: 'H-08', col: 'thb_unrealized_avg', must: true, th: 'กำไร/ขาดทุนที่ยังไม่รับรู้ (บาท)', en: 'unrealized P/L in THB' },
  { id: 'H-09', col: 'record_date', must: true, th: 'วันที่ของ snapshot รูปแบบ YYYY-MM-DD', en: 'snapshot date, YYYY-MM-DD' },
]

const SPEC_TXN: Spec[] = [
  { id: 'T-01', col: 'customer_key', must: true, th: 'ต้องเป็นรหัสชุดเดียวกับไฟล์พอร์ต', en: 'must come from the same map as the portfolio file' },
  { id: 'T-02', col: 'account_key', must: true, th: 'รหัสบัญชีที่ปิดบังแล้ว', en: 'masked account key' },
  { id: 'T-03', col: 'm_id', must: true, th: 'รหัส RM', en: 'RM code' },
  { id: 'T-04', col: 'product_code', must: true, th: 'ใช้หา watchlist และสถานะ TFEX', en: 'used for watchlist and TFEX position' },
  { id: 'T-06', col: 'product_txt_key', must: true, th: 'ชนิดสินทรัพย์ดิบ', en: 'raw asset key' },
  { id: 'T-07', col: 'record_date', must: true, th: 'วันที่ทำรายการ YYYY-MM-DD', en: 'trade date, YYYY-MM-DD' },
  { id: 'T-08', col: 'txn_type', must: true, th: 'ประเภทรายการดิบ เช่น Buy / Sell / SUB', en: 'raw transaction type, e.g. Buy / Sell / SUB' },
  { id: 'T-09', col: 'confirm_unit', must: true, th: 'จำนวนหน่วย — ขาดแล้วคำนวณสถานะ TFEX ไม่ได้', en: 'units — TFEX position needs it' },
  { id: 'T-10', col: 'trading_value', must: true, th: 'มูลค่าที่เทรด (บาท)', en: 'traded value in THB' },
]

const PII_OUT = ['cardid', 'cust_name_th', 'account', 'marketing_name_th']

/* -------------------------------------------------------------------------- */

function fmtSize(b: number) {
  return b >= 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.round(b / 1024)} KB`
}

function Notes({ list, tone }: { list: CheckNote[]; tone: 'critical' | 'warning' }) {
  const { isTh } = useI18n()
  if (!list.length) return null
  return (
    <ul className="mt-3 space-y-1.5">
      {list.map((n, i) => (
        <li key={`${n.code}-${i}`} className="flex gap-2 text-small">
          <span aria-hidden className="mt-[7px] size-1.5 shrink-0 rounded-full" style={{ background: `var(--${tone})` }} />
          <span className="min-w-0">
            <span style={{ color: `var(--${tone})` }}>{isTh ? n.th : n.en}</span>
            {n.detail && 'samples' in n.detail && Array.isArray(n.detail.samples) ? (
              <span className="ml-1.5 text-ink-3">
                {(n.detail.samples as string[]).slice(0, 8).map((s, j) => (
                  <span key={j} className="mr-1">
                    <Code>{s || '—'}</Code>
                  </span>
                ))}
              </span>
            ) : null}
          </span>
        </li>
      ))}
    </ul>
  )
}

/** ช่องวางไฟล์หนึ่งช่อง — บังคับ .xlsx และบอกทันทีว่าเลือกอะไรไป */
function Slot({
  title,
  note,
  file,
  onPick,
  disabled,
}: {
  title: string
  note: string
  file: File | null
  onPick: (f: File | null) => void
  disabled?: boolean
}) {
  const { isTh } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [bad, setBad] = useState<string | null>(null)

  const take = (f?: File | null) => {
    if (!f) return
    if (!/\.xlsx?$|\.xlsm$/i.test(f.name)) {
      setBad(isTh ? 'รับเฉพาะไฟล์ .xlsx' : 'Only .xlsx is accepted')
      return
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setBad(isTh ? `ไฟล์ใหญ่เกิน ${MAX_MB} MB` : `Larger than ${MAX_MB} MB`)
      return
    }
    setBad(null)
    onPick(f)
  }

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 border-b border-rule pb-1.5">
        <h3 className="text-body font-semibold text-ink">{title}</h3>
        {file ? (
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              onPick(null)
              if (input.current) input.current.value = ''
            }}
            className="tap text-micro text-ink-3 hover:text-ink disabled:opacity-40"
          >
            {isTh ? 'เอาออก' : 'Remove'}
          </button>
        ) : null}
      </div>
      <p className="mt-1.5 text-small text-ink-2">{note}</p>

      {/* deslop-ignore-next-line 28 — โซนวางไฟล์ต้องมีขอบให้เห็นว่าลากมาวางได้ */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          if (!disabled) take(e.dataTransfer.files?.[0])
        }}
        className={`mt-3 rounded-out border border-dashed px-4 py-6 text-center ${
          over ? 'border-rule-strong bg-accent-wash' : 'border-rule-strong bg-wash'
        }`}
      >
        {file ? (
          <>
            <p className="truncate text-body font-medium text-ink" title={file.name}>
              {file.name}
            </p>
            <p className="tnum mt-0.5 text-small text-ink-2">{fmtSize(file.size)}</p>
          </>
        ) : (
          <p className="text-small text-ink-2">
            {isTh ? 'ลากไฟล์มาวาง หรือ' : 'Drop the file here, or'}
          </p>
        )}
        <p className="mt-2.5">
          <Button disabled={disabled} onClick={() => input.current?.click()}>
            {file ? (isTh ? 'เปลี่ยนไฟล์' : 'Replace') : isTh ? 'เลือกไฟล์' : 'Choose a file'}
          </Button>
        </p>
        <input
          ref={input}
          type="file"
          accept=".xlsx,.xlsm"
          className="hidden"
          onChange={(e) => take(e.target.files?.[0])}
        />
      </div>
      {bad ? (
        <p className="mt-2 text-small" style={{ color: 'var(--critical)' }}>
          {bad}
        </p>
      ) : null}
    </div>
  )
}

function FileResult({ r }: { r: FileReport }) {
  const { isTh } = useI18n()
  const bad = r.errors.length > 0
  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-rule pb-1.5">
        <h3 className="min-w-0 truncate text-body font-semibold text-ink" title={r.filename}>
          {r.filename}
        </h3>
        <span className="text-small font-medium" style={{ color: `var(--${bad ? 'critical' : 'good'})` }}>
          {bad
            ? isTh
              ? `ไม่ผ่าน ${r.errors.length} ข้อ`
              : `${r.errors.length} blocking issue(s)`
            : isTh
              ? 'ผ่าน'
              : 'Passed'}
        </span>
      </div>
      <dl className="mt-2">
        <Row k={isTh ? 'แถวข้อมูล' : 'Rows'} v={num(r.rows)} />
        <Row k={isTh ? 'ชีตที่อ่าน' : 'Sheet read'} v={r.sheet ?? '—'} />
        <Row k={isTh ? 'ลูกค้าในไฟล์' : 'Customers in file'} v={num(r.stats.customers)} />
        <Row k={isTh ? 'RM' : 'RMs'} v={num(r.stats.rms)} />
        <Row
          k={isTh ? 'ช่วงวันที่' : 'Date range'}
          v={r.stats.date_min ? `${r.stats.date_min} → ${r.stats.date_max}` : '—'}
        />
      </dl>
      <Notes list={r.errors} tone="critical" />
      <Notes list={r.warnings} tone="warning" />
    </section>
  )
}

/* --------------------------------------------------------------------------
   ขั้นตอนการปิดบังข้อมูล — เป็นการ์ดเรียงซ้ายไปขวา ดูรูปแล้วรู้ว่าต้องทำอะไร
   ภาพวาดคือของจริงในขั้นนั้น (ไฟล์ · หน้าต่าง Copilot · ไฟล์ที่แนบ · ช่องพิมพ์)
   ไม่ใช่ไอคอนประดับ
-------------------------------------------------------------------------- */

const ink2 = { stroke: 'var(--ink-2)' }
const ink3 = { stroke: 'var(--ink-3)' }
const acc = { stroke: 'var(--accent)' }

function ArtDownload() {
  return (
    <svg viewBox="0 0 56 48" className="h-[70px]" fill="none" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M16 4h14l8 8v22a4 4 0 0 1-4 4H20a4 4 0 0 1-4-4V8a4 4 0 0 1 4-4z" style={ink2} />
      <path d="M30 4v8h8" style={ink3} />
      <path d="M22 16h9M22 21h6" style={ink3} />
      <path d="M27 26v12M27 38l-4.5-4.5M27 38l4.5-4.5" style={acc} />
    </svg>
  )
}

function ArtCopilot() {
  return (
    <svg viewBox="0 0 56 48" className="h-[70px]" fill="none" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="6" y="8" width="44" height="32" rx="3" style={ink2} />
      <path d="M6 16h44" style={ink3} />
      <circle cx="11" cy="12" r="1.1" style={ink3} />
      <circle cx="15.5" cy="12" r="1.1" style={ink3} />
      <path d="M13 24h14M13 30h9" style={ink3} />
      <path d="M38 21v12M32 27h12M35.5 23.5l5 7M40.5 23.5l-5 7" style={acc} />
    </svg>
  )
}

function Chip({ label, on }: { label: string; on?: boolean }) {
  return (
    <span
      className="rounded-in border px-1.5 py-px text-micro font-medium whitespace-nowrap"
      style={
        on
          ? { borderColor: 'var(--accent)', color: 'var(--accent)' }
          : { borderColor: 'var(--rule-strong)', color: 'var(--ink-2)' }
      }
    >
      {label}
    </span>
  )
}

function ArtAttach() {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 24 24" className="size-9 shrink-0" fill="none" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M18 7.5 9.2 16.3a3.1 3.1 0 0 0 4.4 4.4l8.1-8.1a5.4 5.4 0 0 0-7.6-7.6l-8.4 8.4a7.7 7.7 0 0 0 10.9 10.9" style={ink2} />
      </svg>
      <div className="flex flex-col items-start gap-1.5">
        <Chip label="คู่มือ .md" on />
        <Chip label="Portfolio.xlsx" />
        <Chip label="TXN.xlsx" />
      </div>
    </div>
  )
}

/** บับเบิลแชทสีเน้น — อ่านเป็นข้อความที่พิมพ์ส่งไป ไม่ใช่ช่องกรอก */
function ArtPrompt() {
  return (
    <div className="flex w-full flex-col items-center px-2.5">
      <div className="relative">
        <span
          className="block rounded-out px-3 py-1.5 text-body font-semibold"
          style={{ background: 'var(--accent)', color: 'var(--accent-ink)' }}
        >
          ทำตาม .md
        </span>
        <span
          aria-hidden
          className="absolute -bottom-1 left-4 size-2.5 rotate-45"
          style={{ background: 'var(--accent)' }}
        />
      </div>
      <svg viewBox="0 0 24 16" className="mt-2.5 h-3.5" fill="none" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M12 1v13M12 14l-5-5M12 14l5-5" style={acc} />
      </svg>
      <div className="mt-1.5 flex flex-wrap justify-center gap-1">
        <Chip label="Portfolio_MASKED" />
        <Chip label="TXN_MASKED" />
      </div>
    </div>
  )
}

const BTN =
  'tap inline-block rounded-out border border-rule bg-surface px-3 py-1.5 text-small font-medium text-ink-2 hover:bg-wash hover:text-ink'

function Stepper() {
  const { isTh } = useI18n()
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText('ทำตาม .md')
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  const steps = [
    {
      art: <ArtDownload />,
      title: isTh ? 'โหลดคู่มือ' : 'Download the guide',
      body: isTh ? 'เก็บไฟล์ .md ไว้ในเครื่อง' : 'Keep the .md file on your machine',
      action: (
        <a href="/api/mask-guide" download className={BTN}>
          {isTh ? 'โหลดไฟล์คู่มือ (.md)' : 'Download the .md'}
        </a>
      ),
    },
    {
      art: <ArtCopilot />,
      title: isTh ? 'เปิด Copilot' : 'Open Copilot',
      body: isTh
        ? 'microsoft365.com ด้วย account บริษัท ห้ามใช้ account ส่วนตัว'
        : 'microsoft365.com with the company account — never a personal one',
    },
    {
      art: <ArtAttach />,
      title: isTh ? 'แนบสามไฟล์' : 'Attach three files',
      body: isTh
        ? 'คู่มือ .md + ไฟล์ Portfolio และ TXN ตัวจริง'
        : 'the .md guide plus the real Portfolio and TXN files',
    },
    {
      art: <ArtPrompt />,
      title: isTh ? 'พิมพ์ “ทำตาม .md”' : 'Type “ทำตาม .md”',
      body: isTh
        ? 'ได้ไฟล์ _MASKED สองไฟล์ เอากลับมาวางในช่องข้างล่าง'
        : 'you get two _MASKED files — drop them in the slots below',
      action: (
        <button type="button" onClick={copy} className={BTN}>
          {copied
            ? isTh
              ? 'คัดลอกแล้ว'
              : 'Copied'
            : isTh
              ? 'คัดลอกคำสั่ง'
              : 'Copy the prompt'}
        </button>
      ),
    },
  ]

  return (
    <ol className="mt-4 grid gap-3 border-t border-rule pt-5 sm:grid-cols-2 lg:grid-cols-4">
      {steps.map((s, i) => (
        // deslop-ignore-next-line 28 — การ์ดต่อการ์ดคือลำดับขั้นจริง ไม่ใช่กล่องประดับ
        <li key={i} className="relative rounded-out border border-rule bg-surface p-3.5">
          <div className="flex items-center gap-2">
            <span className="tnum inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-ink text-micro font-semibold text-paper">
              {i + 1}
            </span>
            <h3 className="text-body font-semibold text-ink">{s.title}</h3>
          </div>
          <div className="mt-3 flex h-32 items-center justify-center rounded-in bg-wash">{s.art}</div>
          <p className="mt-3 text-small text-ink-2 lg:min-h-10">{s.body}</p>
          {'action' in s && s.action ? <div className="mt-2.5">{s.action}</div> : null}
          {i < steps.length - 1 ? (
            <span
              aria-hidden
              className="absolute top-1/2 -right-[15px] z-1 hidden -translate-y-1/2 text-h2 leading-none text-ink-3 lg:block"
            >
              ›
            </span>
          ) : null}
        </li>
      ))}
    </ol>
  )
}

/* --------------------------------------------------------------------------
   กล่องกำลังทำงาน — ตรวจไฟล์ 12 MB ราวครึ่งนาที นำเข้า+จับคู่อีกราวครึ่งนาที
   ระหว่างนั้นหน้าจอต้องบอกว่ากำลังทำอะไรอยู่ ถึงขั้นไหน และผ่านไปกี่วินาที
-------------------------------------------------------------------------- */

const STEPS_TH = ['อัปโหลดไฟล์', 'ตรวจตามสัญญาข้อมูล', 'นำเข้าและคำนวณ persona', 'จับคู่ข่าวกับลูกค้า']
const STEPS_EN = ['Upload', 'Validate', 'Import and rebuild personas', 'Match news to customers']

function BusyDialog({
  phase,
  pct,
  seconds,
}: {
  phase: 'checking' | 'uploading' | 'working'
  pct: number
  seconds: number
}) {
  const { isTh } = useI18n()
  const labels = isTh ? STEPS_TH : STEPS_EN
  // ตรวจไฟล์ = อัปโหลด + ตรวจ (2 ขั้น) · นำเข้า = ครบ 4 ขั้น
  const total = phase === 'checking' ? 2 : 4
  const at = phase === 'uploading' || (phase === 'checking' && pct < 100) ? 0 : phase === 'checking' ? 1 : 2

  return (
    // deslop-ignore-next-line 28 — ต้องลอยทับและกันกดซ้ำระหว่างงานยังไม่จบ
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-busy>
      <div className="absolute inset-0 bg-black/30" />
      <div className="relative w-full max-w-sm rounded-out border border-rule bg-surface p-5 shadow-lg">
        <div className="flex items-center gap-3">
          <span style={{ color: 'var(--accent)' }}>
            <Spinner className="size-6" />
          </span>
          <div className="min-w-0">
            <h2 className="text-h2 font-semibold text-ink">
              {phase === 'checking'
                ? isTh
                  ? 'กำลังตรวจไฟล์'
                  : 'Checking the files'
                : phase === 'uploading'
                  ? isTh
                    ? 'กำลังอัปโหลด'
                    : 'Uploading'
                  : isTh
                    ? 'กำลังนำเข้าและจับคู่'
                    : 'Importing and matching'}
            </h2>
            <p className="tnum mt-0.5 text-small text-ink-3">
              {isTh ? `ผ่านไป ${seconds} วินาที` : `${seconds}s elapsed`}
              {phase === 'uploading' || (phase === 'checking' && pct < 100) ? ` · ${pct}%` : ''}
            </p>
          </div>
        </div>

        {/* แถบวัดได้ตอนอัปโหลด · แถบวิ่งตอนงานอยู่ฝั่งเซิร์ฟเวอร์ */}
        <div className="mt-4 h-1.5 overflow-hidden rounded-in bg-wash">
          {phase === 'working' || pct >= 100 ? (
            <div className="mp-sweep h-full w-1/3" style={{ background: 'var(--accent)' }} />
          ) : (
            <div className="h-full transition-[width]" style={{ width: `${pct}%`, background: 'var(--accent)' }} />
          )}
        </div>

        <ol className="mt-4 space-y-2">
          {labels.slice(0, total).map((s, i) => (
            <li key={s} className="flex items-center gap-2 text-small">
              {i < at ? (
                <svg viewBox="0 0 24 24" className="size-4 shrink-0" fill="none" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M5 13l4.5 4.5L19 7" style={{ stroke: 'var(--good)' }} />
                </svg>
              ) : i === at ? (
                <span className="shrink-0" style={{ color: 'var(--accent)' }}>
                  <Spinner />
                </span>
              ) : (
                <span aria-hidden className="size-4 shrink-0" />
              )}
              <span className={i <= at ? 'text-ink' : 'text-ink-3'}>{s}</span>
            </li>
          ))}
        </ol>

        <p className="mt-4 text-small text-ink-2">
          {isTh ? 'ห้ามปิดหน้านี้จนกว่าจะเสร็จ' : 'Keep this page open until it finishes'}
        </p>
      </div>
    </div>
  )
}

/* --------------------------------------------------------------------------
   แจ้งผลตอนงานจบ — นำเข้าใช้เวลาเป็นนาที คนกดมักสลับไปทำอย่างอื่น
   จบแล้วต้องรู้ทันทีว่าสำเร็จหรือไม่ ไม่ใช่ให้ไปเลื่อนหาเอง
-------------------------------------------------------------------------- */

function DoneDialog({
  result,
  error,
  onClose,
  onSeeDetail,
}: {
  result: UploadResult | null
  error: string | null
  onClose: () => void
  onSeeDetail: () => void
}) {
  const { isTh } = useI18n()
  const ok = !!result && !error

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const m = result?.matched
  const problems = result?.installed.problems ?? []

  return (
    // deslop-ignore-next-line 28 — กล่องแจ้งผลต้องลอยทับหน้าจอ ไม่งั้นคนพลาดผลลัพธ์
    <div
      className="fixed inset-0 z-40 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label={ok ? 'นำเข้าเรียบร้อย' : 'นำเข้าไม่สำเร็จ'}
    >
      <button type="button" aria-label="close" onClick={onClose} className="absolute inset-0 bg-black/30" />
      <div className="relative w-full max-w-md rounded-out border border-rule bg-surface p-5 shadow-lg">
        <div className="flex items-start gap-3">
          <span
            aria-hidden
            className="mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-full"
            style={{ background: ok ? 'var(--good)' : 'var(--critical)' }}
          >
            <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              {ok ? <path d="M5 13l4.5 4.5L19 7" /> : <path d="M7 7l10 10M17 7L7 17" />}
            </svg>
          </span>
          <div className="min-w-0">
            <h2 className="text-h2 font-semibold text-ink">
              {ok
                ? isTh
                  ? 'นำเข้าและจับคู่เรียบร้อย'
                  : 'Imported and matched'
                : isTh
                  ? 'นำเข้าไม่สำเร็จ'
                  : 'Import failed'}
            </h2>
            <p className="mt-1 text-small text-ink-2">
              {ok
                ? isTh
                  ? 'ข้อมูลลูกค้าชุดใหม่ใช้งานได้แล้ว ทุกหน้าคำนวณจากชุดนี้'
                  : 'The new customer set is live — every page now uses it'
                : (error ?? '')}
            </p>
          </div>
        </div>

        {ok && result ? (
          <>
            <dl className="mt-4 border-t border-rule">
              <Row k={isTh ? 'ลูกค้า' : 'Customers'} v={num(result.ingested.customers)} />
              <Row k={isTh ? 'แถวการถือครอง' : 'Holding rows'} v={num(result.ingested.holdings_rows)} />
              <Row k={isTh ? 'แถวรายการเทรด' : 'Transaction rows'} v={num(result.ingested.txn_rows)} />
              <Row
                k={isTh ? 'รายชื่อที่จับคู่ได้' : 'Matches'}
                v={m ? `${num(m.matches)} · ${num(m.articles_matched)} ${isTh ? 'ข่าว' : 'articles'}` : '—'}
              />
              <Row k={isTh ? 'ข้อมูล ณ วันที่' : 'Data as of'} v={result.ingested.data_as_of} />
            </dl>
            {problems.length ? (
              <p className="mt-3 text-small" style={{ color: 'var(--warning)' }}>
                {isTh
                  ? 'เก็บสำเนาไฟล์ลง data/ ไม่ได้ (มีโปรแกรมอื่นเปิดไฟล์ค้าง) — ข้อมูลในระบบถูกต้องแล้ว'
                  : 'Could not copy the files into data/ (another program holds them) — the data itself is correct'}
              </p>
            ) : null}
          </>
        ) : null}

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          {ok ? (
            <Button onClick={onSeeDetail}>{isTh ? 'ดูสรุปทั้งหมด' : 'See the full summary'}</Button>
          ) : null}
          <Button variant="primary" onClick={onClose}>
            {isTh ? 'ปิด' : 'Close'}
          </Button>
        </div>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

export default function Upload() {
  const { isTh } = useI18n()
  const qc = useQueryClient()
  const [port, setPort] = useState<File | null>(null)
  const [txn, setTxn] = useState<File | null>(null)
  const [report, setReport] = useState<UploadReport | null>(null)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [phase, setPhase] = useState<'idle' | 'checking' | 'uploading' | 'working'>('idle')
  const [pct, setPct] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [showDone, setShowDone] = useState(false)
  const resultRef = useRef<HTMLDivElement>(null)

  // งานนำเข้ากินเวลาเป็นนาที คนมักสลับแท็บไปทำอย่างอื่น — ติดผลไว้ที่ชื่อแท็บด้วย
  useEffect(() => {
    if (!showDone) return
    const base = document.title
    if (document.hidden) document.title = `${error ? '❌' : '✅'} ${isTh ? 'นำเข้าเสร็จแล้ว' : 'Import finished'} · ${base}`
    const restore = () => {
      if (!document.hidden) document.title = base
    }
    document.addEventListener('visibilitychange', restore)
    return () => {
      document.removeEventListener('visibilitychange', restore)
      document.title = base
    }
  }, [showDone, error, isTh])

  const busy = phase !== 'idle'
  const both = !!port && !!txn
  const passed = report?.ok === true

  // นับวินาทีระหว่างทำงาน — ตัวเลขที่ขยับคือหลักฐานว่ายังทำงานอยู่จริง
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!busy) {
      setSeconds(0)
      return
    }
    const t0 = Date.now()
    const id = window.setInterval(() => setSeconds(Math.round((Date.now() - t0) / 1000)), 1000)
    return () => window.clearInterval(id)
  }, [busy])

  const reset = (setter: (f: File | null) => void) => (f: File | null) => {
    setter(f)
    setReport(null)
    setResult(null)
    setError(null)
  }

  const check = async () => {
    if (!port || !txn) return
    setPhase('checking')
    setError(null)
    setResult(null)
    setPct(0)
    try {
      const r = await postFiles<UploadReport>('/upload/check', { portfolio: port, txn }, {
        onProgress: setPct,
      })
      setReport(r)
    } catch (e) {
      const err = e as Error & { report?: UploadReport }
      if (err.report) setReport(err.report)
      setError(err.message)
    } finally {
      setPhase('idle')
    }
  }

  const install = async () => {
    if (!port || !txn) return
    setPhase('uploading')
    setError(null)
    setShowDone(false)
    setPct(0)
    try {
      const r = await postFiles<UploadResult>(
        '/upload',
        { portfolio: port, txn },
        {
          match: true,
          onProgress: (p) => {
            setPct(p)
            if (p >= 100) setPhase('working')
          },
        },
      )
      setResult(r)
      setReport(r.report)
      qc.invalidateQueries()
      setShowDone(true)
    } catch (e) {
      const err = e as Error & { report?: UploadReport }
      if (err.report) setReport(err.report)
      setError(err.message)
      setShowDone(true)
    } finally {
      setPhase('idle')
    }
  }

  const phaseText =
    phase === 'checking'
      ? isTh
        ? `กำลังตรวจไฟล์… ${pct}%`
        : `Checking… ${pct}%`
      : phase === 'uploading'
        ? isTh
          ? `กำลังอัปโหลด… ${pct}%`
          : `Uploading… ${pct}%`
        : phase === 'working'
          ? isTh
            ? 'นำเข้าและจับคู่ใหม่ทั้งหมด — ใช้เวลาราวหนึ่งถึงสองนาที ห้ามปิดหน้านี้'
            : 'Importing and re-matching everything — one to two minutes, keep this page open'
          : null

  return (
    <div>
      <header>
        <h1 className="text-h1 font-semibold text-ink">
          {isTh ? 'อัปโหลดข้อมูลลูกค้า' : 'Upload customer data'}
        </h1>
        <p className="mt-1 max-w-[74ch] text-body text-ink-2">
          {isTh
            ? 'ต้องอัปโหลดสองไฟล์พร้อมกันเสมอ — พอร์ตการถือครองกับรายการเทรด และต้องปิดบังข้อมูลส่วนบุคคลมาก่อน ระบบตรวจให้ทุกครั้ง ไม่ผ่านคือไม่นำเข้า'
            : 'Both files are required together — holdings and transactions — and both must already be masked. Every upload is checked; if it fails, nothing is imported.'}
        </p>
      </header>

      {/* ---------------- ปิดบังข้อมูลก่อน ---------------- */}
      <section className="mt-9">
        <Head
          note={
            isTh
              ? 'ไฟล์ดิบที่มีชื่อ เลขบัตร เลขบัญชี เอาเข้าระบบไม่ได้ ทำสี่ขั้นนี้ก่อน'
              : 'Raw files with names, ID or account numbers cannot enter the system. Do these four steps first.'
          }
        >
          {isTh ? 'ยังไม่ได้ปิดบังข้อมูล? เริ่มที่นี่' : 'Not masked yet? Start here'}
        </Head>
        <Stepper />
        <p className="mt-4 text-small text-ink-3">
          {isTh
            ? 'ไฟล์ต้นฉบับและตารางแปลงกลับ เก็บไว้ที่ตัวเอง ห้ามส่งต่อ'
            : 'Keep the raw files and the re-identification map to yourself'}
        </p>
      </section>

      {/* ---------------- สองช่อง ---------------- */}
      <div className="mt-9 grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <Slot
          title={isTh ? 'ไฟล์ที่ 1 · พอร์ตการถือครอง' : 'File 1 · Holdings'}
          note={
            isTh
              ? 'Excel ชีตแรก หนึ่งแถวคือสินทรัพย์หนึ่งชิ้นที่ลูกค้าถือ ณ วัน snapshot (STEP1 HOLDINGS)'
              : 'Excel, first sheet. One row per instrument held at the snapshot date (STEP1 HOLDINGS).'
          }
          file={port}
          onPick={reset(setPort)}
          disabled={busy}
        />
        <Slot
          title={isTh ? 'ไฟล์ที่ 2 · รายการเทรด (ปิดบังแล้ว)' : 'File 2 · Transactions (masked)'}
          note={
            isTh
              ? 'Excel ชีตแรก หนึ่งแถวคือหนึ่งรายการเทรด ต้องใช้ตารางแปลงรหัสชุดเดียวกับไฟล์ที่ 1 (STEP1 TRANSACTIONS)'
              : 'Excel, first sheet. One row per trade, masked with the same map as file 1 (STEP1 TRANSACTIONS).'
          }
          file={txn}
          onPick={reset(setTxn)}
          disabled={busy}
        />
      </div>

      {/* ---------------- ปุ่ม ---------------- */}
      <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-rule pt-5">
        <Button disabled={!both || busy} onClick={check}>
          {phase === 'checking' ? (
            <span className="inline-flex items-center gap-1.5">
              <Spinner />
              {isTh ? 'กำลังตรวจ…' : 'Checking…'}
            </span>
          ) : isTh ? (
            'ตรวจไฟล์ก่อน'
          ) : (
            'Check the files'
          )}
        </Button>
        <Button
          variant="primary"
          disabled={!both || busy || !passed}
          title={
            passed
              ? undefined
              : isTh
                ? 'ต้องตรวจไฟล์ให้ผ่านก่อน'
                : 'The files must pass the check first'
          }
          onClick={install}
        >
          {phase === 'uploading' || phase === 'working' ? (
            <span className="inline-flex items-center gap-1.5">
              <Spinner />
              {isTh ? 'กำลังทำงาน…' : 'Working…'}
            </span>
          ) : isTh ? (
            'นำเข้าและคำนวณใหม่'
          ) : (
            'Import and recalculate'
          )}
        </Button>
        {!both ? (
          <span className="text-small text-ink-3">
            {isTh ? 'ยังขาดไฟล์ — ต้องมีทั้งสองไฟล์' : 'Both files are required'}
          </span>
        ) : null}
        {phaseText ? <span className="text-small text-ink-2">{phaseText}</span> : null}
      </div>

      {error ? (
        <p className="mt-4 text-body" style={{ color: 'var(--critical)' }}>
          {error}
        </p>
      ) : null}

      {/* ---------------- ผลการตรวจ ---------------- */}
      {report ? (
        <div className="mt-10">
          <Head
            note={
              report.ok
                ? isTh
                  ? 'ไฟล์ผ่านสัญญาข้อมูล กดนำเข้าได้'
                  : 'Both files satisfy the data contract — ready to import'
                : isTh
                  ? 'แก้ตามรายการด้านล่างแล้วอัปโหลดใหม่ ข้อมูลในระบบยังไม่ถูกแตะต้อง'
                  : 'Fix the items below and upload again — nothing in the system has changed'
            }
          >
            {isTh ? 'ผลการตรวจ' : 'Check result'}
          </Head>
          <div className="grid gap-x-10 gap-y-8 border-t border-rule pt-5 lg:grid-cols-2">
            <FileResult r={report.portfolio} />
            <FileResult r={report.txn} />
          </div>

          <section className="mt-8 border-t border-rule pt-5">
            <h3 className="text-body font-semibold text-ink">
              {isTh ? 'ความสอดคล้องระหว่างสองไฟล์' : 'Consistency between the two files'}
            </h3>
            <div className="mt-2 flex flex-wrap gap-x-10 gap-y-4">
              <Stat
                label={isTh ? 'ลูกค้าที่อยู่ทั้งสองไฟล์' : 'In both files'}
                value={num(report.cross.stats.customers_both)}
              />
              <Stat
                label={isTh ? 'มีแต่ในไฟล์พอร์ต' : 'Portfolio only'}
                value={num(report.cross.stats.only_portfolio)}
              />
              <Stat
                label={isTh ? 'มีแต่ในไฟล์เทรด' : 'Transactions only'}
                value={num(report.cross.stats.only_txn)}
              />
              {report.cross.stats.date_gap_days !== undefined ? (
                <Stat
                  label={isTh ? 'วันข้อมูลห่างกัน (วัน)' : 'Date gap (days)'}
                  value={num(report.cross.stats.date_gap_days)}
                />
              ) : null}
            </div>
            <Notes list={report.cross.errors} tone="critical" />
            <Notes list={report.cross.warnings} tone="warning" />
          </section>
        </div>
      ) : null}

      {/* ---------------- ผลการนำเข้า ---------------- */}
      {result ? (
        <div ref={resultRef} className="mt-10 border-t-2 border-ink pt-5">
          <Head
            note={
              isTh
                ? `ไฟล์ชุดก่อนถูกเก็บไว้ที่ data/archive ${result.installed.archived.length ? `(${result.installed.archived.join(', ')})` : ''}`
                : `The previous files were archived under data/archive ${result.installed.archived.length ? `(${result.installed.archived.join(', ')})` : ''}`
            }
          >
            {isTh ? 'นำเข้าเรียบร้อย' : 'Imported'}
          </Head>
          <div className="flex flex-wrap gap-x-12 gap-y-5 border-t border-rule pt-4">
            <Stat label={isTh ? 'ลูกค้า' : 'Customers'} value={num(result.ingested.customers)} />
            <Stat label={isTh ? 'แถวการถือครอง' : 'Holding rows'} value={num(result.ingested.holdings_rows)} />
            <Stat label={isTh ? 'แถวรายการเทรด' : 'Transaction rows'} value={num(result.ingested.txn_rows)} />
            <Stat
              label={isTh ? 'รายชื่อที่จับคู่ได้' : 'Matches'}
              value={num(result.matched?.matches)}
              sub={
                result.matched
                  ? `${num(result.matched.articles_matched)} ${isTh ? 'ข่าว' : 'articles'}`
                  : undefined
              }
            />
            <Stat label={isTh ? 'ข้อมูล ณ วันที่' : 'Data as of'} value={result.ingested.data_as_of} />
          </div>
          {result.installed.problems.length ? (
            <p className="mt-4 text-small" style={{ color: 'var(--warning)' }}>
              {isTh
                ? 'ข้อมูลนำเข้าและคำนวณเรียบร้อยแล้ว แต่เก็บสำเนาไฟล์ลง data/ ไม่ได้ — น่าจะมีโปรแกรมอื่น (Excel) เปิดไฟล์ค้างอยู่ ปิดไฟล์แล้วอัปโหลดซ้ำได้ ระบบยังใช้งานได้ปกติ: '
                : 'Imported and recalculated, but the files could not be copied into data/ — something (Excel) is holding them open. Close it and upload again; the system still works: '}
              {result.installed.problems.map((p) => `${p.file} (${p.step})`).join(' · ')}
            </p>
          ) : null}
          {Object.keys(result.ingested.skipped_no_customer_key_R1_3 ?? {}).length ? (
            <p className="mt-4 text-small text-ink-2">
              {isTh ? 'ข้ามแถวที่ไม่มี customer_key: ' : 'Rows skipped for a missing customer_key: '}
              {Object.entries(result.ingested.skipped_no_customer_key_R1_3)
                .map(([k, v]) => `${k} ${num(v)}`)
                .join(' · ')}
            </p>
          ) : null}
        </div>
      ) : null}

      {/* ---------------- ข้อกำหนด ---------------- */}
      <div className="mt-14 border-t-2 border-ink pt-6">
        <Head
          note={
            isTh
              ? 'อ่านก่อนเตรียมไฟล์ — ทุกข้อในนี้ระบบตรวจจริง ไม่ใช่คำแนะนำ'
              : 'Read before preparing the files — every rule here is enforced, not advisory'
          }
        >
          {isTh ? 'ข้อกำหนดของไฟล์' : 'File requirements'}
        </Head>

        <div className="mt-5 grid gap-x-10 gap-y-9 lg:grid-cols-2">
          {[
            { title: isTh ? 'ไฟล์ที่ 1 · พอร์ต (HOLDINGS)' : 'File 1 · Holdings', spec: SPEC_PORT },
            { title: isTh ? 'ไฟล์ที่ 2 · รายการเทรด (TRANSACTIONS)' : 'File 2 · Transactions', spec: SPEC_TXN },
          ].map((g) => (
            <section key={g.title} className="min-w-0">
              <h3 className="border-b-2 border-ink pb-1.5 text-body font-semibold text-ink">{g.title}</h3>
              <Scroll className="mt-2">
                <table className="w-full border-collapse">
                  <thead>
                    <tr>
                      <Th>{isTh ? 'ชื่อคอลัมน์' : 'Column'}</Th>
                      <Th>{isTh ? 'ใช้ทำอะไร' : 'What it is for'}</Th>
                      <Th right>ID</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.spec.map((s) => (
                      <tr key={s.id}>
                        <Td>
                          <Code>{s.col}</Code>
                        </Td>
                        <Td className="text-ink-2">{isTh ? s.th : s.en}</Td>
                        <Td right className="text-ink-3">
                          {s.id}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Scroll>
            </section>
          ))}
        </div>

        <div className="mt-11 grid gap-x-10 gap-y-9 lg:grid-cols-2">
          <section>
            <h3 className="border-b-2 border-ink pb-1.5 text-body font-semibold text-ink">
              {isTh ? 'ต้องปิดบังอะไร และปิดบังยังไง' : 'What to mask, and how'}
            </h3>
            <p className="mt-2.5 text-small text-ink-2">
              {isTh
                ? 'ลบคอลัมน์เหล่านี้ออกก่อนส่ง แล้วแทนด้วยรหัส — ระบบทั้งระบบทำงานบนรหัสได้ 100% ไม่ต้องรู้ตัวจริง'
                : 'Delete these columns and replace them with codes — the whole system runs on codes alone.'}
            </p>
            <ul className="mt-3 space-y-1.5">
              {PII_OUT.map((c) => (
                <li key={c} className="flex items-baseline gap-2 text-small">
                  <span aria-hidden className="text-ink-3">
                    ลบ
                  </span>
                  <Code>{c}</Code>
                </li>
              ))}
            </ul>
            <dl className="mt-5 border-t border-rule">
              <Row k="cardid (เลขบัตรประชาชน)" v="customer_key = CUST00001, CUST00002 …" />
              <Row k="account (เลขบัญชี)" v="account_key = ACCT00001 …" />
              <Row k="marketing_name_th (ชื่อ RM)" v="m_id = M001 …" />
              <Row k="cust_name_th (ชื่อลูกค้า)" v={isTh ? 'ลบทิ้ง ไม่ต้องแทน' : 'delete, no replacement'} />
            </dl>
            <p className="mt-4 text-small text-ink-2">
              {isTh ? 'ขั้นตอนละเอียดพร้อม prompt ทุกกล่องอยู่ในไฟล์คู่มือ · ' : 'Every prompt is in the guide · '}
              <a href="/api/mask-guide" download className="underline hover:text-ink">
                {isTh ? 'โหลดไฟล์คู่มือ' : 'download it'}
              </a>
            </p>
          </section>

          <section>
            <h3 className="border-b-2 border-ink pb-1.5 text-body font-semibold text-ink">
              {isTh ? 'ข้อจำกัดที่ระบบบังคับ' : 'Limits the system enforces'}
            </h3>
            <ul className="mt-2.5 space-y-2 text-small text-ink-2">
              {(isTh
                ? [
                    'ต้องอัปโหลดสองไฟล์พร้อมกัน ไฟล์เดียวไม่รับ',
                    'ไฟล์ .xlsx เท่านั้น อ่านชีตแรกของไฟล์ ไฟล์ละไม่เกิน 80 MB',
                    'ห้ามมีคอลัมน์ PII ที่ระบุไว้ และห้ามมีเลข 13 หลัก อีเมล หลงมาในช่องไหนก็ตาม',
                    'customer_key / account_key / m_id ต้องเป็นค่าคงที่ ไม่ใช่สูตร (=XLOOKUP ไม่ผ่าน)',
                    'ห้ามมีชีตตารางแปลงกลับ (customer_map / account_map / rm_map) ติดมาในไฟล์',
                    'customer_key ต้องเป็นรหัสชุดเดียวกันทั้งสองไฟล์ ไม่ตรงกันเลย = ไม่ผ่าน (R1.3)',
                    'm_id ต้องเป็นรหัส ถ้ายังเป็นชื่อคนไทย = ไม่ผ่าน (R1.9)',
                    'วันที่ต้องเป็น YYYY-MM-DD ไม่มีเวลาและ timezone',
                    'มูลค่าทุกช่องเป็นสกุลบาทแล้ว (R1.8) — ระบบไม่แปลงค่าเงินให้',
                    'แถวที่ไม่มี product_code ถือเป็นยอดเงินคงเหลือ ระบบข้ามให้ (R1.6)',
                    'แถวที่ไม่มี customer_key ถูกข้ามทั้งแถว เพราะระบุเจ้าของไม่ได้ (R1.3)',
                    'ค่า enum ที่ไม่รู้จักไม่ทำให้ไฟล์ตก แต่จะถูกจัดเข้า OTHER และขึ้นในหน้าตรวจสอบข้อมูล (R1.5)',
                  ]
                : [
                    'Both files must be uploaded together — one file alone is rejected',
                    '.xlsx only, first sheet is read, 80 MB per file',
                    'No listed PII column, and no 13-digit ID or email value anywhere',
                    'customer_key / account_key / m_id must be values, not formulas (=XLOOKUP fails)',
                    'No re-identification map sheets (customer_map / account_map / rm_map) inside the file',
                    'customer_key must come from the same map in both files (R1.3)',
                    'm_id must be a code — Thai names fail (R1.9)',
                    'Dates must be YYYY-MM-DD, no time, no timezone',
                    'All values are already in THB (R1.8) — no currency conversion is done',
                    'Rows without product_code are cash balances and are skipped (R1.6)',
                    'Rows without customer_key are skipped — no owner to attribute them to (R1.3)',
                    'Unknown enum values do not fail the file — filed under OTHER and reported (R1.5)',
                  ]
              ).map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span aria-hidden className="mt-[7px] size-1.5 shrink-0 rounded-full bg-rule-strong" />
                  <span>{s}</span>
                </li>
              ))}
            </ul>
            <p className="mt-5 text-small text-ink-2">
              {isTh
                ? 'นำเข้าแล้วระบบจะแทนที่ข้อมูลลูกค้าทั้งชุด (ไฟล์ล่าสุดคือความจริง R1.7) ไฟล์ชุดก่อนสำเนาไว้ที่ data/archive แล้วคำนวณ feature, persona และจับคู่ใหม่ทุกบทความ'
                : 'Importing replaces the whole customer set (the latest file is the truth, R1.7). The previous files are archived under data/archive, then features, personas and every article match are recomputed.'}
            </p>
          </section>
        </div>
      </div>

      {phase === 'idle' ? null : <BusyDialog phase={phase} pct={pct} seconds={seconds} />}

      {showDone ? (
        <DoneDialog
          result={result}
          error={error}
          onClose={() => setShowDone(false)}
          onSeeDetail={() => {
            setShowDone(false)
            resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          }}
        />
      ) : null}
    </div>
  )
}
