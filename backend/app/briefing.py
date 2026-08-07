# -*- coding: utf-8 -*-
"""สรุปทิศทางข่าว + ประเด็นที่ควรคุยกับลูกค้า (GAP-22)

STEP7 หลักการหน้าจอข้อ 6 สั่งห้ามแสดงว่าข่าวดีหรือร้าย และ STEP3 ตัด sentiment ทิ้ง
เพราะทดสอบ 300 บทความแล้วได้แค่ 42% และข่าวประธานลาออกถูกติดว่าบวก
เจ้าของงานสั่งให้ใส่กลับ — ทำให้ แต่ไม่ทำแบบเดิมที่พังมาแล้ว

เหตุผลที่ spec ยกมามีสองข้อ และคมไม่เท่ากัน
  ก. โมเดลไม่แม่น          -> เป็นความล้มเหลวของวิธี ไม่ใช่ข้อพิสูจน์ว่าทำไม่ได้
  ข. ทิศทางขึ้นกับว่าถืออะไร -> ข้อนี้ถูกโดยโครงสร้าง น้ำมันขึ้นดีต่อ PTTEP แต่ร้ายต่อสายการบิน

โมดูลนี้จึงไม่เดาอารมณ์จากถ้อยคำ แต่ยกสิ่งที่ "มีแหล่งอ้างอิง" ขึ้นมาแสดง 3 ชั้น
และไม่เคยยุบเป็นค่าเดียวเมื่อบทความพูดสองทาง

  ชั้น 1  คำแนะนำของ INVX เอง  — Top Picks เขียน "แนะนำซื้อ/แนะนำขาย" ไว้ในพาดหัวตรง ๆ
                                 และ Coverage List มี rating + ราคาเป้าหมาย
                                 เป็นจุดยืนที่บ้านตัวเองประกาศแล้ว ยกมาอ้าง ไม่ใช่ตีความ
  ชั้น 2  ข้อเท็จจริงเทียบคาด   — "ดีกว่าคาด" / "ต่ำกว่าคาด" / "ตามคาด" เป็นการรายงานผล
  ชั้น 3  โทนของพาดหัว          — หนุน / กดดัน ฯลฯ ติดป้ายชัดว่าเป็นการอ่านถ้อยคำ
                                 บังคับแสดงวลีที่ทำให้ติดเสมอ เพื่อให้ RM ค้านได้ในหนึ่งสายตา

ทุกวลีผ่านเกณฑ์เดียวกับ R3.38 (ติดเกิน 30% ของคลัง = กว้างเกินไป ใช้ไม่ได้)
ไม่เรียก LLM — ข้อความที่ออกไปถึงลูกค้าต้องได้ผลเดิมทุกครั้ง และชี้แหล่งที่มาได้ทุกบรรทัด
"""
from __future__ import annotations

import re

from . import db, news
from .mapping import coverage_of
from .matching import MACRO_SENSITIVITY

# ==========================================================================
# ชั้น 1 — คำแนะนำที่ INVX ประกาศเอง
# ==========================================================================

HOUSE_CALL = [
    (re.compile(r"แนะนำซื้อ|แนะนำ\s*ซื้อ|\bBUY\b"), "buy",
     "บทความแนะนำ “ซื้อ”", "the article recommends BUY"),
    (re.compile(r"แนะนำขายทำกำไร"), "take_profit",
     "บทความแนะนำ “ขายทำกำไร”", "the article recommends taking profit"),
    (re.compile(r"เพื่อตัดขาดทุน|\bcut\s*loss\b", re.I), "cut_loss",
     "บทความแนะนำ “ขายตัดขาดทุน”", "the article recommends cutting the loss"),
    (re.compile(r"แนะนำขาย|\bSELL\b"), "sell",
     "บทความแนะนำ “ขาย”", "the article recommends SELL"),
    (re.compile(r"\bLONG\b"), "long",
     "บทความแนะนำเปิดสถานะ LONG", "the article suggests a LONG position"),
    (re.compile(r"\bSHORT\b"), "short",
     "บทความแนะนำเปิดสถานะ SHORT", "the article suggests a SHORT position"),
]

CALL_DIRECTION = {"buy": "up", "long": "up", "take_profit": "down",
                  "cut_loss": "down", "sell": "down", "short": "down"}

# ==========================================================================
# ชั้น 2 — ผลเทียบกับที่ตลาดคาด (เป็นการรายงาน ไม่ใช่ความเห็น)
# ==========================================================================

VS_EXPECTED = [
    (re.compile(r"ดีกว่าคาด|แข็งแกร่งกว่าคาด|สูงกว่าคาด|เกินคาด"), "up",
     "ผลออกมา “ดีกว่าคาด”", "results came in better than expected"),
    (re.compile(r"ต่ำกว่าคาด|แย่กว่าคาด|อ่อนกว่าคาด|ผิดคาด"), "down",
     "ผลออกมา “ต่ำกว่าคาด”", "results came in below expectations"),
    (re.compile(r"ตามคาด|เป็นไปตามคาด"), "flat",
     "ผลออกมา “ตามคาด”", "results were in line with expectations"),
]

# ==========================================================================
# ชั้น 3 — โทนของพาดหัว (การอ่านถ้อยคำ ต้องแสดงวลีเสมอ)
# ==========================================================================

TONE_UP = ["ทำสถิติสูงสุด", "ปรับเพิ่มประมาณการ", "ปรับเป้าขึ้น", "ฟื้นตัว", "แข็งแกร่ง",
           "ดีดตัวขึ้น", "รีบาวด์", "แกว่งขึ้น", "ปรับตัวขึ้น", "เพิ่มขึ้น", "พุ่ง",
           "ทะลุ", "หนุน", "โอกาส", "ฟื้น"]
TONE_DOWN = ["ปรับลดประมาณการ", "หั่นเป้า", "ปรับลดเป้า", "ถูกกดดัน", "กดดัน", "อ่อนแอ",
             "ชะลอ", "อ่อนตัว", "แกว่งลง", "ปรับตัวลง", "ลดลง", "ร่วง", "ดิ่ง",
             "ขาดทุน", "เสี่ยง", "ตึงเครียด", "กังวล"]

# คำบวกที่มาขยายคำลบ ไม่ใช่สัญญาณบวกของตัวเอง
# ของจริงที่เจอ: "สะท้อนความเสี่ยงจาก AI Agent ที่เพิ่มขึ้นเร็วกว่าระบบควบคุม"
# เดิมนับ "เพิ่มขึ้น" เป็นบวก + "เสี่ยง" เป็นลบ แล้วสรุปว่าข่าวมีทั้งบวกและลบ
# ซึ่งไม่จริง มันคือวลีลบวลีเดียว
_NEGATIVE_HEAD = ("ความเสี่ยง", "เสี่ยง", "แรงกดดัน", "กดดัน", "ความกังวล", "กังวล",
                  "ต้นทุน", "หนี้", "เงินเฟ้อ", "ความผันผวน", "ผันผวน", "ภาระ")
_ATTACH_WINDOW = 25          # ตัวอักษรก่อนคำบวกที่ถือว่ายังอยู่ในวลีเดียวกัน

# คำเชื่อมที่บอกว่าพาดหัวตั้งใจพูดสองด้าน — "AI แข็งแกร่ง แต่ Smartphone ยังถูกกดดัน"
# แบบนี้ mixed คือคำตอบที่ถูก ต่างจากกรณีที่คำบวกกับคำลบมาจากวลีเดียวกัน
_CONTRAST = re.compile(r"แต่|ขณะที่|ทว่า|ส่วน|อีกด้าน|สวนทาง")

# ==========================================================================

_CALL_PHRASE = {
    "long": re.compile(r"\bLONG\b"),
    "short": re.compile(r"\bSHORT\b"),
    "buy": re.compile(r"แนะนำซื้อ|\bBUY\b"),
    "sell": re.compile(r"แนะนำขาย|\bSELL\b"),
    "take_profit": re.compile(r"แนะนำขายทำกำไร"),
    "cut_loss": re.compile(r"ตัดขาดทุน"),
}

# คำสั่งซื้อขายที่มักเขียนกำกับในวงเล็บ ไม่ใช่ชื่อสินทรัพย์
_NOT_A_TICKER = {"BUY", "SELL", "LONG", "SHORT", "HOLD", "TP", "SL", "BUY)", "SELL)"}
_TICKER_TOKEN = re.compile(r"([A-Z][A-Z0-9]{1,11})")


def _call_targets(kind: str, text: str) -> list[str]:
    """คำแนะนำชี้ไปที่ตัวไหน

    สแกนต่อจากวลีคำแนะนำไปข้างหน้าไม่เกิน 40 ตัวอักษร แล้วเอาตัวย่อตัวแรกที่ไม่ใช่
    คำสั่งซื้อขายเอง (พาดหัวจริงเขียน "แนะนำซื้อ (BUY) - INTC" ถ้าจับตัวแรกจะได้ BUY)
    TFEX ถอด underlying ให้ด้วย (R4.18)
    """
    rx = _CALL_PHRASE.get(kind)
    if not rx:
        return []
    from .mapping import map_tfex
    out: list[str] = []
    for m in rx.finditer(text):
        window = text[m.end(): m.end() + 40]
        for tok in _TICKER_TOKEN.findall(window):
            if tok in _NOT_A_TICKER:
                continue
            res = map_tfex(tok)
            name = res.entity if res.ok else tok
            if name not in out:
                out.append(name)
            break
    return out



def _hits(text: str, words: list[str]) -> list[str]:
    """คืนวลีที่พบ โดยตัดวลีสั้นที่ซ้อนอยู่ในวลียาวออก (ฟื้น ที่อยู่ใน ฟื้นตัว)"""
    found = [w for w in words if w in text]
    return [w for w in found if not any(w != o and w in o for o in found)]


def _attached_to_negative(text: str, word: str) -> bool:
    """คำบวกนี้ไปขยายคำลบที่อยู่ข้างหน้าใช่ไหม (เช่น "ความเสี่ยง...เพิ่มขึ้น")"""
    for m in re.finditer(re.escape(word), text):
        before = text[max(0, m.start() - _ATTACH_WINDOW):m.start()]
        if not any(neg in before for neg in _NEGATIVE_HEAD):
            return False            # เจออย่างน้อยหนึ่งที่ที่ยืนเดี่ยวจริง
    return True


# ==========================================================================
# ชั้น 2 — ประโยคที่บทความระบุทิศทางไว้เอง (ไม่ใช่การอ่านถ้อยคำ)
# ==========================================================================
#
# ของจริงในคลัง: "ระยะสั้นเป็นลบต่อความเชื่อมั่นในผู้พัฒนา Frontier AI …
#                 ขณะที่เป็นบวกต่อความต้องการลงทุนใน Cybersecurity"
# นี่คือทิศทางที่ผู้เขียนระบุเอง อ้างอิงได้ ไม่ใช่การเดาจากคำในพาดหัว
# จับจากเนื้อข่าว (ไม่ใช่แค่พาดหัว) แล้วบังคับแนบประโยคเป็นหลักฐานทุกครั้ง

_STATED = re.compile(
    r"(?:ระยะสั้น|ระยะกลาง|ระยะยาว|โดยรวม|ภาพรวม)?\s*"
    r"(?:มอง|ประเมิน|คาดว่า)?\s*เป็น(บวก|ลบ)ต่อ\s*([^,\.]{2,70}?)"
    r"(?=\s*(?:ขณะที่|แต่|ส่วน|ทั้งนี้|โดย|และ|$|[,\.]))"
)
STATED_MAX = 2               # เก็บไม่เกินสองขา พอให้เห็นว่าเป็นข่าวสองด้าน


AI_DIRECTION_TH = {
    "up": "AI อ่านเนื้อหาเต็มแล้วสรุปว่าบทความมองเป็นบวก",
    "down": "AI อ่านเนื้อหาเต็มแล้วสรุปว่าบทความมองเป็นลบ",
    "mixed": "AI อ่านเนื้อหาเต็มแล้วพบว่าบทความมีทั้งบวกและลบ",
    "position_dependent": "AI อ่านเนื้อหาเต็มแล้วพบว่าผลขึ้นกับว่าถือตัวไหน",
}
AI_DIRECTION_EN = {
    "up": "AI read the full article as positive",
    "down": "AI read the full article as negative",
    "mixed": "AI found both positive and negative in the full article",
    "position_dependent": "AI found the impact depends on what is held",
}


def analyse(article: dict) -> dict:
    """อ่านทิศทางของบทความหนึ่งชิ้นจากสิ่งที่มีแหล่งอ้างอิง

    ข้อย่อยของ Brief ต้องอ่านจาก "ข้อความของข้อนั้นเอง" เท่านั้น
    แถวข้อย่อยรับ summary กับ full_text ของฉบับแม่มาทั้งก้อน (มาจาก **base ตอนซอย)
    ถ้าอ่านจากตรงนั้นจะหยิบหลักฐานของข้ออื่นมาตอบ — ของจริงที่เจอ:
    ข้อ 1 "ฟิวเจอร์สหุ้นสหรัฐฯ บวกต่อ" ถูกตอบว่าไปทางลบ เพราะคำว่า "ต่ำกว่าคาด"
    ที่จริงอยู่ในข้อ 2 เรื่อง Apple
    """
    title = article.get("title") or ""
    is_segment = article.get("record_type") == "segment"
    if is_segment:
        summary = article.get("segment_text") or ""
        body = ""                       # ห้ามใช้เนื้อหาเต็มของแม่
    else:
        summary = article.get("summary") or ""
        body = article.get("full_text") or ""
    text = f"{title} {summary}"
    entities = db.jload(article.get("entity"), []) or []
    macro = [m["topic"] for m in (db.jload(article.get("macro_topic"), []) or [])]

    signals: list[dict] = []

    # ---- ชั้น 1 คำแนะนำของบ้านเอง ----
    # TFEX Daily เขียน "LONG S50U26 ; SHORT USDU26" ในพาดหัวเดียว
    # เก็บให้ครบทุกคำแนะนำ ห้ามหยุดที่ตัวแรก ไม่งั้นจะรายงานครึ่งเดียว
    call_spans: list[tuple[int, int]] = []
    for rx, kind, th, en in HOUSE_CALL:
        m = rx.search(title) or rx.search(summary)
        if not m:
            continue
        # "แนะนำขายทำกำไร" กับ "แนะนำขาย" ติดพร้อมกันเสมอ — เก็บเฉพาะที่เจาะจงกว่า
        if kind == "sell" and any(s["kind"] in ("take_profit", "cut_loss") for s in signals):
            continue
        on = _call_targets(kind, f"{title} {summary}")
        if rx.search(title):
            call_spans.append(rx.search(title).span())
        signals.append({
            "tier": 1, "kind": kind, "direction": CALL_DIRECTION[kind],
            "th": th + (f" — {', '.join(on)}" if on else ""),
            "en": en + (f" — {', '.join(on)}" if on else ""),
            "phrase": m.group(0), "on": on,
            "source_th": "บทความเขียนไว้ตรง ๆ",
            "source_en": "stated in the article",
        })

    # ---- ชั้น 1 rating จาก Thai Stock Coverage List ----
    for e in entities:
        cov = coverage_of(e)
        if not cov or not cov.get("rating") or cov["rating"] == "No rec":
            continue
        up = None
        if cov.get("target_price") and cov.get("last_close"):
            up = cov["target_price"] / cov["last_close"] - 1
        direction = {"Outperform": "up", "Underperform": "down"}.get(cov["rating"], "flat")
        signals.append({
            "tier": 1, "kind": "research_rating", "direction": direction, "entity": e,
            "rating": cov["rating"], "target_price": cov.get("target_price"),
            "last_close": cov.get("last_close"), "upside": up,
            "th": f"INVX Research ให้ {cov['rating']} กับ {e}"
                  + (f" เป้า {cov['target_price']:,.2f} บาท (upside {up:+.0%})" if up is not None else ""),
            "en": f"INVX Research rates {e} {cov['rating']}"
                  + (f", target THB {cov['target_price']:,.2f} ({up:+.0%})" if up is not None else ""),
            "source_th": "จากบทวิเคราะห์ INVX",
            "source_en": "from INVX research",
        })

    # ---- ชั้น 2 ผลเทียบคาด ----
    for rx, direction, th, en in VS_EXPECTED:
        m = rx.search(text)
        if m:
            signals.append({
                "tier": 2, "kind": "vs_expected", "direction": direction,
                "th": th, "en": en, "phrase": m.group(0),
                "source_th": "จากเนื้อข่าว",
                "source_en": "from the article",
            })
            break

    # ---- ชั้น 2 ประโยคที่บทความระบุทิศทางไว้เอง ----
    stated_src = f"{summary} {body}"
    seen_side: set[str] = set()
    for m in _STATED.finditer(stated_src):
        side, target = m.group(1), m.group(2).strip(" ฯ–—-")
        if side in seen_side or len(seen_side) >= STATED_MAX:
            continue
        seen_side.add(side)
        direction = "up" if side == "บวก" else "down"
        signals.append({
            "tier": 2, "kind": "stated_impact", "direction": direction,
            "th": f"บทความระบุว่าเป็น{side}ต่อ {target}",
            "en": f"the article states this is {'positive' if side == 'บวก' else 'negative'} for {target}",
            "phrase": m.group(0).strip(),
            "on": [target],
            "source_th": "ประโยคที่ผู้เขียนระบุไว้เอง",
            "source_en": "stated by the author",
        })

    # ---- ชั้น 3 โทนของพาดหัว ----
    # แสดงเฉพาะเมื่อไม่มีหลักฐานชั้น 1/2 เลย — การอ่านถ้อยคำเป็นทางเลือกสุดท้าย
    # ไม่ใช่ของที่มาแย้งคำแนะนำหรือประโยคที่ผู้เขียนเขียนไว้เอง
    tone_src = title
    for a, b in sorted(call_spans, reverse=True):
        tone_src = tone_src[:a] + ' ' + tone_src[b:]
    up_words, down_words = _hits(tone_src, TONE_UP), _hits(tone_src, TONE_DOWN)
    # คำบวกที่ไปขยายคำลบไม่นับเป็นสัญญาณบวก ("ความเสี่ยง...เพิ่มขึ้น")
    up_words = [w for w in up_words if not _attached_to_negative(tone_src, w)]
    if signals:                       # มีชั้น 1 หรือ 2 อยู่แล้ว
        up_words, down_words = [], []
    for words, direction, th, en in ((up_words, "up", "โทนพาดหัวไปทางบวก", "headline reads positive"),
                                     (down_words, "down", "โทนพาดหัวไปทางลบ", "headline reads negative")):
        if words:
            signals.append({
                "tier": 3, "kind": "headline_tone", "direction": direction,
                "th": f"{th} — จากคำว่า {' / '.join(words)}",
                "en": f"{en} — from {' / '.join(words)}",
                "phrase": " / ".join(words),
                "source_th": "เป็นการอ่านถ้อยคำ ไม่ใช่ข้อเท็จจริง",
                "source_en": "reading the wording of the headline, not a fact",
            })

    # ---- ประเด็นที่ผลต่างกันตามสิ่งที่ถือ (ข้อที่ spec เตือนไว้ถูกต้อง) ----
    two_sided = []
    for topic in macro:
        rule = MACRO_SENSITIVITY.get(topic)
        if rule and not rule.get("all"):
            who = sorted(rule.get("sector", set())) or sorted(rule.get("asset", set()))
            two_sided.append({"topic": topic, "affects": who})

    # ---- สรุปทิศทาง: ยุบเป็นค่าเดียวเฉพาะเมื่อไม่ขัดกันเอง ----
    dirs = {s["direction"] for s in signals if s["direction"] in ("up", "down")}
    # ประเด็นมหภาคสองทางใช้ตัดสินภาพรวมได้เฉพาะบทความที่ไม่ได้เจาะสินทรัพย์ตัวไหน
    # ถ้าบทความพูดถึงหุ้นตัวหนึ่งชัดเจน ทิศทางเป็นของหุ้นตัวนั้น ส่วน macro เป็นข้อควรระวัง
    tiers = {s["tier"] for s in signals}
    if two_sided and not entities:
        overall = "position_dependent"
    elif dirs == {"up"}:
        overall = "up"
    elif dirs == {"down"}:
        overall = "down"
    elif dirs and tiers <= {3} and not _CONTRAST.search(title):
        # ขัดกันเองโดยมีแค่การอ่านถ้อยคำ และพาดหัวไม่ได้มีคำเชื่อมว่าพูดสองด้าน
        # = ไม่มีหลักฐานพอจะบอกทิศทาง ตอบ "ไม่บอกทิศทาง" ตรงกว่าตอบ "มีทั้งบวกและลบ"
        overall = "unknown"
    elif dirs:
        overall = "mixed"
    elif signals:
        overall = "flat"
    else:
        overall = "unknown"

    # ---- ชั้น 2 ทิศทางที่ AI อ่านจากเนื้อหาเต็ม (AI-01) ----
    # ใช้เฉพาะเมื่อกฎ "สรุปไม่ได้" — ไม่ใช่เมื่อไม่มีสัญญาณเลย เพราะเคสที่เป็นปัญหาจริง
    # คือมีสัญญาณจากถ้อยคำแต่ขัดกันเองจนตอบ unknown
    # กฎที่มีหลักฐานตรงตัวยังมาก่อน AI เสมอ และประโยคที่ AI ยกมาถูกเก็บไว้ในสัญญาณ
    # เพื่อให้หน้าจอบอกที่มาได้ ไม่ใช่ "โมเดลว่ามา"
    ai_dir = (article.get("ai_direction") or "").strip()
    ai_quote = (article.get("ai_direction_quote") or "").strip()
    if overall == "unknown" and ai_quote and ai_dir in ("up", "down", "mixed",
                                                        "position_dependent"):
        signals.append({
            "tier": 2, "kind": "ai_read",
            "direction": ai_dir if ai_dir in ("up", "down") else "flat",
            "th": AI_DIRECTION_TH.get(ai_dir, ai_dir),
            "en": AI_DIRECTION_EN.get(ai_dir, ai_dir),
            "phrase": ai_quote[:180], "on": [],
            "source_th": "AI อ่านเนื้อหาเต็มแล้วยกประโยคนี้มา",
            "source_en": "read from the full article by AI, quoting this line",
        })
        overall = ai_dir

    # ---- AI-02 "ไม่ตีความ" ก็ต้องบอกได้ว่าเพราะอะไร ----
    # ช่องว่างบนหน้าจอทำให้ RM เดาเองว่าระบบพัง ทั้งที่คำตอบที่ถูกต้องคือ
    # "บทความเล่าประวัติบริษัท ไม่ได้ให้มุมมองต่อราคา"
    no_call = ""
    if overall == "unknown":
        no_call = (article.get("ai_reason_th") or "").strip()
        if not no_call and not (article.get("ai_at") or ""):
            no_call = "ยังไม่ได้ให้ AI อ่านเนื้อหาเต็มของข่าวนี้"

    best = min((s["tier"] for s in signals), default=9)
    # ความเห็นของนักวิเคราะห์บ้านเราเอง — ของชิ้นที่มีค่าที่สุดสำหรับ RM
    # ติดมากับผลวิเคราะห์ทุกที่ที่เรียก analyse() จะได้ไม่ต้องไปดึงซ้ำทีละจุด
    # ข้อย่อยของ Brief ใช้ full_text ของฉบับแม่ไม่ได้ (เหตุผลเดียวกับ body ข้างบน)
    return {"overall": overall, "signals": signals, "two_sided": two_sided,
            "no_call_th": no_call, "no_call_code": (article.get("ai_reason") or ""),
            "invx_view": "" if is_segment else news.invx_view(article.get("full_text")),
            "invx_points": [] if is_segment else news.invx_view_points(article.get("full_text")),
            "strongest_tier": None if best == 9 else best}


# ==========================================================================
# ประเด็นที่ควรคุย — ประกอบจากข้อเท็จจริงที่ระบบมีอยู่แล้ว ไม่แต่งเอง
# ==========================================================================

# ชื่อที่ผู้ใช้อ่านรู้เรื่อง — ห้ามให้รหัสภายในหลุดไปอยู่บนหน้าจอ
DISPLAY_TH = {
    "EQUITY_TH": "หุ้นไทย",
    "EQUITY_OFFSHORE": "หุ้นต่างประเทศ",
    "OPTIONS_OFFSHORE": "ออปชันต่างประเทศ",
    "FUND_OFFSHORE": "กองทุนต่างประเทศ",
    "BOND_OFFSHORE": "ตราสารหนี้ต่างประเทศ",
    "BOND_TH": "หุ้นกู้ไทย",
    "Banking": "ธนาคาร",
    "Finance & Securities": "เงินทุนและหลักทรัพย์",
    "Insurance": "ประกัน",
    "Energy & Utilities": "พลังงาน",
    "Petrochemicals & Chemicals": "ปิโตรเคมี",
    "Transportation & Logistics": "ขนส่ง",
}
DISPLAY_EN = {
    "EQUITY_TH": "Thai equity", "EQUITY_OFFSHORE": "offshore equity",
    "OPTIONS_OFFSHORE": "offshore options", "FUND_OFFSHORE": "offshore funds",
    "BOND_OFFSHORE": "offshore bonds", "BOND_TH": "Thai bonds",
}


def _label(code: str, th: bool) -> str:
    return (DISPLAY_TH if th else DISPLAY_EN).get(code, code)


LEVEL_ANGLE = {
    "L1_HOLD": ("ถือตัวที่เป็นข่าวอยู่ — คุยเรื่องผลกระทบต่อสิ่งที่ถือโดยตรง",
                "holds the instrument in the news — talk about the direct impact"),
    "L2_WATCH": ("เพิ่งเทรดตัวนี้ใน 90 วันแต่ตอนนี้ไม่ถือ — เปิดบทสนทนาว่ายังสนใจอยู่ไหม",
                 "traded it within 90 days but no longer holds — ask if they are still watching it"),
    "L3_SECTOR": ("ถือหุ้นกลุ่มเดียวกัน — คุยระดับอุตสาหกรรม ไม่ใช่รายตัว",
                  "holds the same sector — frame it at the industry level, not the single name"),
    "L4_RELATED": ("ถือหุ้นที่ถูกกล่าวถึงร่วมกันบ่อย — เป็นการเชื่อมโยงทางอ้อม บอกลูกค้าตามนั้น",
                   "holds a stock frequently co-mentioned — an indirect link; say so"),
    "L5_ASSET": ("ถือสินทรัพย์ประเภทเดียวกัน — คุยภาพรวมของสินทรัพย์กลุ่มนี้",
                 "holds the same asset class — keep it at the asset-class level"),
    "L6_MACRO": ("พอร์ตไวต่อประเด็นมหภาคนี้ — คุยผลต่อพอร์ตรวม",
                 "portfolio is sensitive to this macro topic — talk about the whole book"),
}

LABEL_CAVEAT = {
    "dr": ("ลูกค้าบางรายถือ DR ไม่ใช่หุ้นตัวจริง ราคาและสภาพคล่องต่างกัน ต้องบอกก่อนคุย",
           "some hold the DR, not the underlying share — different price and liquidity"),
    "bond": ("บางรายถือหุ้นกู้ของบริษัทนี้ ไม่ใช่หุ้น ความเสี่ยงคนละแบบ",
             "some hold this issuer's bond, not its equity — a different risk"),
    "tfex": ("บางรายเทรดอนุพันธ์อ้างอิงตัวนี้ ไม่ได้ถือหุ้น",
             "some trade a derivative on this name rather than holding it"),
    "tfex_index": ("เป็นอนุพันธ์ดัชนีหรือสินค้า ไม่ใช่หุ้นรายตัว",
                   "this is an index or commodity derivative, not a single stock"),
    "options": ("บางรายเล่น options อ้างอิงตัวนี้ ไม่ได้ถือหุ้น",
                "some hold options on this name rather than the share"),
    "kiko": ("บางรายถือ KIKO ที่อ้างอิงหุ้นตัวนี้ ผลตอบแทนไม่ได้วิ่งตามราคาหุ้นตรง ๆ",
             "some hold a KIKO linked to this name; the payoff does not track the share directly"),
}


def talking_points(con, article: dict, view: dict) -> list[dict]:
    """ประเด็นคุยรวม ๆ ต่อบทความ — ไม่ใช่รายคน ทุกข้อบอกที่มา"""
    aid = article["article_id"]
    points: list[dict] = []

    def add(kind: str, th: str, en: str, src_th: str, src_en: str) -> None:
        points.append({"kind": kind, "th": th, "en": en,
                       "source_th": src_th, "source_en": src_en})

    # 1. บทความว่าอะไร
    add("headline", article.get("title") or "", article.get("title") or "",
        "", "")

    # 2. จุดยืนที่มีแหล่งอ้างอิง
    for s in view["signals"]:
        if s["tier"] <= 2:
            add("stance", s["th"], s["en"], s["source_th"], s["source_en"])

    # 3. ประเด็นที่ผลต่างกันตามสิ่งที่ถือ
    for t in view["two_sided"]:
        who = ", ".join(_label(x, True) for x in t["affects"][:4])
        who_en = ", ".join(_label(x, False) for x in t["affects"][:4])
        add("two_sided",
            f"ประเด็น{t['topic']} กระทบไม่เหมือนกันในแต่ละพอร์ต กลุ่มที่ไวที่สุดคือ {who} "
            f"— อย่าสรุปให้ลูกค้าว่าดีหรือร้ายเหมือนกันทุกคน",
            f"{t['topic']} does not hit every portfolio the same way; the most exposed are {who_en} "
            f"— do not tell every client the same story",
            "", "")

    # 4. กลุ่มลูกค้าที่เข้าข่าย มาจากผลจับคู่จริง
    levels = list(con.execute(
        "SELECT level, COUNT(*) n FROM matches WHERE article_id=? GROUP BY 1 ORDER BY 1", (aid,)))
    for r in levels:
        th, en = LEVEL_ANGLE.get(r["level"], ("", ""))
        if th:
            add("angle", f"{r['n']} คน — {th}", f"{r['n']} customers — {en}", "", "")

    # 5. ข้อควรระวังที่ระบบรู้จากผลจับคู่จริง
    labels = [r["instrument_label"] for r in con.execute(
        "SELECT DISTINCT instrument_label FROM matches "
        "WHERE article_id=? AND instrument_label<>''", (aid,))]
    for lb in labels:
        th, en = LABEL_CAVEAT.get(lb, (None, None))
        if th:
            add("caveat", th, en, "", "")

    # 6. ความสดของข้อมูล
    as_of = db.get_setting(con, "data_as_of")
    if as_of:
        add("caveat",
            f"ข้อมูลการถือครองเป็นภาพ ณ {as_of} ลูกค้าอาจซื้อขายไปแล้วหลังจากนั้น",
            f"holdings are a snapshot as of {as_of}; the client may have traded since",
            "", "")

    # 7. เส้นที่ห้ามข้าม
    add("disclaimer",
        "นี่ไม่ใช่คำแนะนำการลงทุน จะโทรหรือพูดอะไร คุณเป็นคนตัดสินใจ",
        "The system proposes names and reasons only; it is not investment advice. "
        "What to say, and whether to call, is the RM's decision.",
        "", "")

    return points


def briefing(con, article: dict) -> dict:
    view = analyse(article)
    return {"article_id": article["article_id"], **view,
            "talking_points": talking_points(con, article, view)}
