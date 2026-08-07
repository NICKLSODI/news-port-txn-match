import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

export type Lang = 'th' | 'en'

/**
 * ข้อความทั้งหมดที่ผู้ใช้เห็น
 *
 * คนใช้จริงคือ RM ที่ต้องโทรหาลูกค้า ไม่ใช่คนเขียนสเปค
 * จึงไม่มีเลขกฎ ไม่มีชื่อ field ในระบบ และไม่มีคำอธิบายว่าทำไมระบบถึงทำแบบนี้
 * รายละเอียดพวกนั้นอยู่ที่หน้า "เกี่ยวกับระบบ" กับ "ตรวจสอบข้อมูล" เท่านั้น
 */
const DICT = {
  'app.title': ['วันนี้ควรโทรหาใคร', 'Who to call today'],
  'app.subtitle': ['INVX', 'INVX'],

  'nav.today': ['ข่าววันนี้', 'Today’s news'],
  'nav.news': ['ข่าวทั้งหมด', 'All news'],
  'nav.dividends': ['ตามรอยหุ้นปันผล', 'Dividends'],
  'nav.rm': ['งานวันนี้ของ RM', "Today's work by RM"],
  'nav.mail': ['ส่งอีเมลให้ RM', 'Email the team'],
  'nav.stock': ['หาจากหุ้น', 'By instrument'],
  'nav.admin': ['สำหรับผู้ดูแลระบบ', 'Admin'],
  'nav.customers': ['ลูกค้า', 'Customers'],
  'nav.reports': ['ตรวจสอบข้อมูล', 'Data checks'],
  'nav.spec': ['เกี่ยวกับระบบ', 'About'],
  'nav.upload': ['อัปโหลดข้อมูล', 'Upload data'],
  'nav.settings': ['ตั้งค่า', 'Settings'],
  'nav.menu': ['เมนู', 'Menu'],
  'theme.light': ['สว่าง', 'Light'],
  'theme.dark': ['มืด', 'Dark'],

  'slot.morning': ['ก่อนตลาดเปิด', 'Before the open'],
  'slot.morning.note': ['สรุปเช้า ก่อนเที่ยง', 'Morning wrap, before noon'],
  'slot.intraday': ['ระหว่างวัน', 'During the day'],
  'slot.intraday.note': ['ข่าวรายตัวที่เพิ่งออก', 'Single-name news as it breaks'],
  'slot.evening': ['เย็น', 'Evening'],
  'slot.evening.note': ['สรุปวัน เตรียมตลาดคืน', 'Day wrap, prep for the night session'],

  // เหตุผลที่ลูกค้าคนนี้เข้าข่าย — พูดเป็นภาษาคน ไม่ใช่รหัสระดับ
  'lvl.L1_HOLD': ['ถือตัวนี้อยู่', 'Holds it now'],
  'lvl.L2_WATCH': ['เคยเทรด ตอนนี้ไม่ถือ', 'Traded it, not holding'],
  'lvl.L3_SECTOR': ['ถือหุ้นกลุ่มเดียวกัน', 'Holds the same sector'],
  'lvl.L4_RELATED': ['ถือหุ้นที่เกี่ยวข้องกัน', 'Holds a related stock'],
  'lvl.L5_ASSET': ['ถือสินทรัพย์ประเภทเดียวกัน', 'Same asset class'],
  'lvl.L6_MACRO': ['พอร์ตไวต่อประเด็นนี้', 'Portfolio is exposed'],

  'persona.US_OFFSHORE': ['หุ้นนอก', 'Offshore equity'],
  'persona.FUND_DIY': ['กองทุนเลือกเอง', 'Fund DIY'],
  'persona.THAI_STOCK': ['หุ้นไทย', 'Thai equity'],
  'persona.DORMANT': ['ไม่เคลื่อนไหว', 'Inactive'],
  'persona.CRYPTO': ['คริปโต', 'Crypto'],
  'persona.FUND_ROBO': ['กองทุน robo', 'Robo fund'],
  'persona.DERIVATIVES': ['อนุพันธ์', 'Derivatives'],
  'persona.BOND': ['ตราสารหนี้', 'Bonds'],
  'persona.NO_PORTFOLIO': ['ไม่มีพอร์ต', 'No portfolio'],

  'ac.EQUITY_TH': ['หุ้นไทย', 'Thai equity'],
  'ac.EQUITY_OFFSHORE': ['หุ้นต่างประเทศ', 'Offshore equity'],
  'ac.OPTIONS_OFFSHORE': ['ออปชันต่างประเทศ', 'Offshore options'],
  'ac.FUND_DIY': ['กองทุนเลือกเอง', 'Fund DIY'],
  'ac.FUND_ROBO': ['กองทุน robo', 'Robo fund'],
  'ac.FUND_OFFSHORE': ['กองทุนต่างประเทศ', 'Offshore fund'],
  'ac.DIGITAL_ASSET': ['คริปโต', 'Crypto'],
  'ac.BOND_TH': ['หุ้นกู้ไทย', 'Thai bond'],
  'ac.BOND_OFFSHORE': ['ตราสารหนี้ต่างประเทศ', 'Offshore bond'],
  'ac.TFEX': ['อนุพันธ์ TFEX', 'TFEX'],
  'ac.STRUCTURED_NOTE': ['หุ้นกู้อนุพันธ์', 'Structured note'],
  'ac.OTHER': ['อื่น ๆ', 'Other'],

  'u.now': ['ควรโทรวันนี้', 'Call today'],
  'u.this_week': ['สัปดาห์นี้', 'This week'],
  'u.low': ['ไม่เร่ง', 'Not urgent'],

  'mode.realtime': ['ข่าวรายตัว', 'Single name'],
  'mode.digest': ['สรุปรวม', 'Digest'],

  // เตือนว่าลูกค้าถือของที่ไม่ใช่หุ้นตัวจริง — สำคัญมากตอนคุย
  'lbl.dr': ['ถือ DR ไม่ใช่หุ้นตัวจริง', 'holds the DR, not the share'],
  'lbl.bond': ['ถือหุ้นกู้ ไม่ใช่หุ้น', 'holds the bond, not the share'],
  'lbl.tfex': ['เทรดอนุพันธ์ ไม่ได้ถือหุ้น', 'trades the derivative, not the share'],
  'lbl.tfex_index': ['อนุพันธ์ดัชนี ไม่ใช่หุ้นรายตัว', 'index derivative, not a single stock'],
  'lbl.options': ['เล่นออปชัน ไม่ได้ถือหุ้น', 'holds options, not the share'],
  'lbl.kiko': ['ถือ KIKO ที่อ้างอิงหุ้นนี้', 'holds a KIKO linked to this share'],

  'tier.vip': ['พอร์ต 20 ลบ.+', '20M+'],
  'tier.large': ['5–20 ลบ.', '5–20M'],
  'tier.mid': ['1–5 ลบ.', '1–5M'],
  'tier.small': ['ต่ำกว่า 1 ลบ.', 'under 1M'],

  'freq.very_active': ['เทรดถี่มาก', 'Very active'],
  'freq.active': ['เทรดถี่', 'Active'],
  'freq.passive': ['เทรดบ้าง', 'Occasional'],
  'freq.inactive': ['ไม่เทรด', 'Inactive'],

  'pnl.profit': ['กำลังกำไร', 'In profit'],
  'pnl.loss': ['กำลังขาดทุน', 'At a loss'],
  'pnl.unknown': ['ไม่ทราบ', 'Unknown'],

  'k.customers': ['ลูกค้า', 'Customers'],
  'k.articles': ['ข่าว', 'Articles'],
  'k.segments': ['หัวข้อย่อย', 'Sub-items'],
  'k.matches': ['รายชื่อ', 'Names'],
  'k.unmapped': ['รหัสที่อ่านไม่ออก', 'Unreadable codes'],
  'k.weak': ['ข่าวที่ควรตรวจ', 'Worth a check'],
  'k.score': ['คะแนน', 'Score'],
  'k.level': ['เกี่ยวข้องยังไง', 'How they relate'],
  'k.reason': ['ทำไมต้องโทรหาคนนี้', 'Why call them'],
  'k.persona': ['กลุ่ม', 'Group'],
  'k.rm': ['ผู้ดูแล', 'RM'],
  // มุมมองแยกตามผู้ดูแล — ใช้ทั้งหน้าหุ้นและหน้าแรก
  'k.byRm': ['แยกตามผู้ดูแล', 'By RM'],
  'k.allRms': ['ทุกคน', 'All'],
  'k.showAll': ['แสดงทุกคน', 'Show all'],
  'k.shareOfBook': ['ของบุ๊ก', 'of book'],
  'k.allRmsTotal': ['รวมทุกผู้ดูแล', 'All RMs combined'],
  'k.portfolio': ['มูลค่าพอร์ต', 'Portfolio'],
  'k.holdings': ['ที่ถืออยู่', 'Holdings'],
  'k.watchlist': ['เคยสนใจ', 'Previously traded'],
  'k.entity': ['สินทรัพย์', 'Instrument'],
  'k.importance': ['ความสำคัญ', 'Importance'],
  'k.urgency': ['ความเร่งด่วน', 'Urgency'],
  'k.lastTrade': ['เทรดล่าสุด', 'Last trade'],
  'k.value': ['มูลค่า', 'Value'],
  'k.date': ['วันที่', 'Date'],
  'k.rule': ['กฎ', 'Rule'],
  'k.source': ['ที่มา', 'Source'],

  'a.openArticle': ['อ่านข่าวเต็ม', 'Read the full article'],
  'a.showMore': ['ดูเพิ่ม', 'Show more'],
  'a.evidence': ['ดูรายละเอียด', 'Details'],
  'a.hideEvidence': ['ปิด', 'Close'],
  'a.refreshNews': ['ดึงข่าวใหม่', 'Fetch news'],
  'a.reingest': ['อัปเดตข้อมูลลูกค้า', 'Refresh customer data'],
  'a.rematch': ['คำนวณใหม่', 'Recalculate'],
  'a.copy': ['คัดลอกรายชื่อ', 'Copy list'],
  'a.copied': ['คัดลอกแล้ว', 'Copied'],
  'a.search': ['ค้นหา', 'Search'],
  'a.clear': ['ล้าง', 'Clear'],
  'a.all': ['ทั้งหมด', 'All'],

  'msg.empty.today': ['วันนี้ยังไม่มีข่าวใหม่', 'No news published yet today'],
  'msg.empty.day': ['วันนี้ไม่มีข่าว', 'No news on this date'],
  'msg.empty.matches': ['ไม่มีลูกค้าเข้าเกณฑ์สำหรับข่าวนี้', 'No customer matches this article'],
  'msg.empty': ['ไม่มีข้อมูล', 'Nothing here'],
  'msg.dataLag': ['ข้อมูลลูกค้า ณ', 'Customer data as of'],
  'msg.daysAgo': ['วันก่อน', 'days ago'],
  'msg.notSentToClient': [
    'ระบบช่วยหารายชื่อและเหตุผล ส่วนจะโทรหรือพูดอะไร คุณเป็นคนตัดสินใจ',
    'The system finds the names and the reason. Whether to call, and what to say, is your call.',
  ],

  'd.today': ['วันนี้', 'Today'],
  'd.notToday': ['ย้อนหลัง', 'Earlier'],
  'd.backToToday': ['กลับมาวันนี้', 'Back to today'],
  'd.goLatest': ['ไปวันที่มีข่าวล่าสุด', 'Go to the latest day with news'],
  'd.prev': ['วันก่อนหน้า', 'Previous day'],
  'd.next': ['วันถัดไป', 'Next day'],

  // ทิศทางข่าว
  'b.title': ['ข่าวนี้ไปทางไหน และควรคุยอะไร', 'Which way this points, and what to say'],
  'b.signals': ['ทิศทางมาจากไหน', 'Where the direction comes from'],
  'b.points': ['ประเด็นที่ควรคุย', 'What to talk about'],
  'b.tier1': ['คำแนะนำจากบทวิเคราะห์', 'From INVX research'],
  'b.tier2': ['สิ่งที่บทความรายงานไว้เอง', 'Reported in the article'],
  'b.tier3': ['จากถ้อยคำในพาดหัว (ไม่มีหลักฐานอื่น)', 'From the headline wording only'],

  'ov.up': ['ไปทางบวก', 'Positive'],
  'ov.down': ['ไปทางลบ', 'Negative'],
  'ov.mixed': ['มีทั้งบวกและลบ', 'Both positive and negative'],
  'ov.flat': ['เป็นกลาง', 'Neutral'],
  'ov.position_dependent': ['ขึ้นกับว่าลูกค้าถืออะไร', 'Depends on what they hold'],
  'ov.unknown': ['ข่าวไม่ได้บอกทิศทาง', 'The news states no direction'],

  // AI-02 — เหตุผลที่ AI อ่านเนื้อหาเต็มแล้วสรุปทิศทางไม่ได้ (แสดงเฉพาะภาษาอังกฤษ
  // ฝั่งไทยใช้ประโยคเต็มจาก backend ตรง ๆ เพราะมีรายชื่อตัวย่อที่ถูกทิ้งต่อท้ายด้วย)
  'ai.notRead': ['', 'AI has not read this article yet'],
  'ai.reason.history_only': ['', 'The article recounts company history, not a price view'],
  'ai.reason.data_only': ['', 'The article reports figures or events only, no stated direction'],
  'ai.reason.no_view': ['', 'The article states no direction'],
  'ai.reason.not_about_stock': ['', 'The article does not discuss a single instrument'],
  'ai.reason.conflicting': ['', 'The article argues both sides without a conclusion'],
  'ai.reason.other': ['', 'No sentence stating a direction was found'],
  'ai.reason.quote_failed': ['', 'AI stated a direction, but the quoted sentence was not in the article'],
  'ai.reason.bad_answer': ['', 'AI returned an unreadable response'],
  'ai.reason.no_text': ['', 'No text was available to read'],

  // หน้าตรวจสอบข้อมูล (สำหรับผู้ดูแล)
  'rep.unmapped': ['รหัสที่อ่านไม่ออก', 'Unreadable codes'],
  'rep.verification': ['คุณภาพการอ่านข่าว', 'News-reading quality'],
  'rep.coverage': ['ความครอบคลุม', 'Coverage'],
  'rep.related': ['ความสัมพันธ์หุ้น', 'Stock relationships'],
  'rep.unmapped.note': [
    'หน้านี้สำหรับผู้ดูแลระบบ ใช้ดูว่ามีอะไรที่ระบบอ่านไม่ออกหรือควรตรวจซ้ำ',
    'For administrators — what the system could not read, and what deserves a second look.',
  ],
  'rep.coverage.note': [
    'ลูกค้าที่ไม่เคยเข้าเกณฑ์เลย มักแปลว่าไม่มีข่าวเกี่ยวกับสิ่งที่เขาถือ',
    'Customers who never match usually hold things the newsroom does not write about.',
  ],
  'rep.related.note': [
    'ระบบเรียนเองว่าหุ้นตัวไหนมักถูกพูดถึงด้วยกัน',
    'The system learns which stocks tend to be mentioned together.',
  ],
  // ระดับความรุนแรงของสิ่งที่ระบบอ่านไม่ออก — เรียงตามผลกระทบ ไม่ใช่ความถี่
  'sev.high': ['ต้องแก้ก่อน', 'Fix first'],
  'sev.medium': ['กระทบบางคน', 'Affects some customers'],
  'sev.low': ['ไม่กระทบรายชื่อ', 'No effect on the lists'],
  'rep.new': ['ใหม่', 'new'],
  'rep.impact.note': [
    'เรียงตามผลกระทบจริง ไม่ใช่จำนวนครั้งที่เจอ — รหัสที่เจอบ่อยแต่ไม่มีใครถือ สำคัญน้อยกว่ารหัสที่เจอน้อยแต่มีคนถือเยอะ',
    'Ranked by real impact, not how often it appears — something seen often but held by nobody matters less than something seen rarely but held widely.',
  ],
  'rep.neverMatched': ['ไม่เคยเข้าเกณฑ์', 'Never matched'],
  'rep.covered': ['มีข่าวถึง', 'Has coverage'],
  'rep.instruments': ['สินทรัพย์', 'Instruments'],

  'g.confirmed': ['ชัดเจน', 'Clear'],
  'g.auto_verified': ['ตรวจแล้วผ่าน', 'Checked, passed'],
  'g.weak': ['ควรตรวจ', 'Worth a check'],
  'g.unknown': ['ยังไม่ตรวจ', 'Not checked'],
  'g.checks': ['รายละเอียดการตรวจ', 'Check detail'],

  'spec.gaps': ['จุดที่เอกสารไม่ครบ และระบบตั้งค่าเอง', 'Where the spec is silent and the system chose'],
  'spec.gaps.note': [
    'สำหรับทีมพัฒนา — ทุกข้อคือจุดที่เอกสารไม่ได้ระบุหรือไม่ตรงกับข้อมูลจริง',
    'For the build team — each item is a place the docs are silent or disagree with the real data.',
  ],
  'spec.assumed': ['ระบบตั้งไว้', 'The system uses'],
  'spec.levels': ['ลูกค้าเข้าเกณฑ์ได้ยังไงบ้าง', 'How a customer qualifies'],
  'spec.formula': ['คะแนนคิดยังไง', 'How the score is computed'],

  'set.running': ['กำลังทำงาน…', 'Working…'],
} satisfies Record<string, [string, string]>

export type Key = keyof typeof DICT

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({
  lang: 'th',
  setLang: () => {},
})

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    try {
      return (localStorage.getItem('mp-lang') as Lang) || 'th'
    } catch {
      return 'th'
    }
  })
  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    try {
      localStorage.setItem('mp-lang', l)
    } catch {}
  }, [])
  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])
  return <Ctx.Provider value={{ lang, setLang }}>{children}</Ctx.Provider>
}

export function useI18n() {
  const { lang, setLang } = useContext(Ctx)
  const t = useCallback(
    (key: Key | string, fallback?: string) => {
      const row = (DICT as Record<string, [string, string]>)[key]
      if (!row) return fallback ?? key
      return lang === 'th' ? row[0] : row[1]
    },
    [lang],
  )
  return { lang, setLang, t, isTh: lang === 'th' }
}
