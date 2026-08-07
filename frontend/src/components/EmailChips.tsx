import { useRef, useState } from 'react'
import type { ClipboardEvent, KeyboardEvent } from 'react'
import { useI18n } from '../lib/i18n'

const EMAIL = /^[\w.+-]+@[\w-]+\.[\w.-]+$/

/**
 * ช่องกรอกอีเมลหลายคนในช่องเดียว — Enter หรือ , หรือเว้นวรรค = ตัดเป็นชิป
 *
 * ที่อยู่ที่พิมพ์ผิดรูปยังรับเข้าเป็นชิปแต่ทำเครื่องหมายไว้ ไม่ใช่ปฏิเสธเงียบ ๆ
 * คนพิมพ์ต้องเห็นว่าตัวไหนมีปัญหา แทนที่จะสงสัยว่าทำไมกด Enter แล้วไม่มีอะไรเกิดขึ้น
 * แล้วให้ปุ่มส่งเป็นตัวกันจริงอีกชั้น — อีเมลผิดหนึ่งตัวไม่ควรทำให้ส่งไม่ได้ทั้งชุด
 * แต่ต้องเห็นก่อนกด ไม่ใช่ไปเด้งกลับมาตอนส่งไปแล้ว
 */
export default function EmailChips({
  value,
  onChange,
}: {
  value: string[]
  onChange: (v: string[]) => void
}) {
  const { isTh } = useI18n()
  const [draft, setDraft] = useState('')
  const box = useRef<HTMLInputElement>(null)

  const add = (raw: string) => {
    const parts = raw
      .split(/[,;\s]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (!parts.length) return
    const have = new Set(value.map((v) => v.toLowerCase()))
    const next = [...value]
    for (const p of parts) {
      if (!have.has(p.toLowerCase())) {
        have.add(p.toLowerCase())
        next.push(p)
      }
    }
    onChange(next)
    setDraft('')
  }

  const key = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',' || e.key === ';' || e.key === ' ') {
      if (draft.trim()) {
        e.preventDefault()
        add(draft)
      } else if (e.key === 'Enter') {
        e.preventDefault() // กัน Enter ตอนช่องว่างไปกด submit ของฟอร์มแทน
      }
      return
    }
    // ลบชิปตัวท้ายด้วย Backspace เฉพาะตอนช่องว่างจริง ๆ — พฤติกรรมเดียวกับช่อง To ของโปรแกรมเมล
    if (e.key === 'Backspace' && !draft && value.length) {
      onChange(value.slice(0, -1))
    }
  }

  const paste = (e: ClipboardEvent<HTMLInputElement>) => {
    const text = e.clipboardData.getData('text')
    if (/[,;\s]/.test(text)) {
      e.preventDefault()
      add(text)
    }
  }

  return (
    <div
      onClick={() => box.current?.focus()}
      className="flex min-h-[42px] flex-wrap items-center gap-1.5 rounded-out border border-rule bg-surface px-2 py-1.5 focus-within:border-rule-strong"
    >
      {value.map((e) => {
        const bad = !EMAIL.test(e)
        return (
          <span
            key={e}
            title={bad ? (isTh ? 'รูปแบบอีเมลไม่ถูกต้อง' : 'not a valid address') : undefined}
            className="inline-flex items-center gap-1.5 rounded-in bg-wash px-2 py-1 text-small"
            style={bad ? { color: 'var(--critical)', boxShadow: '0 0 0 1px var(--critical) inset' } : undefined}
          >
            {e}
            <button
              type="button"
              aria-label={`remove ${e}`}
              onClick={(ev) => {
                ev.stopPropagation()
                onChange(value.filter((x) => x !== e))
              }}
              className="tap text-ink-3 hover:text-ink"
            >
              ×
            </button>
          </span>
        )
      })}
      <input
        ref={box}
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={key}
        onPaste={paste}
        // เผลอคลิกออกทั้งที่ยังพิมพ์ค้างแล้วข้อความหายไปเงียบ ๆ คือทางที่คนตกหล่นผู้รับได้ง่ายสุด
        onBlur={() => draft.trim() && add(draft)}
        placeholder={
          value.length
            ? isTh
              ? 'เพิ่มอีกคน…'
              : 'add another…'
            : isTh
              ? 'พิมพ์อีเมลแล้วกด Enter'
              : 'type an address, press Enter'
        }
        className="min-w-[180px] flex-1 bg-transparent px-1 py-0.5 text-small text-ink outline-none"
      />
    </div>
  )
}
