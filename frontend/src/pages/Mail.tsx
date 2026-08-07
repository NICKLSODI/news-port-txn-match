import { useEffect, useState } from 'react'
import { mailFileUrl, useMailActions, useMailConfig, useMailPreview } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { num, thb } from '../lib/format'
import EmailChips from '../components/EmailChips'
import { Button, Empty, Head, Loading, Spinner } from '../components/ui'

const EMAIL = /^[\w.+-]+@[\w-]+\.[\w.-]+$/

/**
 * หน้าของหัวหน้าทีม — ส่ง "เรื่องที่ควรโทรวันนี้" ให้ทั้งทีมในฉบับเดียว
 *
 * ผู้รับกับข้อมูลที่แนบแยกกันคนละส่วน: ใครได้รับ (รายชื่ออีเมลอิสระ) กับ
 * แนบข้อมูลของทีมไหนบ้าง — ของจริงคนที่ควรได้รับไม่ได้มีแค่ RM เจ้าของบุ๊ก
 *
 * ตัวอย่างมาก่อนปุ่มส่งเสมอ เพราะอีเมลที่ออกไปแล้วเรียกคืนไม่ได้ คนกดต้องเห็น
 * ของจริงก่อนทุกครั้ง ไม่ใช่กดแล้วค่อยรู้ว่าส่งอะไรไป
 */
export default function MailPage() {
  const { isTh, lang } = useI18n()
  const { data: cfg } = useMailConfig()
  const { data: pv, isLoading } = useMailPreview()
  const a = useMailActions()

  const [to, setTo] = useState<string[]>([])
  const [books, setBooks] = useState<string[]>([])
  const [confirming, setConfirming] = useState(false)
  const [loaded, setLoaded] = useState(false)

  // ดึงค่าเดิมจากเซิร์ฟเวอร์ครั้งเดียว ไม่ทับสิ่งที่กำลังพิมพ์อยู่
  useEffect(() => {
    if (cfg && !loaded) {
      setTo(cfg.recipients)
      setLoaded(true)
    }
  }, [cfg, loaded])

  // ค่าเริ่มต้นคือแนบครบทุกทีม — เอาออกง่ายกว่าต้องไล่ติ๊กเข้าทีละอัน
  useEffect(() => {
    if (pv && !books.length) setBooks(pv.files.map((f) => f.rm_id))
  }, [pv]) // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) return <Loading rows={8} />
  if (!pv?.files.length) return <Empty />

  const bad = to.filter((e) => !EMAIL.test(e))
  const ready = to.length > 0 && !bad.length && books.length > 0
  const picked = pv.files.filter((f) => books.includes(f.rm_id))
  const result = a.send.data

  return (
    <div>
      <header>
        <h1 className="text-h1 font-semibold text-ink">
          {isTh ? 'ส่งอีเมลให้ RM' : 'Email the team'}
        </h1>
        <p className="mt-0.5 max-w-[76ch] text-small text-ink-2">
          {isTh
            ? 'ส่งฉบับเดียวถึงทุกคนในรายชื่อ แนบไฟล์ให้ทีมละหนึ่งไฟล์ — เปิดอ่านได้เลย และกดที่รหัสลูกค้าเพื่อดูหน้าของคนนั้นในไฟล์เดียวกัน ไม่ได้ส่งถึงลูกค้า'
            : 'One email to everyone listed, one file per team — readable as-is, and each customer code opens their own page inside it. Nothing goes to clients.'}
        </p>
      </header>

      {/* ---------------- 1. ผู้รับ ---------------- */}
      <section className="mt-8">
        <Head note={isTh ? 'พิมพ์แล้วกด Enter · วางหลายอีเมลพร้อมกันได้' : 'press Enter · pasting a list works'}>
          {isTh ? '1. ส่งถึงใคร' : '1. Recipients'}
        </Head>
        <div className="border-t border-rule pt-3">
          <EmailChips value={to} onChange={setTo} />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button disabled={a.save.isPending} onClick={() => a.save.mutate({ recipients: to })}>
              {isTh ? 'จำรายชื่อนี้ไว้' : 'Remember this list'}
            </Button>
            {a.save.isSuccess ? (
              <span className="text-micro text-ink-3">{isTh ? 'บันทึกแล้ว' : 'saved'}</span>
            ) : null}
            {bad.length ? (
              <span className="text-micro" style={{ color: 'var(--critical)' }}>
                {isTh ? `รูปแบบอีเมลไม่ถูกต้อง: ${bad.join(', ')}` : `invalid: ${bad.join(', ')}`}
              </span>
            ) : null}
          </div>
        </div>
      </section>

      {/* ---------------- 2. แนบข้อมูลของทีมไหน ---------------- */}
      <section className="mt-10">
        <Head
          note={
            isTh
              ? 'กดชื่อไฟล์เพื่อเปิดดูของจริงก่อนส่ง'
              : 'click a filename to inspect it before sending'
          }
        >
          {isTh ? '2. แนบข้อมูลของทีมไหน' : '2. Which books to attach'}
        </Head>
        <div className="border-t border-rule">
          {pv.files.map((f) => {
            const on = books.includes(f.rm_id)
            return (
              <div
                key={f.rm_id}
                className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-rule py-2.5"
              >
                <label className="flex min-w-[250px] items-center gap-2.5">
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() =>
                      setBooks((v) => (on ? v.filter((x) => x !== f.rm_id) : [...v, f.rm_id]))
                    }
                  />
                  <span className="tnum font-medium text-ink">{f.rm_id}</span>
                  <span className="text-micro text-ink-3">
                    {num(f.entities)} {isTh ? 'ตัว' : 'items'} · {num(f.rows)}{' '}
                    {isTh ? 'รายชื่อ' : 'rows'} · {thb(f.value_total, lang)}
                  </span>
                </label>
                <a
                  href={mailFileUrl(f.rm_id, pv.date)}
                  target="_blank"
                  rel="noreferrer"
                  className="tap text-micro text-ink-2 underline hover:text-ink"
                >
                  {f.report}
                </a>
              </div>
            )
          })}
        </div>
        <p className="mt-3 max-w-[80ch] text-micro text-ink-2">
          {isTh
            ? 'ทีมละหนึ่งไฟล์ เปิดอ่านได้เลย จัดเรียงแบบเดียวกับหน้าจอในเว็บ และกดที่รหัสลูกค้าเพื่อเปิดหน้าของคนนั้นได้ในไฟล์เดียวกัน'
            : 'One file per team — reads like the web view, and each customer code opens their own page inside it.'}
        </p>
        {/* ระบบไม่เก็บชื่อลูกค้าเลย คนรับต้องรู้ว่าไปขอตารางเทียบจากใคร ไม่ใช่คิดว่าไฟล์เสีย */}
        <p className="mt-2 max-w-[80ch] text-micro text-ink-2">
          {isTh
            ? 'ทั้งอีเมลและไฟล์มีข้อความกำกับไว้แล้วว่า รหัสลูกค้าเป็นรหัสอ้างอิงในระบบ ไม่ใช่ชื่อจริง และถ้าต้องการตารางเทียบว่ารหัสไหนคือใคร ให้ขอจากผู้ดูแลระบบที่กดส่ง'
            : 'Both the email and the files state that customer codes are system references, and that the mapping must be requested from whoever sent it.'}
        </p>
      </section>

      {/* ---------------- 3. ตัวอย่างจริง ---------------- */}
      <section className="mt-10">
        <Head>{isTh ? '3. ตัวอย่างที่จะส่งจริง' : '3. Exactly what will be sent'}</Head>
        <div className="border-t border-rule pt-4">
          <p className="text-small font-medium text-ink">{pv.subject}</p>
          <p className="mt-0.5 text-micro text-ink-3">
            {isTh ? 'ถึง ' : 'To '}
            {to.length ? to.join('; ') : isTh ? '(ยังไม่ได้ใส่ผู้รับ)' : '(no recipients yet)'}
            {isTh ? ` · แนบ ${picked.length} ไฟล์` : ` · ${picked.length} attachments`}
          </p>
          <div
            className="mt-4 max-h-[520px] overflow-y-auto rounded-out border border-rule bg-surface p-4"
            // เนื้อหามาจาก backend ของเราเอง ไม่ใช่ข้อความที่ผู้ใช้ภายนอกพิมพ์เข้ามา
            dangerouslySetInnerHTML={{ __html: pv.html }}
          />
        </div>
      </section>

      {/* ---------------- 4. ส่ง ---------------- */}
      <section className="mt-10">
        <Head>{isTh ? '4. ส่ง' : '4. Send'}</Head>
        <div className="border-t border-rule pt-4">
          {cfg?.blocked ? (
            <div className="rounded-out border border-rule bg-wash p-4">
              <p className="text-small font-medium text-ink">
                {isTh ? 'ส่งอัตโนมัติจากเครื่องนี้ไม่ได้' : 'This machine cannot send automatically'}
              </p>
              <p className="mt-1 text-small text-ink-2">{cfg.blocked}</p>
              <p className="mt-2 text-micro text-ink-3">
                {isTh
                  ? 'โหลดไฟล์จากลิงก์ด้านบนแล้วส่งเองจากโปรแกรมเมลแทนได้'
                  : 'Download the files above and send from your mail client instead.'}
              </p>
            </div>
          ) : confirming ? (
            /* ส่งแล้วเรียกคืนไม่ได้ — ต้องบอกชัดว่าถึงใครและแนบอะไร ไม่ใช่แค่ "แน่ใจไหม" */
            <div className="rounded-out border p-4" style={{ borderColor: 'var(--serious)' }}>
              <p className="text-small font-medium text-ink">
                {isTh
                  ? `กำลังจะส่งอีเมลจริง 1 ฉบับ ถึง ${to.length} คน พร้อมไฟล์แนบ ${picked.length} ไฟล์ ผ่าน Outlook ของคุณ ส่งแล้วเรียกคืนไม่ได้`
                  : `About to send 1 real email to ${to.length} people with ${picked.length} attachments, through your Outlook. This cannot be undone.`}
              </p>
              <ul className="mt-2 space-y-0.5">
                {to.map((e) => (
                  <li key={e} className="text-small text-ink-2">
                    {e}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-micro text-ink-3">
                {isTh ? 'แนบข้อมูลของ ' : 'Attaching books for '}
                {picked.map((f) => f.rm_id).join(', ')}
              </p>
              {!cfg?.running ? (
                <p className="mt-1 text-micro text-ink-3">
                  {isTh
                    ? 'Outlook ยังไม่ได้เปิด ระบบจะเปิดให้เองแล้วลองซ้ำอัตโนมัติจนพร้อม (ถ้ามี login/MFA ให้ทำที่หน้าต่าง Outlook)'
                    : 'Outlook is not running — it will be launched and retried automatically until ready.'}
                </p>
              ) : null}
              <div className="mt-4 flex flex-wrap gap-3">
                <Button
                  variant="primary"
                  disabled={a.send.isPending}
                  onClick={() => {
                    a.send.mutate({ to, rm_ids: books, date: pv.date })
                    setConfirming(false)
                  }}
                >
                  {isTh ? 'ยืนยันส่ง' : 'Confirm send'}
                </Button>
                <Button onClick={() => setConfirming(false)}>{isTh ? 'ยกเลิก' : 'Cancel'}</Button>
              </div>
            </div>
          ) : a.send.isPending ? (
            <p className="inline-flex items-center gap-2 text-small text-ink-2">
              <Spinner />
              {isTh
                ? 'กำลังส่งผ่าน Outlook… ถ้า Outlook ยังไม่เปิด ระบบจะเปิดและลองซ้ำให้เอง อาจใช้เวลาหลายนาที'
                : 'Sending through Outlook — launching and retrying automatically if needed.'}
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="primary" disabled={!ready} onClick={() => setConfirming(true)}>
                {isTh ? `ส่งถึง ${to.length} คน` : `Send to ${to.length}`}
              </Button>
              {!to.length ? (
                <span className="text-micro text-ink-3">
                  {isTh ? 'ใส่อีเมลผู้รับก่อน' : 'add a recipient first'}
                </span>
              ) : !books.length ? (
                <span className="text-micro" style={{ color: 'var(--serious)' }}>
                  {isTh ? 'ยังไม่ได้เลือกทีมที่จะแนบ' : 'no books selected'}
                </span>
              ) : null}
            </div>
          )}

          {a.send.error ? (
            <p className="mt-3 max-w-[80ch] text-small" style={{ color: 'var(--critical)' }}>
              {String(a.send.error)}
            </p>
          ) : null}

          {result ? (
            <div className="mt-4 border-t border-rule pt-3">
              <p className="text-small text-ink-2">
                {isTh ? 'ส่งแล้วถึง ' : 'Sent to '}
                <b className="text-ink">{result.to.join('; ')}</b>
                {isTh ? ` · แนบ ${result.files.length} ไฟล์` : ` · ${result.files.length} files`}
              </p>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  )
}
