# -*- coding: utf-8 -*-
"""ให้ Claude Code อ่านเนื้อหาเต็มของข่าว แล้วเติมสิ่งที่กฎคำอ่านไม่ออก (AI-01)

จุดที่ใช้ — มาจากการตรวจคลังจริง ไม่ใช่เดา:
  1. หุ้นที่บทความพูดถึงจริง — บทวิเคราะห์รายกลุ่มเขียน "หุ้นเด่น: BBL KTB KBANK"
     แต่ API ส่ง stock=[] มา ระบบจึงเคยจับได้แค่ระดับกลุ่ม
  2. ทิศทาง — 23% ของข่าวตอบ "ไม่บอกทิศทาง" เพราะจับจากคีย์เวิร์ดในพาดหัวไม่ได้
  3. macro — เดิมอ่านจากพาดหัว+สรุปเท่านั้น

หลักการที่ไม่ผ่อน: โมเดล "เสนอ" เท่านั้น ทุกอย่างที่ลงฐานต้องผ่านด่านตรวจของโค้ด
และสิ่งที่ "ไม่ตีความ" ต้องบอกเหตุผลได้เท่ากับสิ่งที่ตีความ (AI-02)

ด่านตรวจตัวย่อหุ้น 4 ชั้น — ผิดชั้นไหนก็ทิ้ง และบันทึกไว้ว่าทิ้งเพราะอะไร:
  1. ตัวย่อต้องพิมพ์อยู่ในบทความจริง (คำเต็ม) — กันโมเดลแปลงชื่อบริษัทเป็นตัวย่อเอง
  2. ประโยคที่ยกมาต้องมีอยู่ในบทความจริง (llm.verify_quote)
  3. ประโยคนั้นต้องเอ่ยถึงหุ้นตัวนั้น (ตัวย่อหรือชื่อบริษัท) — กันยกประโยคของหุ้นตัวอื่นมาแปะ
  4. ตลาดต้องไม่ขัดกัน — บทความหุ้นนอกห้ามแปลงเป็นตัวย่อหุ้นไทยที่สะกดเหมือนกัน
     (เจอจริง: TEL = Tokyo Electron, 8035, ASTS, IBM)
ที่ตรวจไม่ผ่านถูกทิ้งและบันทึกลงตาราง unmapped + คอลัมน์ ai_mentions — ห้ามเงียบ (STEP8)
"""
from __future__ import annotations

import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor

from . import briefing, db, llm
from .mapping import Universe, refdata
from .tables import BLOOMBERG_COUNTRY
from .news import (SEGMENTED_SUBCATEGORIES, build_alias_index, sector_of,
                   universe_from_db)

MAX_TEXT = 6000          # เนื้อหาไทยยาวกว่านี้มักเป็นบทวิเคราะห์ที่ท่อนสำคัญอยู่ต้น ๆ
DIRECTIONS = {"up", "down", "mixed", "position_dependent", "unknown"}

# role ที่โมเดลต้องติดให้ทุกตัวย่อที่เจอ — โค้ดรับแค่ 3 อันแรก
# mention_only คือหัวใจของ AI-02: บทความที่แค่ "เล่าถึง" บริษัท (ประวัติบริษัท ยกตัวอย่าง
# ประกอบ อ้างเป็นข้อมูลพื้นหลัง) ต้องไม่ถูกนับเป็นการแนะนำหุ้น
ROLE_TH = {
    "recommend": "บทความมองเป็นบวก/แนะนำ",
    "avoid": "บทความมองเป็นลบ/ให้เลี่ยง",
    "analyze": "บทความวิเคราะห์หุ้นตัวนี้เป็นเรื่องหลัก",
}
ROLE_MENTION = "mention_only"

# เหตุผลที่ "ไม่สรุปทิศทาง" — โมเดลเป็นคนเลือกจากรายการนี้เท่านั้น ห้ามเขียนเอง
NO_CALL_TH = {
    "history_only": "บทความเล่าประวัติหรืออธิบายตัวบริษัท ไม่ได้ให้มุมมองต่อราคา",
    "data_only": "บทความรายงานตัวเลขหรือเหตุการณ์ ไม่ได้สรุปทิศทาง",
    "no_view": "บทความไม่ได้บอกทิศทางไว้",
    "not_about_stock": "บทความไม่ได้พูดถึงสินทรัพย์รายตัว",
    "conflicting": "บทความพูดสองด้านโดยไม่ได้สรุป",
    "other": "อ่านแล้วไม่พบประโยคที่บอกทิศทางไว้ตรง ๆ",
}
# เหตุผลที่ "โค้ด" เป็นคนตัดสิน ไม่ใช่โมเดล
NO_CALL_BY_CODE = {
    "quote_failed": "โมเดลบอกทิศทางมา แต่ประโยคที่ยกมาไม่มีอยู่ในบทความ จึงไม่รับ",
    "bad_answer": "โมเดลตอบผิดรูปแบบ อ่านไม่ได้",
    "no_text": "ไม่มีเนื้อหาให้อ่าน",
}

# กติกาชุดเดียวใช้ร่วมกันทั้ง prompt เดี่ยว (PROMPT) และ prompt กลุ่ม (_build_batch_prompt)
# ไม่มีวงเล็บปีกกาปนอยู่ในนี้ — ต่อเป็น string เฉย ๆ ปลอดภัยกับ .format() ทั้งสองที่ที่ใช้มัน
RULES = """กติกา — สำคัญมาก:

[stocks]
- ใส่ให้ครบทุกตัวย่อที่บทความเอ่ยถึง แม้จะเอ่ยผ่าน ๆ ห้ามคัดออกเอง ให้บอก role แทน
- role:
  · recommend    = บทความแนะนำหรือมองบวกต่อหุ้นตัวนั้นตรง ๆ (เช่นอยู่ใน "หุ้นเด่น" / "Top picks")
  · avoid        = บทความมองลบ หรือแนะนำให้เลี่ยง
  · analyze      = บทความวิเคราะห์หุ้นตัวนั้นเป็นเรื่องหลัก แต่ไม่ได้ชี้ว่าซื้อหรือเลี่ยง
  · mention_only = แค่ยกตัวอย่าง เล่าประวัติบริษัท เอ่ยชื่อประกอบ หรือเป็นข้อมูลพื้นหลัง
- ไม่แน่ใจระหว่าง analyze กับ mention_only ให้ตอบ mention_only เสมอ
- symbol ต้องเป็นตัวย่อที่ "พิมพ์อยู่ในบทความจริง ๆ" ห้ามแปลงจากชื่อบริษัทเอง ห้ามเติมชื่อตลาด
  บทความเขียนแต่ชื่อบริษัท ไม่ได้พิมพ์ตัวย่อ ให้ symbol เป็น "" แล้วใส่ชื่อใน name
- name เขียนตามที่บทความเขียน (Nvidia / Tokyo Electron) ห้ามแปลเป็นไทยหรือย่อเอง
- market บอกตลาดที่หุ้นตัวนั้นจดทะเบียน: หุ้นไทย/SET = "TH" · หุ้นสหรัฐ = "US"
  · ญี่ปุ่น = "JP" · ฮ่องกง = "HK" · จีน = "CN" · เกาหลี = "KR" · ไต้หวัน = "TW"
  ไม่แน่ใจว่าตลาดไหน แต่รู้ว่าไม่ใช่ไทย ให้ตอบ "ต่างประเทศ"
- quote ต้องคัดลอกจากบทความคำต่อคำ ห้ามเรียบเรียงใหม่ ห้ามแปล ห้ามแต่ง
  และประโยคนั้นต้องเอ่ยถึงหุ้นตัวนั้น (ตัวย่อหรือชื่อบริษัท)
  ถ้ายกประโยคไม่ได้ ให้ใส่ quote เป็น "" แล้ว role = mention_only

[direction]
- คือทิศทางที่ "บทความบอกไว้เอง" ไม่ใช่ความเห็นของคุณ
- ถ้าบทความไม่ได้ระบุ ให้ตอบ unknown แล้ว quote เป็น ""
- position_dependent = ผลบวกหรือลบขึ้นกับว่าถือตัวไหน (เช่นดีต่อผู้ผลิต แต่ลบต่อผู้ใช้)

[no_call_reason]
- ตอบทุกครั้งที่ overall = unknown ว่าที่ไม่สรุปทิศทางเป็นเพราะอะไร เลือกจากรหัสข้างบนเท่านั้น
  · history_only    บทความเล่าประวัติ/อธิบายตัวบริษัท
  · data_only       รายงานตัวเลขหรือเหตุการณ์เฉย ๆ
  · no_view         ไม่ได้บอกทิศทางไว้
  · not_about_stock ไม่ได้พูดถึงสินทรัพย์รายตัว
  · conflicting     พูดสองด้านโดยไม่สรุป
- ถ้า overall ไม่ใช่ unknown ให้ใส่ ""

[macro]
- ใส่เฉพาะที่บทความพูดถึงจริง ไม่มีก็ใส่ []"""

PROMPT = """คุณกำลังช่วยโบรกเกอร์ไทยอ่านบทวิเคราะห์ เพื่อบอกผู้ดูแลลูกค้าว่าข่าวนี้เกี่ยวกับหุ้นตัวไหน

อ่านบทความข้างล่าง แล้วตอบเป็น JSON เท่านั้น ไม่ต้องอธิบายอะไรเพิ่ม:

{{
  "stocks": [
    {{"symbol": "ตัวย่อเฉพาะที่บทความพิมพ์ตัวย่อไว้จริง ไม่มีให้ใส่ \\"\\"",
      "name": "ชื่อบริษัทตามที่บทความเขียน",
      "market": "TH | US | JP | HK | CN | KR | TW | VN | SG | ต่างประเทศ",
      "role": "recommend | avoid | analyze | mention_only",
      "quote": "ประโยคจากบทความที่ทำให้รู้"}}
  ],
  "direction": {{"overall": "up|down|mixed|position_dependent|unknown",
                 "quote": "ประโยคจากบทความที่ทำให้รู้"}},
  "no_call_reason": "history_only|data_only|no_view|not_about_stock|conflicting|other",
  "macro": ["ดอกเบี้ย", "ค่าเงิน", "เงินเฟ้อ", "สงครามการค้า", "ราคาน้ำมัน", "เศรษฐกิจโลก"]
}}

""" + RULES + """

พาดหัว: {title}

เนื้อหา:
{body}
"""

# ---- ตลาดของสินทรัพย์ ------------------------------------------------------
# ใช้ตัดเคสตัวย่อชนกันข้ามตลาด ซึ่งเป็นความเสี่ยงที่แพงที่สุดของงานนี้:
# ส่งรายชื่อลูกค้าที่ถือหุ้นไทย เพราะข่าวหุ้นสหรัฐที่บังเอิญสะกดตัวย่อเหมือนกัน
_CLASS_MARKET = {
    "EQUITY_TH": "TH", "TFEX": "TH", "BOND_TH": "TH", "STRUCTURED_NOTE": "TH",
    "FUND_DIY": "TH", "FUND_ROBO": "TH",
    "EQUITY_OFFSHORE": "foreign", "OPTIONS_OFFSHORE": "foreign",
    "FUND_OFFSHORE": "foreign", "BOND_OFFSHORE": "foreign",
    "DIGITAL_ASSET": "global",
}
_TH_WORDS = {"TH", "THAI", "THAILAND", "SET", "MAI", "ไทย", "หุ้นไทย", "ตลาดหุ้นไทย"}
# คำตอบ market ของโมเดล -> รหัสประเทศใน BLOOMBERG_COUNTRY
# ต้องรู้ถึงระดับประเทศ เพราะตัวย่อเดียวกันคนละตลาดคือคนละบริษัท:
# TEL ที่ญี่ปุ่นคือ Tokyo Electron แต่ TEL:xnys ในพอร์ตลูกค้าคือ TE Connectivity
_COUNTRY = {
    "US": "US", "USA": "US", "NYSE": "US", "NASDAQ": "US", "สหรัฐ": "US", "อเมริกา": "US",
    "JP": "JP", "JAPAN": "JP", "ญี่ปุ่น": "JP",
    "HK": "HK", "HONGKONG": "HK", "HONG KONG": "HK", "ฮ่องกง": "HK",
    "CN": "CN", "CHINA": "CN", "จีน": "CN",
    "KR": "KS", "KS": "KS", "KOREA": "KS", "เกาหลี": "KS",
    "TW": "TT", "TT": "TT", "TAIWAN": "TT", "ไต้หวัน": "TT",
    "VN": "VN", "VIETNAM": "VN", "เวียดนาม": "VN",
    "SG": "SG", "SINGAPORE": "SG", "สิงคโปร์": "SG",
    "AU": "AU", "CA": "CA", "MY": "MY", "ID": "ID", "IN": "", "UK": "LN", "LN": "LN",
}


def crypto_ids(con) -> set[str]:
    """รหัสคริปโตที่ลูกค้าถือจริง — ไม่ผูกตลาด จึงยกเว้นจากด่านตรวจตลาด"""
    return {r["entity"] for r in con.execute(
        "SELECT DISTINCT entity FROM holdings "
        "WHERE asset_class='DIGITAL_ASSET' AND entity IS NOT NULL")}


def entity_aliases() -> dict[str, list[str]]:
    """entity -> ชื่อที่ใช้เรียกตัวมันเอง (ตัวย่อ + ชื่อบริษัท) สำหรับตรวจชั้นที่ 3"""
    out: dict[str, list[str]] = {}
    for entity, info in refdata()["entity_dictionary"].items():
        out[entity] = [entity.split(":", 1)[0], *info.get("aliases", [])]
    for tic in refdata()["thai_sector"]:
        out.setdefault(tic, [tic])
    return out


def _entity_market(entity: str, crypto: set[str]) -> str:
    if ":" in entity:
        return "foreign"
    if entity in crypto:
        return "global"
    return "TH"          # รหัสกลางที่ไม่มี MIC และไม่ใช่คริปโต = หุ้นไทย


def _article_markets(art: dict) -> set[str]:
    """ตลาดที่บทความนี้พูดถึง ตาม article_asset_class ที่ API ส่งมา

    ว่าง หรือมี "*" = ไม่จำกัด (ไม่เอามาตัดสิน เพราะข้อมูลไม่ครบ ไม่ใช่หลักฐานว่าไม่ใช่)
    """
    classes = db.jload(art.get("article_asset_class"), []) or []
    if not classes or "*" in classes:
        return set()
    return {m for m in (_CLASS_MARKET.get(c) for c in classes) if m}


def _model_market(v: str) -> tuple[str, tuple[str, ...]]:
    """คำตอบ market ของโมเดล -> (TH | foreign | "", ตลาดที่ยอมรับ)

    รู้ประเทศ = จำกัด MIC ได้ ซึ่งเป็นด่านที่กันตัวย่อชนข้ามประเทศได้จริง
    บอกแค่ "ต่างประเทศ" ก็ยังใช้ได้ แต่ต้องมีตัวย่อพิมพ์อยู่ในบทความและชี้ได้ตัวเดียว
    """
    s = (v or "").strip().upper()
    if not s:
        return "", ()
    if s in _TH_WORDS:
        return "TH", ()
    code = _COUNTRY.get(s, "")
    return "foreign", BLOOMBERG_COUNTRY.get(code, ())


# ---- ด่านตรวจ --------------------------------------------------------------

def _word_in(token: str, text: str) -> bool:
    """ตัวย่อต้องปรากฏแบบคำเต็ม — AP ต้องไม่ไปตรงกับ APPLE

    ตัวย่อภาษาละตินเทียบแบบตรงตัวพิมพ์ (R4.45 ตัวย่อหุ้นเป็นตัวใหญ่ล้วน)
    ข้อความไทยไม่มีการเว้นวรรค จึงเทียบแบบมีอยู่ในข้อความ
    """
    if not token or not text:
        return False
    if token.isascii():
        flags = 0 if token.isupper() else re.I
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text, flags))
    return token in text


def _resolve(token: str, market: str, mics: tuple[str, ...], by_alias: dict,
             uni: Universe, crypto: set[str], curated: bool) -> tuple[str | None, str]:
    """ตัวย่อ/ชื่อบริษัทที่โมเดลบอกมา -> entity ของระบบ · คืน (entity, เหตุผลที่แปลงไม่ได้)

    ทางที่ 1 alias index (Coverage List + พจนานุกรมชื่อบริษัท) — alias ยาว >= 3 ตาม R4.44
    ทางที่ 2 ของที่ "ลูกค้าถืออยู่จริง" แม้ตัวย่อจะยาวแค่ 2 ตัวอักษร (TU, AP)
             ซึ่ง R4.44 กันไว้เพราะกลัวกำกวมเวลากวาดข้อความทั้งบทความ
             แต่ที่นี่ต่างกัน: มีประโยคที่ยกมาเป็นหลักฐาน และตัวย่อต้องผ่านด่าน 1+3
             ถ้าไม่ยอมรับ จะทิ้งของที่ลูกค้าถืออยู่จริงไป (TU 15 คน · AP 15 คน 19.6 ลบ.)

    ตลาดที่โมเดลบอกมาเป็นตัวคุมทิศทางการแปลง ไม่ใช่แค่ข้อมูลประกอบ:
    หุ้นนอกห้ามตกไปเป็นรหัสหุ้นไทยที่สะกดเหมือนกัน กลับกันด้วย และถ้ารู้ประเทศ
    ก็ต้องอยู่ตลาดของประเทศนั้น (TEL ญี่ปุ่น = Tokyo Electron คนละตัวกับ TEL:xnys)
    curated = คำนี้มาจากพจนานุกรมที่คนคัดแล้ว จึงยอมให้ชื่อบริษัทเป็นทางเข้าได้

    ข้อยกเว้น: alias ที่มาจากพจนานุกรมคนคัด (curated) ไม่ต้องผ่านด่านตลาดซ้ำ — เจอจริง:
    "TSMC" ถูกทิ้งเพราะโมเดลบอก market เป็นไต้หวัน (บริบทข่าวพูดถึง TSMC ในฐานะบริษัทไต้หวัน)
    แต่ลูกค้าถือ ADR ที่จดทะเบียนในสหรัฐ (TSM:xnys) เป็นบริษัทเดียวกัน คนละใบหุ้นเดียวกันเอง
    พจนานุกรมมีแค่ทางเดียวต่อชื่อ (ไม่มี "TSMC" ชี้ได้สองบริษัท) จึงเชื่อพจนานุกรมได้มากกว่า
    คำเดาตลาดของโมเดล — ต่างจาก TEL ที่ไม่ได้มาจากพจนานุกรม (มาจากรายการที่ลูกค้าถือ ทาง
    offshore/by_root ด้านล่าง) ซึ่งยังต้องผ่านด่านตลาดเหมือนเดิม เพราะนั่นกำกวมได้จริง
    """
    alias_hit = by_alias.get(token)
    offshore = sorted(c for c in uni.by_root.get(token, set()) if ":" in c)
    if mics:
        offshore = [c for c in offshore if c.rsplit(":", 1)[1] in mics]

    if market == "foreign":
        if len(offshore) == 1:
            return offshore[0], ""
        if len(offshore) > 1:
            return None, f"กำกวม — ลูกค้าถือรหัสนี้ใน {len(offshore)} ตลาด {offshore}"
        if alias_hit and ":" in alias_hit:
            return alias_hit, ""
        if alias_hit:
            return None, f"โมเดลบอกว่าเป็นหุ้นต่างประเทศ แต่รหัสนี้คือ {alias_hit}"
        if mics and uni.by_root.get(token):
            return None, "ลูกค้าถือรหัสนี้ แต่คนละตลาดกับที่บทความพูดถึง"
        return None, "เป็นหุ้นต่างประเทศที่ระบบไม่รู้จัก และไม่มีลูกค้าถือ"

    if market == "TH":
        if alias_hit and ":" not in alias_hit and alias_hit not in crypto:
            return alias_hit, ""
        if token in uni.ids and ":" not in token and token not in crypto:
            return token, ""
        if alias_hit:
            return None, f"โมเดลบอกว่าเป็นหุ้นไทย แต่รหัสนี้คือ {alias_hit}"
        return None, "ไม่รู้จักรหัสนี้ในตลาดไทย และไม่มีลูกค้าถือ"

    # โมเดลไม่ได้บอกตลาด — พจนานุกรมที่คัดแล้วมาก่อน แล้วค่อยของที่ลูกค้าถือ
    if alias_hit:
        return alias_hit, ""
    if curated:
        return None, "ไม่รู้จักชื่อนี้ในพจนานุกรม"
    if token in uni.ids:
        return token, ""
    if len(offshore) == 1:
        return offshore[0], ""
    return None, "ไม่รู้จักรหัสนี้ และไม่มีลูกค้าถือ"


def _seen_in(token: str, text: str, curated: bool) -> bool:
    """คำนี้อ่านได้จากบทความจริงไหม

    ตัวย่อเทียบตรงตัวพิมพ์ (R4.45) แต่ชื่อบริษัทในพจนานุกรมที่คนคัดแล้วเทียบแบบ
    ไม่สนตัวพิมพ์ได้ เพราะบทความพิมพ์ Nvidia บ้าง NVIDIA บ้าง — ไม่ใช่คนละบริษัท
    """
    if _word_in(token, text):
        return True
    if curated and token.isascii():
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
                              text, re.I))
    return False


def judge_stocks(items, body: str, art_markets: set[str], by_alias: dict,
                 uni: Universe, crypto: set[str],
                 aliases_of: dict[str, list[str]]) -> tuple[list[dict], list[dict]]:
    """ตรวจรายการหุ้นที่โมเดลเสนอทีละตัว · คืน (ที่รับ, บันทึกทุกตัวพร้อมผลตรวจ)

    ทุกตัวที่โมเดลเห็นถูกบันทึกไว้หมด ไม่ว่าจะรับหรือทิ้ง เพื่อให้ตอบ RM ได้ว่า
    "บทความเอ่ยถึง ASTS แต่ไม่นับ เพราะแค่เล่าประวัติบริษัท" ไม่ใช่หายไปเงียบ ๆ

    รับคำเข้าได้ 2 ทาง: ตัวย่อที่บทความพิมพ์ไว้ (ทางหลัก) และชื่อบริษัทที่อยู่ใน
    พจนานุกรมที่คนคัดแล้ว (ทางรอง — บทความไทยหลายชิ้นเขียนแต่ "Nvidia" ไม่มีตัวย่อ)
    ทั้งสองทางต้องอ่านได้จากบทความจริง ห้ามให้โมเดลนึกตัวย่อขึ้นมาเอง
    """
    kept: list[dict] = []
    log: list[dict] = []

    for it in items or []:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or "").strip().upper()
        name = str(it.get("name") or "").strip()
        if not sym and not name:
            continue
        role = str(it.get("role") or "").strip().lower()
        quote = str(it.get("quote") or "").strip()
        market, mics = _model_market(str(it.get("market") or ""))
        rec = {"symbol": sym or name.upper(), "name": name, "role": role,
               "market": market, "quote": quote[:180]}

        def note(ok: bool, why: str, entity: str = "", report: bool = True) -> None:
            # report=False สำหรับ "ตัดสินใจแล้วว่าไม่นับ" ซึ่งไม่ใช่ความผิดพลาด
            # จึงไม่ต้องไปกองในตาราง unmapped ที่ไว้ดูของที่ระบบจัดการไม่ได้
            log.append({**rec, "kept": ok, "why": why, "entity": entity, "report": report})

        if role not in ROLE_TH:
            why = ("บทความแค่เอ่ยถึง ไม่ได้ให้มุมมองต่อหุ้นตัวนี้"
                   if role == ROLE_MENTION else f"role '{role}' ไม่อยู่ในรายการที่รับ")
            # ยังแปลงเป็นรหัสให้ด้วย เพราะกฎอาจจับตัวนี้ไปแล้วจากการเจอชื่อในสรุป (R4.42)
            # แล้วลูกค้าที่ถือ AMD จะได้ข่าวของบริษัทอื่นที่แค่เอ่ยถึง AMD ประกอบ
            # ตรงนี้ไม่ได้เพิ่มอะไรลงฐาน จึงไม่ต้องผ่านด่านประโยค แค่ต้องอ่านได้จากบทความ
            seen = None
            for token in [t for t in (sym, name.upper()) if t]:
                if _seen_in(token, body, token in by_alias):
                    seen, _ = _resolve(token, market, mics, by_alias, uni, crypto,
                                       token in by_alias)
                    if seen:
                        break
            note(False, why, seen or "", report=role != ROLE_MENTION)
            continue

        # ชั้น 2 — ประโยคที่ยกมาต้องมีอยู่ในบทความจริง (ตรวจก่อน เพราะใช้ร่วมทุกทางเข้า)
        if not llm.verify_quote(quote, body):
            note(False, "ประโยคที่ยกมาไม่มีอยู่ในบทความ")
            continue

        entity, why = None, ""
        for token in [t for t in (sym, name.upper()) if t]:
            curated = token in by_alias
            # ชั้น 1 — คำนี้ต้องพิมพ์อยู่ในบทความจริง
            if not _seen_in(token, body, curated):
                # แยกให้ชัดว่าเป็น "โมเดลนึกเอง" หรือ "พจนานุกรมยังไม่มีชื่อนี้"
                # อย่างหลังคือช่องว่างของข้อมูลอ้างอิง ซึ่งคนแก้ได้ที่ overrides.json
                why = why or (f"{token}: ยังไม่มีชื่อนี้ในพจนานุกรมของระบบ"
                              if _seen_in(token, body, True)
                              else f"ไม่พบ {token} ในบทความ (โมเดลอาจแปลงจากชื่อบริษัทเอง)")
                continue
            entity, fail = _resolve(token, market, mics, by_alias, uni, crypto, curated)
            if entity:
                # ชั้น 3 — ประโยคต้องเอ่ยถึงหุ้นตัวนี้ ไม่ใช่ประโยคของหุ้นตัวอื่น
                names = [token, *aliases_of.get(entity, [])]
                if not any(_seen_in(n, quote, True) for n in names):
                    entity, why = None, "ประโยคที่ยกมาไม่ได้เอ่ยถึงหุ้นตัวนี้"
                    continue
                break
            why = why or f"{token}: {fail}"
        if not entity:
            note(False, why or "แปลงเป็นรหัสในระบบไม่ได้")
            continue

        # ชั้น 4 — ตลาดต้องไม่ขัดกับตลาดของบทความ
        if art_markets and _entity_market(entity, crypto) == "TH" and "TH" not in art_markets:
            note(False, "บทความไม่ใช่ข่าวตลาดหุ้นไทย แต่รหัสนี้เป็นหุ้นไทย", entity)
            continue

        note(True, ROLE_TH[role], entity)
        kept.append({"entity": entity, "symbol": rec["symbol"], "role": role, "quote": quote})
    return kept, log


def _reason_line(reason: str, mentions: list[dict]) -> str:
    """ประโยคที่หน้าจอเอาไปแสดงตรง ๆ ว่า "ไม่ตีความเพราะอะไร" """
    base = NO_CALL_TH.get(reason) or NO_CALL_BY_CODE.get(reason) or NO_CALL_TH["other"]
    skipped = [m for m in mentions if not m["kept"]]
    if not skipped:
        return base
    shown = ", ".join(f"{m['symbol']} ({m['why']})" for m in skipped[:3])
    more = f" และอีก {len(skipped) - 3} ตัว" if len(skipped) > 3 else ""
    return f"{base} · เอ่ยถึงแต่ไม่นับ: {shown}{more}"


# ---- อ่านหนึ่งชิ้น: เสนอ -> ตรวจ -> บันทึก ---------------------------------

def _body_of(art: dict) -> str:
    # ข้อย่อยต้องอ่านเฉพาะข้อความของตัวเอง ไม่ใช่เนื้อหาเต็มของแม่ที่พูดถึงหุ้นอื่นด้วย
    if art.get("record_type") == "segment":
        return (art.get("segment_text") or "")[:MAX_TEXT]
    return (art.get("full_text") or art.get("summary") or "")[:MAX_TEXT]


def propose(art: dict) -> dict:
    """เรียกโมเดลอย่างเดียว ไม่แตะฐาน — แยกไว้เพื่อยิงขนานกันได้หลายชิ้น"""
    # R3.3 — Brief ต้องจับคู่ที่ระดับข้อย่อย ตัวแม่ห้ามมี entity รวมของทุกข้อ
    # ไม่งั้นลูกค้าที่ถือ AOT จะได้ Brief ทั้งฉบับด้วยเหตุผลของข้อที่พูดถึง DELTA
    if art.get("record_type") == "article" and art.get("subcategory") in SEGMENTED_SUBCATEGORIES:
        return {"skipped": "Brief ตัวแม่ — อ่านที่ระดับข้อย่อย"}
    body = _body_of(art)
    if not body.strip():
        return {"skipped": "ไม่มีเนื้อหาให้อ่าน", "reason": "no_text"}
    data, problem = llm.ask_json(PROMPT.format(title=art.get("title") or "", body=body))
    if problem or not isinstance(data, dict):
        return {"problem": problem or "คำตอบไม่ใช่ JSON object", "body": body}
    return {"data": data, "body": body}


def _build_batch_prompt(items: list[tuple[int, str, str]]) -> str:
    """สร้าง prompt เดียวถามหลายบทความพร้อมกัน — items = [(index, title, body), ...]

    เหตุผล: ทุกครั้งที่เรียก `claude -p` ต้องแบก overhead คงที่ไปด้วยใหม่ทุกครั้ง
    (~8,300 token ต่อการเรียกหนึ่งครั้ง ไม่ว่าจะถามสั้นหรือยาว เพราะแต่ละครั้งเป็น process
    ใหม่ ไม่มี conversation ต่อกัน) รวมหลายบทความเข้า prompt เดียวจึงหารเฉลี่ย overhead
    นี้ข้ามหลายบทความ แทนที่จะจ่ายเต็มซ้ำทุกชิ้น (ดู ENGINEERING-HANDOVER.md ข้อ 5.6.1)
    """
    blocks = "\n\n".join(
        f"=== บทความ INDEX={i} ===\nพาดหัว: {title}\n\nเนื้อหา:\n{body}"
        for i, title, body in items
    )
    return f"""คุณกำลังช่วยโบรกเกอร์ไทยอ่านบทวิเคราะห์ {len(items)} ชิ้นพร้อมกัน เพื่อบอกผู้ดูแลลูกค้าว่า
แต่ละชิ้นเกี่ยวกับหุ้นตัวไหน

อ่านบทความทุกชิ้นข้างล่าง แล้วตอบเป็น JSON array เท่านั้น หนึ่งอ็อบเจกต์ต่อหนึ่งบทความ
ต้องมีให้ครบทุกชิ้นตามจำนวน INDEX ที่กำกับไว้ ห้ามข้ามแม้แต่ชิ้นเดียว ห้ามรวมหลายชิ้นเป็น
คำตอบเดียว ไม่ต้องอธิบายอะไรเพิ่ม:

[
  {{"index": <เลข INDEX ของบทความนั้น ต้องตรงกับที่กำกับไว้ทุกตัว ห้ามเปลี่ยนหรือเรียงใหม่>,
    "stocks": [{{"symbol": "...", "name": "...", "market": "...", "role": "...", "quote": "..."}}],
    "direction": {{"overall": "...", "quote": "..."}},
    "no_call_reason": "...",
    "macro": ["..."]}}
]

{RULES}

บทความที่ต้องอ่านมีทั้งหมด {len(items)} ชิ้น (แต่ละชิ้นกำกับ INDEX ไว้ให้แล้ว):

{blocks}
"""


def propose_batch(arts: list[dict]) -> dict[int, dict]:
    """เรียก Claude ครั้งเดียวถามหลายบทความพร้อมกัน — คืน {ตำแหน่งใน arts: ผลลัพธ์}

    ผลลัพธ์ต่อบทความมีรูปแบบเดียวกับ propose() ทุกอย่าง (data/body หรือ problem/skipped)
    เพื่อให้ enrich_batch() ใช้ pipeline ตรวจ+บันทึกเดิมได้โดยไม่ต้องรู้ว่ามาจากการเรียก
    เดี่ยวหรือเรียกเป็นกลุ่ม

    ความล้มเหลวของบทความหนึ่งชิ้นไม่ทำให้ทั้งกลุ่มเสีย — ถ้าโมเดลตอบไม่ครบหรือ index ไม่ตรง
    เฉพาะชิ้นนั้นถูกทำเครื่องหมาย problem ชิ้นอื่นในกลุ่มเดียวกันที่ตอบมาถูกต้องยังใช้ได้ปกติ
    ล้มทั้งกลุ่มเฉพาะตอนเรียก claude ไม่สำเร็จเลยหรือคำตอบไม่ใช่ JSON array เท่านั้น
    """
    items: list[tuple[int, str, str]] = []      # เฉพาะที่มีเนื้อหาให้อ่านจริง
    out: dict[int, dict] = {}
    for i, art in enumerate(arts):
        if art.get("record_type") == "article" and art.get("subcategory") in SEGMENTED_SUBCATEGORIES:
            out[i] = {"skipped": "Brief ตัวแม่ — อ่านที่ระดับข้อย่อย"}
            continue
        body = _body_of(art)
        if not body.strip():
            out[i] = {"skipped": "ไม่มีเนื้อหาให้อ่าน", "reason": "no_text"}
            continue
        items.append((i, art.get("title") or "", body))
    if not items:
        return out

    prompt = _build_batch_prompt(items)
    # เนื้อหารวมกันหลายชิ้น + ต้องตอบหลายอ็อบเจกต์ ให้เวลามากกว่าเรียกเดี่ยวตามสัดส่วน
    timeout = min(600, llm.TIMEOUT_SECONDS + 40 * (len(items) - 1))
    data, problem = llm.ask_json(prompt, timeout=timeout)
    if problem or not isinstance(data, list):
        msg = problem or "คำตอบไม่ใช่ JSON array"
        for i, _, body in items:
            out[i] = {"problem": msg, "body": body}
        return out

    by_index = {e["index"]: e for e in data
               if isinstance(e, dict) and isinstance(e.get("index"), int)}
    for i, _, body in items:
        entry = by_index.get(i)
        if not isinstance(entry, dict):
            out[i] = {"problem": "โมเดลไม่ได้ตอบสำหรับบทความนี้ในผลลัพธ์แบบกลุ่ม", "body": body}
            continue
        out[i] = {"data": entry, "body": body}
    return out


def judge(art: dict, data: dict, body: str, by_alias: dict, uni: Universe,
          crypto: set[str], aliases_of: dict[str, list[str]]) -> dict:
    """ตรวจข้อเสนอทั้งก้อน — ฟังก์ชันบริสุทธิ์ ไม่แตะฐาน จึงเขียนเทสต์ตรงได้"""
    kept, mentions = judge_stocks(data.get("stocks"), body, _article_markets(art),
                                  by_alias, uni, crypto, aliases_of)

    d = data.get("direction") or {}
    overall = str(d.get("overall") or "unknown")
    dquote = str(d.get("quote") or "").strip()
    if overall not in DIRECTIONS:
        overall = "unknown"
    reason = str(data.get("no_call_reason") or "").strip().lower()
    # ทิศทางที่ไม่มีประโยครองรับ ถือว่าไม่ได้บอก — จะเก็บก็ตอบ RM ไม่ได้ว่ารู้จากไหน
    if overall != "unknown" and not llm.verify_quote(dquote, body):
        overall, dquote, reason = "unknown", "", "quote_failed"
    if overall != "unknown":
        reason = ""
    elif reason not in NO_CALL_TH and reason not in NO_CALL_BY_CODE:
        reason = "other"

    macro = [m for m in (data.get("macro") or []) if isinstance(m, str) and m in body]

    # entity ที่ "กฎจับไว้แล้ว" แต่ AI อ่านเนื้อหาเต็มแล้วเห็นว่าบทความแค่เอ่ยถึง
    # เป็นคนละเรื่องกับของที่ AI เสนอเพิ่ม — อันนี้คือกฎอาจจับเกิน จึงต้องบอกให้รู้
    have = set(db.jload(art.get("entity"), []) or [])
    flagged = [m["entity"] for m in mentions
               if not m["kept"] and m["role"] == ROLE_MENTION and m["entity"] in have]
    return {"kept": kept, "mentions": mentions, "direction": overall, "quote": dquote,
            "reason": reason, "reason_th": _reason_line(reason, mentions) if reason else "",
            "macro": macro, "mention_only": sorted(set(flagged))}


def apply(con, art: dict, verdict: dict, now: str, demote: bool = False) -> dict:
    """บันทึกเฉพาะส่วนที่ผ่านด่านตรวจ + บันทึกเหตุผลของส่วนที่ไม่ผ่าน

    demote=True ให้ถอน entity ที่กฎจับไว้แต่ AI อ่านแล้วเห็นว่าบทความแค่เอ่ยถึง
    ค่าปกติคือ False — ติดป้ายให้เห็นก่อน ไม่ถอนเอง เพราะการถอนคือการตัดรายชื่อ
    ที่ RM เคยเห็นออก ควรเป็นการตัดสินใจของคน ไม่ใช่ผลข้างเคียงของการอ่านข่าว
    """
    have = db.jload(art.get("entity"), []) or []
    ev = db.jload(art.get("evidence"), {}) or {}
    added: list[str] = []
    demoted: list[str] = []
    for item in verdict["kept"]:
        entity, sym, quote = item["entity"], item["symbol"], item["quote"]
        if entity not in have:
            have.append(entity)
            added.append(entity)
        text = f"AI อ่านเนื้อหาเต็มแล้วพบว่า{ROLE_TH[item['role']]}: “{quote[:180]}”"
        # recommend/avoid มีน้ำหนักกว่า analyze จึงให้ทับของเดิมได้ ส่วน analyze ไม่ทับ
        if item["role"] == "analyze":
            ev.setdefault(entity, {"text": text, "token": sym, "rule": "AI-01"})
        else:
            ev[entity] = {"text": text, "token": sym, "rule": "AI-01"}

    # กฎจับไว้ แต่ AI อ่านเนื้อหาเต็มแล้วเห็นว่าแค่เอ่ยถึง — ติดป้ายไว้ให้หน้าจอเตือน
    main = {k["entity"] for k in verdict["kept"]}
    for entity in verdict.get("mention_only", []):
        if entity in main or entity not in have:
            continue
        if demote:
            have.remove(entity)
            ev.pop(entity, None)
            demoted.append(entity)
            continue
        old = ev.get(entity)
        if isinstance(old, dict) and not old.get("ai_mention_only"):
            ev[entity] = {**old, "ai_mention_only": True,
                          "text": old.get("text", "") +
                          " · AI อ่านเนื้อหาเต็มแล้วเห็นว่าบทความแค่เอ่ยถึงตัวนี้ประกอบ"
                          " ไม่ได้วิเคราะห์ตัวนี้"}

    secs = list(dict.fromkeys((db.jload(art.get("sector"), []) or [])
                              + [x for x in (sector_of(e) for e in have) if x]))
    macro_rows = db.jload(art.get("macro_topic"), []) or []
    known = {m.get("topic") for m in macro_rows if isinstance(m, dict)}
    macro_rows += [{"topic": m, "keyword": m} for m in verdict["macro"] if m not in known]

    # ลงบัญชี unmapped เฉพาะของที่ระบบ "จัดการไม่ได้" (STEP8)
    # ส่วนที่ตัดสินใจแล้วว่าไม่นับ (mention_only) ไม่ใช่ความผิดพลาด อยู่ใน ai_mentions พอ
    # raw ใช้ตัวย่ออย่างเดียว ไม่ผูก article_id เพื่อให้ n สะสมข้ามบทความ
    # แล้วเห็นว่า "SERVICENOW ไม่รู้จัก 12 ครั้ง" = ควรเพิ่ม alias ไม่ใช่รายการใช้แล้วทิ้ง
    for m in verdict["mentions"]:
        if m["kept"] or not m.get("report", True):
            continue
        db.report_unmapped(con, "ai", f"{m['symbol']} — {m['why'][:80]}", "AI-01",
                           "ข้อเสนอของ AI ไม่ผ่านการตรวจ จึงไม่ถูกบันทึก",
                           ref=art.get("url") or "", now=now)

    with con:
        con.execute("""UPDATE articles SET entity=?, evidence=?, sector=?, macro_topic=?,
                          ai_direction=?, ai_direction_quote=?, ai_reason=?, ai_reason_th=?,
                          ai_mentions=?, ai_at=?,
                          entity_source=CASE WHEN entity_source='none' AND ?<>''
                                        THEN 'ai' ELSE entity_source END,
                          matched_at=CASE WHEN ?>0 THEN NULL ELSE matched_at END
                       WHERE article_id=?""",
                    (db.jdump(have), db.jdump(ev), db.jdump(secs), db.jdump(macro_rows),
                     verdict["direction"], verdict["quote"], verdict["reason"],
                     verdict["reason_th"], db.jdump(verdict["mentions"]), now,
                     ",".join(added), len(added) + len(demoted), art["article_id"]))
    return {"article_id": art["article_id"], "added": added, "demoted": demoted,
            "direction": verdict["direction"], "reason": verdict["reason"],
            "dropped": sum(1 for m in verdict["mentions"] if not m["kept"]),
            "flagged": [e for e in verdict.get("mention_only", []) if e in have],
            "macro": verdict["macro"]}


def _mark_unread(con, art: dict, reason: str, now: str) -> None:
    """อ่านไม่ได้ก็ต้องเขียนไว้ว่าเพราะอะไร ไม่ปล่อยให้เป็นช่องว่าง"""
    with con:
        con.execute("UPDATE articles SET ai_direction=?, ai_reason=?, ai_reason_th=?, ai_at=? "
                    "WHERE article_id=?",
                    ("unknown", reason, NO_CALL_BY_CODE.get(reason, reason), now,
                     art["article_id"]))


class Refs:
    """ตารางอ้างอิงที่ใช้ซ้ำทั้งล็อต — สร้างครั้งเดียว ไม่ใช่ต่อบทความ"""

    def __init__(self, con, aliases=None, held: Universe | None = None):
        pairs = aliases if aliases is not None else build_alias_index()
        self.by_alias = {a.upper(): e for a, e in pairs}
        self.uni = held if held is not None else universe_from_db(con)
        self.crypto = crypto_ids(con)
        self.aliases_of = entity_aliases()


def enrich_article(con, art: dict, refs: Refs | None = None, now: str = "",
                   demote: bool = False) -> dict:
    """อ่านบทความหนึ่งชิ้นด้วย Claude Code แล้วบันทึกเฉพาะส่วนที่ตรวจผ่าน"""
    now = now or dt.datetime.now().isoformat(timespec="seconds")
    refs = refs or Refs(con)
    out = propose(art)
    if out.get("skipped"):
        if out.get("reason"):
            _mark_unread(con, art, out["reason"], now)
        return {"article_id": art["article_id"], "skipped": out["skipped"]}
    if out.get("problem"):
        db.report_unmapped(con, "ai", art["article_id"], "AI-01", out["problem"],
                           ref=art.get("url") or "", now=now)
        _mark_unread(con, art, "bad_answer", now)
        return {"article_id": art["article_id"], "problem": out["problem"]}
    verdict = judge(art, out["data"], out["body"], refs.by_alias, refs.uni,
                    refs.crypto, refs.aliases_of)
    return apply(con, art, verdict, now, demote)


# ---- อ่านทั้งล็อต ----------------------------------------------------------

def _select(con, limit: int, redo: bool, target: str, date: str | None,
            since: str = "") -> list[dict]:
    """เล็งชิ้นที่ AI ให้ผลจริง ไม่ใช่ไล่ตามลำดับวันเฉย ๆ

    ลำดับความสำคัญ (target='auto'):
      1. กฎตอบทิศทางไม่ได้ (overall = unknown) — จุดที่ RM บ่นว่าเปิดมาแล้วไม่ช่วยอะไร
      2. ไม่มี entity เลย — จับคู่กับลูกค้าไม่ได้ทั้งชิ้น
      3. ที่เหลือ เรียงจากใหม่สุด
    เคยเรียงด้วย "entity ว่างมาก่อน" เฉย ๆ แล้วได้แต่ชิ้นที่กฎตอบทิศทางได้อยู่แล้ว
    ทำให้ AI ไม่เปลี่ยนคำตอบอะไรเลยทั้งรอบ
    """
    where = ["role='content'",
             "((record_type='article' AND full_text IS NOT NULL AND full_text<>'')"
             " OR (record_type='segment' AND segment_text IS NOT NULL AND segment_text<>''))"]
    args: list = []
    if not redo:
        where.append("ai_at IS NULL")
    elif since:
        # อ่านซ้ำทั้งวันเป็นหลายล็อต — ชิ้นที่รอบนี้อ่านไปแล้วต้องไม่ถูกหยิบซ้ำ
        # ไม่งั้นวนอ่านชิ้นเดิมไม่รู้จบ เพราะการจัดลำดับให้ผลเดิมทุกรอบ
        where.append("(ai_at IS NULL OR ai_at < ?)")
        args.append(since)
    if date:                       # อ่านเฉพาะข่าวของวันนั้น — งานเช้าสนใจแค่ของวันนี้
        where.append("substr(trigger_at,1,10)=?")
        args.append(date)
    sql = (f"SELECT * FROM articles WHERE {' AND '.join(where)} "
           f"ORDER BY trigger_at DESC LIMIT {max(int(limit) * 8, 40)}")
    pool = [dict(r) for r in con.execute(sql, args)]

    def rank(a: dict) -> tuple:
        no_entity = (a.get("entity") or "[]") in ("[]", "")
        unknown_dir = briefing.analyse(a)["overall"] == "unknown"
        if target == "unknown_direction" and not unknown_dir:
            return (9,)
        if target == "no_entity" and not no_entity:
            return (9,)
        return (0 if unknown_dir else 1 if no_entity else 2,)

    pool = [a for a in pool if rank(a) != (9,)]
    pool.sort(key=lambda a: rank(a) + (a.get("trigger_at") or "",))
    return pool[:int(limit)]


def remaining(con, date: str | None = None, since: str = "") -> int:
    """ยังเหลือให้อ่านกี่ชิ้น · since = รอบอ่านซ้ำ นับชิ้นที่ยังไม่ได้อ่านในรอบนี้"""
    return con.execute(
        """SELECT COUNT(*) FROM articles WHERE role='content'
           AND (ai_at IS NULL OR (?<>'' AND ai_at < ?))
           AND ((record_type='article' AND full_text IS NOT NULL AND full_text<>'')
             OR (record_type='segment' AND segment_text IS NOT NULL AND segment_text<>''))
           AND (?='' OR substr(trigger_at,1,10)=?)""",
        (since, since, date or "", date or "")).fetchone()[0]


def _propose_chunk(chunk: list[dict]) -> list[dict]:
    """เรียก propose_batch() ให้กลุ่มบทความหนึ่งกลุ่ม คืนผลลัพธ์เรียงลำดับเดิมของ chunk

    ห่อไว้เป็นฟังก์ชันเดียวเพื่อให้ ThreadPoolExecutor.map ยิงหลายกลุ่มขนานกันได้
    เหมือนที่เคยยิงยิงหลายบทความขนานกัน แค่หน่วยงานตอนนี้คือ "กลุ่ม" แทน "ชิ้นเดียว"
    """
    got = propose_batch(chunk)
    return [got.get(i, {"problem": "ไม่มีคำตอบสำหรับบทความนี้"}) for i in range(len(chunk))]


def enrich_batch(con, limit: int = 10, redo: bool = False, target: str = "auto",
                 date: str | None = None, workers: int = 1, dry_run: bool = False,
                 demote: bool = False, since: str = "", batch_size: int = 1) -> dict:
    """อ่านหลายชิ้น — เรียกโมเดลขนานกันได้ แต่เขียนฐานเส้นเดียว

    workers > 1 ยิง claude หลาย process พร้อมกัน (งานนี้รอ I/O ไม่ใช่กิน CPU)
    การเขียน SQLite ทำในเธรดหลักทั้งหมด จึงไม่ต้องกังวลเรื่อง connection ข้ามเธรด
    dry_run = ลองอ่านและตรวจ แต่ไม่บันทึก — ใช้ตรวจคุณภาพก่อนรันจริง

    batch_size > 1 รวมหลายบทความเข้า claude call เดียว (ดู propose_batch) ลดต้นทุน
    overhead คงที่ต่อการเรียกที่ต้องจ่ายซ้ำทุกครั้งถ้ายิงทีละชิ้น — ค่าเริ่มต้น 1 คือพฤติกรรม
    เดิมทุกอย่าง (หนึ่งบทความต่อหนึ่งการเรียก) เพื่อไม่ให้ของเก่าที่ไม่ได้ตั้งค่าใหม่พังหรือช้าลง
    """
    if not llm.available()["available"]:
        return {"problem": "ไม่พบคำสั่ง claude บนเครื่อง", "done": 0}
    now = dt.datetime.now().isoformat(timespec="seconds")
    rows = _select(con, limit, redo, target, date, since)
    refs = Refs(con)
    out = {"tried": len(rows), "done": 0, "entities_added": 0, "directions": {},
           "reasons": {}, "dropped": 0, "problems": 0, "flagged": 0, "demoted": 0,
           "items": [], "at": now, "dry_run": dry_run, "usage": {}}
    if not rows:
        return out

    n = max(1, min(int(workers or 1), 8))
    b = max(1, min(int(batch_size or 1), 8))
    chunks = [rows[i:i + b] for i in range(0, len(rows), b)]
    before = llm.usage()
    with ThreadPoolExecutor(max_workers=n) as pool:
        chunk_results = (list(pool.map(_propose_chunk, chunks)) if n > 1
                         else [_propose_chunk(c) for c in chunks])
    proposals = [r for group in chunk_results for r in group]
    after = llm.usage()
    out["usage"] = {k: round(after[k] - before[k], 4) for k in after}
    out["batch_size"] = b

    for art, got in zip(rows, proposals):
        if got.get("skipped"):
            out["problems"] += 1
            if got.get("reason") and not dry_run:
                _mark_unread(con, art, got["reason"], now)
            continue
        if got.get("problem"):
            out["problems"] += 1
            if not dry_run:
                db.report_unmapped(con, "ai", art["article_id"], "AI-01", got["problem"],
                                   ref=art.get("url") or "", now=now)
                _mark_unread(con, art, "bad_answer", now)
            continue
        verdict = judge(art, got["data"], got["body"], refs.by_alias, refs.uni,
                        refs.crypto, refs.aliases_of)
        res = (apply(con, art, verdict, now, demote) if not dry_run else {
            "added": [k["entity"] for k in verdict["kept"]], "demoted": [],
            "direction": verdict["direction"], "reason": verdict["reason"],
            "flagged": verdict["mention_only"],
            "dropped": sum(1 for m in verdict["mentions"] if not m["kept"])})
        out["done"] += 1
        out["entities_added"] += len(res["added"])
        out["dropped"] += res["dropped"]
        out["flagged"] += len(res.get("flagged") or [])
        out["demoted"] += len(res.get("demoted") or [])
        d = res["direction"]
        out["directions"][d] = out["directions"].get(d, 0) + 1
        if res.get("reason"):
            out["reasons"][res["reason"]] = out["reasons"].get(res["reason"], 0) + 1
        out["items"].append({"article_id": art["article_id"], "title": art["title"][:60],
                             "added": res["added"], "direction": d,
                             "reason": res.get("reason") or "",
                             "reason_th": verdict["reason_th"],
                             "flagged": res.get("flagged") or [],
                             "demoted": res.get("demoted") or [],
                             "mentions": verdict["mentions"]})
    return out
