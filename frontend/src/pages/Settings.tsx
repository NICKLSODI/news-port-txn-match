import { useHealth } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { num } from '../lib/format'
import { Head, Row, Stat } from '../components/ui'

/**
 * หน้าผู้ดูแล — บอกสถานะข้อมูลอย่างเดียว ไม่มีปุ่มสั่งงาน
 *
 * ปุ่มสั่งงานย้ายไปอยู่ที่เดียวกับงานที่มันทำหมดแล้ว: อัปโหลดอยู่หน้าอัปโหลด
 * ดึงข่าว/ให้ AI อ่านอยู่บนแถบด้านบน ส่งอีเมลอยู่หน้าส่งอีเมล
 * ปุ่มเดียวกันโผล่สองที่ทำให้ไม่รู้ว่าต้องกดอันไหน และกดซ้ำโดยไม่ตั้งใจ
 * เกณฑ์คะแนน (R6.14) เป็นค่าคงที่ของระบบ แก้ที่ tables.py ไม่ใช่ปุ่มบนหน้าจอ
 */
export default function Settings() {
  const { t, isTh } = useI18n()
  const { data: h } = useHealth()

  // ISO ที่มี T คั่นอ่านยากเวลาไล่ดูว่าอันไหนใหม่กว่า
  const stamp = (s?: string | null) => (s ? s.replace('T', ' ').slice(0, 16) : '—')

  /** ไฟล์ครอบคลุมกี่วัน — "6 เดือน" อ่านเข้าใจกว่า "191 วัน" */
  const span = (() => {
    if (!h?.txn_from || !h?.txn_to) return null
    const days =
      Math.round(
        (new Date(`${h.txn_to}T00:00:00`).getTime() -
          new Date(`${h.txn_from}T00:00:00`).getTime()) /
          86_400_000,
      ) + 1
    const months = days / 30.44
    const label =
      months >= 1.5
        ? isTh
          ? `${months.toFixed(1)} เดือน`
          : `${months.toFixed(1)} months`
        : isTh
          ? `${days} วัน`
          : `${days} days`
    return { days, label }
  })()

  return (
    <div>
      <header>
        <h1 className="text-h1 font-semibold text-ink">{t('nav.settings')}</h1>
        <p className="mt-1 max-w-[70ch] text-body text-ink-2">
          {isTh
            ? 'สถานะข้อมูลในระบบ — อัปโหลดไฟล์ที่หน้า "นำเข้าไฟล์" ดึงข่าวและให้ AI อ่านที่แถบด้านบน'
            : 'Data status only — upload files on the Upload page, fetch news from the top bar'}
        </p>
      </header>

      <div className="mt-8 flex flex-wrap gap-x-12 gap-y-5 border-y border-rule py-5">
        <Stat label={t('k.customers')} value={num(h?.customers)} />
        <Stat
          label={t('k.articles')}
          value={num(h?.articles)}
          sub={`${num(h?.news_api_total)} ${isTh ? 'ทั้งเว็บ' : 'on the site'}`}
        />
        <Stat label={t('k.matches')} value={num(h?.matches)} />
      </div>

      <div className="mt-10 grid max-w-[110ch] gap-x-12 gap-y-9 lg:grid-cols-2">
        <section>
          <Head
            note={
              isTh
                ? 'ช่วงเวลาที่ไฟล์ครอบคลุมจริง — คนละเรื่องกับวันที่นำเข้า'
                : 'the period the files actually cover — not the same as when they were imported'
            }
          >
            {isTh ? 'ไฟล์ที่อัปโหลดครอบคลุมช่วงไหน' : 'What the uploaded files cover'}
          </Head>
          <dl className="border-t border-rule">
            <Row
              k={isTh ? 'ธุรกรรมตั้งแต่' : 'transactions from'}
              v={h?.txn_from ?? '—'}
            />
            <Row k={isTh ? 'ถึง' : 'to'} v={h?.txn_to ?? '—'} />
            <Row
              k={isTh ? 'รวมระยะเวลา' : 'duration'}
              v={span ? `${span.label} (${num(span.days)} ${isTh ? 'วัน' : 'days'})` : '—'}
            />
            <Row
              k={isTh ? 'จำนวนธุรกรรม' : 'transaction rows'}
              v={num(h?.transactions)}
            />
            <Row
              k={isTh ? 'พอร์ต ณ วันที่' : 'holdings as of'}
              v={h?.holdings_as_of ?? '—'}
            />
            <Row k={isTh ? 'จำนวนรายการถือครอง' : 'holding rows'} v={num(h?.holdings)} />
          </dl>
        </section>

        <section>
          <Head
            note={
              isTh
                ? 'ไฟล์ล่าสุดคือความจริง (R1.7) — อัปโหลดชุดใหม่แล้วระบบคำนวณทุกอย่างใหม่ทั้งหมด'
                : 'The latest file is the truth (R1.7) — a new upload recomputes everything'
            }
          >
            {isTh ? 'ระบบทำอะไรไปล่าสุดเมื่อไหร่' : 'When things last ran'}
          </Head>
          <dl className="border-t border-rule">
            <Row k={t('msg.dataLag')} v={h?.customer_data_as_of ?? '—'} />
            <Row k={isTh ? 'นำเข้าไฟล์ลูกค้าเมื่อ' : 'customers ingested at'} v={stamp(h?.customers_ingested_at)} />
            <Row k={isTh ? 'ดึงข่าวล่าสุดเมื่อ' : 'news fetched at'} v={stamp(h?.news_ingested_at)} />
            <Row k={isTh ? 'ดึงตารางปันผลเมื่อ' : 'dividends fetched at'} v={stamp(h?.dividends_ingested_at)} />
            <Row k={isTh ? 'จับคู่ล่าสุดเมื่อ' : 'matched at'} v={stamp(h?.matched_at)} />
            <Row
              k={isTh ? 'เกณฑ์คะแนนที่ใช้คัด' : 'score cut-off'}
              v={`${num(h?.score_threshold)} ${isTh ? '(คงที่)' : '(fixed)'}`}
            />
          </dl>
        </section>
      </div>
    </div>
  )
}
