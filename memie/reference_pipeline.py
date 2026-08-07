# -*- coding: utf-8 -*-
"""
reference_pipeline.py
โครงโค้ดอ้างอิง — News–Customer Matching (INVX)

** นี่คือ "โครง" ไม่ใช่ production code **
เขียนให้เห็นภาพว่า logic ในสเปค STEP1-8 แปลงเป็นโค้ดหน้าตาประมาณไหน
dev ปรับสถาปัตยกรรม / DB / framework ได้ตามสะดวก ขอแค่ rule ตรงตามสเปค

ตัวเลข/น้ำหนักทุกตัวมี rule ID กำกับ -> เปิดดูรายละเอียดใน STEP ไฟล์นั้นได้
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import requests


# ==========================================================================
# [1] ดึงข่าวจาก Cafe Invest API              (สเปค: STEP2 ชีต API Spec)
# ==========================================================================

API_BASE = "https://www.innovestx.co.th/cafeinvest/api/cafe/v1/content/search"


def fetch_articles(category_slug=None, sub_category_slug=None, limit=100, page=1):
    """ดึงบทความจาก public API (ไม่ต้อง auth)

    ห้าม scrape HTML และห้ามใช้ sitemap — sitemap มีบทความแค่ 27%
    และ lastmod ถูก regenerate ทำให้หา 'ของใหม่' ไม่ได้
    """
    params = {
        "lang": "THA",
        "user_type": "visitor",
        "content_type": "article",
        "limit": limit,
        "page": page,
    }
    if category_slug:
        params["category_slug"] = category_slug
    if sub_category_slug:
        params["sub_category_slug"] = sub_category_slug

    r = requests.get(API_BASE, params=params, timeout=30)
    r.raise_for_status()
    result = r.json()["result"]
    return result["data"], result["total"]


# หมวดที่เลิกผลิตแล้ว — อย่า ingest (STEP2)
DISCONTINUED = {
    "bitesforbreakfast", "bitesfordinner", "glb-morning", "kohsue",
    "invest-ideas/offshore-stock",
}


# ==========================================================================
# [2] แท็กข่าว — 23 field                                    (สเปค: STEP3)
# ==========================================================================

@dataclass
class Article:
    # กลุ่ม 1: ได้จาก API ตรงๆ (A-01..A-11)
    article_id: str
    record_type: str            # A-02  "article" | "segment" (Brief ซอยเป็นข้อ)
    title: str
    url: str
    summary: str
    trigger_at: datetime        # A-06  published_date -> ใช้หาของใหม่
    display_at: datetime        # A-07  displayed_date -> ใช้แสดงผลเท่านั้น (R3.15)
    pillar: str
    category: str
    subcategory: str            # A-10  ตัวกำหนด content_type/importance/urgency
    source: Optional[str]

    # กลุ่ม 2: แปลงจาก API (A-12..A-15)
    entity_raw: list = field(default_factory=list)   # เช่น "NYS/TSM.N", "EPG.BK"
    entity: list = field(default_factory=list)       # แปลงแล้ว: "TSM:xnys", "EPG"
    article_asset_class: Optional[str] = None        # จาก product_type
    content_type: Optional[str] = None               # จาก subcategory

    # กลุ่ม 3: ต้องสร้างเอง (A-16..A-23)
    entity_extracted: list = field(default_factory=list)
    entity_source: str = "none"        # api|url_slug|title|summary|html_body|none
    entity_confidence: str = "unknown" # confirmed|inferred|unknown
    sector: list = field(default_factory=list)   # หุ้นไทยเท่านั้น เฟสแรก
    macro_topic: list = field(default_factory=list)
    importance: int = 1                # A-21  1-5
    urgency: str = "low"               # A-22  now|this_week|low
    role: str = "content"              # A-23  content=ส่งได้ | reference=ป้อนระบบ


def tag_article(raw: dict) -> Article:
    """แปลง JSON จาก API เป็น Article ที่แท็กครบ

    หลักการ (STEP3):
      - ไม่มั่นใจ = ไม่แท็ก (ปล่อย unknown ได้ ห้ามเดา)
      - ทุก entity ต้องบอกที่มาเสมอ (entity_source)
      - ห้ามสร้างข้อมูลที่ไม่มีในต้นทาง
    """
    art = Article(
        article_id=str(raw["id"]),
        record_type="article",
        title=raw["title"],
        url=raw["url"],
        summary=raw.get("summary_plain", ""),
        trigger_at=_parse_dt(raw["published_date"]),
        display_at=_parse_dt(raw["displayed_date"]),
        pillar=raw.get("pillar", ""),
        category=raw.get("category", ""),
        subcategory=raw.get("sub_category", ""),
        source=raw.get("source"),
    )

    art.content_type = CONTENT_TYPE_BY_SUBCATEGORY.get(art.subcategory, "unknown")
    art.importance = IMPORTANCE_BY_CONTENT_TYPE.get(art.content_type, 1)   # A-21
    art.urgency = URGENCY_BY_CONTENT_TYPE.get(art.content_type, "low")     # A-22

    # --- entity: ลองตามลำดับความน่าเชื่อถือ ---
    art.entity_raw = [s.get("symbol") for s in raw.get("stock", []) if s.get("symbol")]
    if art.entity_raw:
        art.entity = [normalize_ticker(t) for t in art.entity_raw]
        art.entity_source = "api"
        art.entity_confidence = "confirmed"          # ใช้จับคู่ได้เลย
    else:
        # หมวดที่ stock ว่าง เช่น Top Picks -> ticker ฝังใน url slug
        # ตย. thaistocktoppicks-kkp-20260721 -> KKP
        extracted = extract_ticker_from_slug(art.url) or extract_ticker_from_title(art.title)
        if extracted:
            art.entity_extracted = extracted
            art.entity = [normalize_ticker(t) for t in extracted]
            art.entity_source = "url_slug"
            art.entity_confidence = "inferred"       # ** ต้องมีคนตรวจก่อนใช้จริง **

    # --- sector: หุ้นไทยเท่านั้น จาก Thai Stock Coverage List (97 ตัว) ---
    art.sector = [SECTOR_BY_TICKER[t] for t in art.entity if t in SECTOR_BY_TICKER]

    # --- macro_topic: R3.37/R3.38 ---
    art.macro_topic = detect_macro_topics(art.title + " " + art.summary)

    return art


def detect_macro_topics(text: str) -> list:
    """หา macro topic จากคำค้น

    !! ภาษาไทยไม่เว้นวรรค — ห้ามใช้คำสั้น (R3.37) !!
    ทดสอบแล้ว: "ยา" ไป match "อย่าง"/"ยาว" -> 35% ของข่าวถูกแท็ก Healthcare ผิด
                "AI" match "THai"/"dAIly" | "EV" match "EVOlution" | "FIN" match "KFINdia"
    ใช้เฉพาะคำยาวเฉพาะเจาะจง และต้องผ่านชุดทดสอบตาม R3.38 ก่อนเพิ่มคำใหม่
    """
    hits = []
    for topic, keywords in MACRO_KEYWORDS.items():
        if any(kw in text for kw in keywords):   # keyword ต้องยาว >= เกณฑ์ R3.37
            hits.append(topic)
    return hits


# ==========================================================================
# [3] แปลงรหัส ticker ให้ตรงกัน 2 ฝั่ง                        (สเปค: STEP4)
# ==========================================================================

def normalize_ticker(raw: str) -> str:
    """แปลงรหัสฝั่งข่าว -> รูปแบบเดียวกับฝั่งลูกค้า

    ตัวอย่างที่ทดสอบกับ client book แล้ว:
        EPG.BK       -> EPG            (หุ้นไทย ตัด suffix)
        NYS/TSM.N    -> TSM:xnys       (US: venue -> MIC)
        NXB/COST.NB  -> COST:xnas
        0700.HK      -> 00700:xhkg     (HK: pad เป็น 5 หลัก)
        MC.FP        -> MC:xpar
        BTCUSD       -> BTC            (crypto ตัด USD)
        CPALLU26     -> CPALL          (single-stock futures -> underlying)
        CPALL293B    -> CPALL          (หุ้นกู้ -> ผู้ออก)
        S50U26       -> S50U26         (TFEX index ตรงอยู่แล้ว)

    ระวัง: บริษัทเดียวอาจ list หลายที่ (TSM.US และ 2330.TT) -> ถือเป็นคนละ instrument
    ระวัง: ฝั่งลูกค้าเองก็มีทั้ง "MC" และ "MC:xpar" ปนกัน -> ต้อง normalize สองฝั่ง

    กฎเต็ม 47 ข้อ (R4.1-R4.47) อยู่ใน STEP4 — A1-A6, B1(DR), B2(กองทุน), B3(sector)
    """
    raise NotImplementedError("implement ตามกฎ R4.1-R4.47 ใน STEP4")


def resolve_fund_underlying(product_code: str):
    """กองทุน -> underlying

    ปัญหา: product_name เป็น 'null' ทุกแถว (4,870 rows) และไม่มี fund master
    ทำได้แค่ infer จากรหัส เช่น SCBS&P500A -> S&P500
    coverage จริงที่ทดสอบแล้ว = 46.5% (ไม่มี false positive) อีก 54% แกะไม่ได้ -> unknown
    return (underlying, confidence)  # confidence: confirmed|inferred|unknown
    """
    raise NotImplementedError("implement ตามกฎ B2 ใน STEP4")


# ==========================================================================
# [4] คุณสมบัติลูกค้า + persona                              (สเปค: STEP5)
# ==========================================================================

@dataclass
class Customer:
    customer_key: str                  # masked แล้ว — ไม่มีชื่อ/เลขบัตรในระบบ
    rm_id: str                         # CF-10
    dominant_asset_class: str          # CF-01
    asset_mix: dict                    # CF-02  {asset_class: pct}
    sector_exposure: dict              # CF-03  {sector: pct}  (หุ้นไทยเท่านั้น)
    holdings: dict                     # CF-04  {ticker: มูลค่าถือ THB}
    watchlist: set                     # CF-05  เทรดใน 90 วันแต่ไม่ถือแล้ว
    trade_frequency: str               # CF-06  inactive|passive|active|very_active
    days_since_last_trade: int         # CF-07
    portfolio_value: float             # CF-08
    last_traded_at: dict               # {ticker: datetime}  ใช้คิด recency (R6.11)
    persona: str = ""


def build_customer_features(holdings_rows, txn_rows, as_of: datetime) -> Customer:
    """คำนวณ CF-01..CF-10 จาก Portfolio + TXN

    R1.17: สิ่งที่ลูกค้าถือ = HOLDINGS + TRANSACTIONS ที่เกิดหลัง as_of_date
           (ชดเชยกรณีลูกค้าซื้อของใหม่หลังวันทำ snapshot)
    R1.6:  แถวที่ product_code ว่าง ไม่ใช่การถือครอง -> ข้าม
           (TFEX ใน Portfolio เป็นยอดเงินในบัญชี ไม่ใช่สถานะ
            สถานะ TFEX ต้อง net Buy(Long) - Sell(Short) จาก txn)
    """
    raise NotImplementedError("implement ตาม CF-01..CF-10 ใน STEP5")


def assign_persona(c: Customer) -> str:
    """จัด persona — เรียงตามลำดับ ตัวแรกที่เข้าเงื่อนไขชนะ (R5.1-R5.4)"""
    if c.days_since_last_trade > 90 and c.trade_frequency == "inactive":
        return "DORMANT"                                    # R5.1

    ac = c.dominant_asset_class                             # R5.2
    if ac == "da":
        return "CRYPTO"
    if ac == "tfex":
        return "DERIVATIVES"
    if ac == "offshore":
        return "US_OFFSHORE"
    if ac == "stock":
        return "THAI_STOCK"
    if ac == "bond":
        return "BOND"
    if ac == "fund":                                        # R5.3
        robo = c.asset_mix.get("FUND_ROBO", 0)
        diy = c.asset_mix.get("FUND_DIY", 0)
        return "FUND_ROBO" if robo > diy else "FUND_DIY"
    return "NO_PORTFOLIO"
    # R5.4: persona ต้องคำนวณใหม่ทุกครั้งที่ข้อมูลอัปเดต ห้าม cache ข้ามรอบ


# ==========================================================================
# [5] จับคู่ L1-L6                                            (สเปค: STEP6)
# ==========================================================================

LEVEL_WEIGHT = {          # R6.1 - R6.6
    "L1_HOLD":     100,   # ถือตรงตัว
    "L2_WATCH":     60,   # เคยเทรดใน 90 วัน แต่ไม่ถือแล้ว
    "L3_SECTOR":    40,   # sector เดียวกัน (หุ้นไทยเท่านั้น)
    "L4_RELATED":   30,   # ตารางความสัมพันธ์หุ้น (R3.29-R3.36) ใช้กับหุ้นนอก
    "L5_ASSET":     20,   # asset class เดียวกัน
    "L6_MACRO":     10,   # ทุกคน ถ่วงตามความไวของพอร์ต
}

MIN_SECTOR_WEIGHT = 0.05   # R6.3 ต้องถือ sector นั้นมากพอ — ตั้งค่าได้


@dataclass
class Match:
    customer_key: str
    rm_id: str
    level: str
    matched_entity: str      # จับคู่เพราะตัวไหน  <- evidence
    reason: str              # จับคู่เพราะอะไร     <- evidence
    score: float = 0.0


def match_article(art: Article, customers: list, mode: str) -> list:
    """จับคู่ข่าว 1 ชิ้น -> ลูกค้าที่ควรติดต่อ

    mode: "realtime" (R6.12) จับถึง L2 เท่านั้น — แม่นสูง ส่งทันที
          "digest"   (R6.13) จับถึง L4 — กว้างได้ รวมส่งเช้า/เย็น
    """
    max_level = 2 if mode == "realtime" else 4
    matches = []

    for c in customers:
        # --- R6.16: กรอง persona ก่อนจับคู่ ---
        if not persona_accepts(c.persona, art):
            continue

        hits = []   # (level, entity, reason)

        # L1 ถือตรงตัว (R6.1)
        for e in art.entity:
            if e in c.holdings:
                hits.append(("L1_HOLD", e, f"ถือ {e} มูลค่า {c.holdings[e]:,.0f} บาท"))

        # L2 watchlist (R6.2)
        if max_level >= 2:
            for e in art.entity:
                if e in c.watchlist and e not in c.holdings:
                    hits.append(("L2_WATCH", e, f"เคยเทรด {e} ใน 90 วัน"))

        # L3 sector — หุ้นไทยเท่านั้น (R6.3)
        if max_level >= 3:
            for s in art.sector:
                if c.sector_exposure.get(s, 0) >= MIN_SECTOR_WEIGHT:
                    hits.append(("L3_SECTOR", s,
                                 f"ถือหุ้นกลุ่ม {s} {c.sector_exposure[s]:.0%}"))

        # L4 ความสัมพันธ์ — ใช้แทน L3 สำหรับหุ้นนอกที่ไม่มี sector (R6.4)
        if max_level >= 4:
            for e in art.entity:
                for rel in RELATED_STOCKS.get(e, []):
                    if rel in c.holdings:
                        hits.append(("L4_RELATED", rel, f"ถือ {rel} ซึ่งสัมพันธ์กับ {e}"))

        # L5 / L6 ใช้เฉพาะ digest ของข่าวภาพรวม (R6.5, R6.6)
        # ...

        if not hits:
            continue

        # ลูกค้าเข้าหลายระดับ -> ใช้ระดับสูงสุดเป็นฐาน + โบนัสถ้าแตะหลายจุด
        best = max(hits, key=lambda h: LEVEL_WEIGHT[h[0]])
        m = Match(c.customer_key, c.rm_id, best[0], best[1], best[2])
        m.score = compute_score(m, art, c, n_hits=len(hits))
        matches.append(m)

    # R6.14 ตัดที่เกณฑ์ขั้นต่ำ / R6.15 ไม่ cap แต่เรียงลำดับ
    matches = [m for m in matches if m.score >= SCORE_THRESHOLD]
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches


def compute_score(m: Match, art: Article, c: Customer, n_hits: int) -> float:
    """R6.7-R6.11

    score = น้ำหนักระดับ x มูลค่าถือ x importance x urgency x recency
    ทุกตัวเป็นข้อเท็จจริงที่ตรวจสอบได้ — ไม่มี sentiment (ตัดทิ้งตั้งแต่ STEP3)
    """
    base = LEVEL_WEIGHT[m.level]

    # R6.8 มูลค่าถือ — ใช้ log กันไม่ให้รายใหญ่กลบทุกคน (ปรับ curve ได้)
    value = c.holdings.get(m.matched_entity, 0)
    value_factor = 1 + _log_scale(value)

    # R6.9 importance 1-5 (A-21)
    importance_factor = art.importance / 3.0

    # R6.10 urgency (A-22)
    urgency_factor = {"now": 1.5, "this_week": 1.0, "low": 0.7}[art.urgency]

    # R6.11 recency — เพิ่งเทรดตัวนั้น = กำลังสนใจ
    last = c.last_traded_at.get(m.matched_entity)
    if last and (datetime.now() - last) <= timedelta(days=7):
        recency_factor = 1.3
    elif last and (datetime.now() - last) <= timedelta(days=30):
        recency_factor = 1.1
    else:
        recency_factor = 1.0

    multi_hit_bonus = 1 + 0.1 * (n_hits - 1)   # แตะหลายจุด = เกี่ยวมากกว่า

    return (base * value_factor * importance_factor
            * urgency_factor * recency_factor * multi_hit_bonus)


SCORE_THRESHOLD = 50   # R6.14 — ปรับได้ กันข่าว macro เหมาะกับ 1,107 คนแบบไร้ความหมาย


def persona_accepts(persona: str, art: Article) -> bool:
    """R6.16 — กรอง persona ก่อนจับคู่"""
    if persona == "DORMANT":
        return False                                   # ไม่ฝืนส่ง
    if persona == "FUND_ROBO":
        return art.content_type in ("REBALANCE_REPORT", "MONTHLY_REPORT")
    if persona == "NO_PORTFOLIO":
        return False
    return art.content_type in PERSONA_CONTENT_MAP.get(persona, set())


# ==========================================================================
# [6] Output — ส่งให้ RM                                      (สเปค: STEP7)
# ==========================================================================

def build_rm_payload(art: Article, matches: list) -> dict:
    """จัดกลุ่มผลลัพธ์ตาม RM แต่ละคน

    ระบบทำงานบน customer_key ที่ mask แล้วทั้งหมด
    การแปลงกลับเป็นตัวตนจริง ทำที่ฝั่ง CRM/RM เท่านั้น — ระบบนี้ไม่เห็นตารางแปลงกลับ
    """
    by_rm = {}
    for m in matches:
        by_rm.setdefault(m.rm_id, []).append({
            "customer_key": m.customer_key,
            "level": m.level,
            "score": round(m.score, 1),
            "why": m.reason,            # RM ต้องเห็นเหตุผลเสมอ
            "entity": m.matched_entity,
        })
    return {
        "article_id": art.article_id,
        "title": art.title,
        "url": art.url,
        "urgency": art.urgency,
        "importance": art.importance,
        "rm_lists": by_rm,
    }


# ==========================================================================
# [7] Unknown / Exception                                     (สเปค: STEP8)
# ==========================================================================

def report_unmapped(unmapped_entities, unmapped_products):
    """ไม่มั่นใจ = ไม่จับคู่ แต่ต้องออกรายงานเสมอ ห้ามเงียบ

    รายงานที่ต้องมี (STEP8):
      1. entity ในข่าวที่แปลงรหัสไม่ได้
      2. product_code ฝั่งลูกค้าที่ไม่รู้จัก
      3. entity ที่ confidence = inferred และยังไม่มีคนตรวจ
      4. ข่าวที่จับคู่ไม่ได้เลยสักคน
    """
    raise NotImplementedError("implement ตาม STEP8")


# ==========================================================================
# main
# ==========================================================================

def run_realtime(article_raw: dict, customers: list):
    art = tag_article(article_raw)

    if art.role == "reference":       # A-23: reference = ป้อนระบบเท่านั้น ไม่ส่ง
        return None
    if art.entity_confidence == "inferred" and not is_human_verified(art):
        return None                   # inferred ต้องผ่านคนตรวจก่อน (STEP3/STEP8)

    matches = match_article(art, customers, mode="realtime")
    if not matches:
        return None                   # ไม่มีคนเหมาะ = ไม่ส่ง ไม่ฝืน
    return build_rm_payload(art, matches)


# --- ตารางอ้างอิงที่ต้องเติมจากสเปค (ห้าม hardcode มั่ว) ---
CONTENT_TYPE_BY_SUBCATEGORY = {}   # STEP3 ชีต content_type
                                   # R3.16: เจอ subcategory ที่ไม่รู้จัก ต้องหยุด+รายงาน ห้ามเดา
IMPORTANCE_BY_CONTENT_TYPE = {}    # STEP3 A-21
URGENCY_BY_CONTENT_TYPE = {}       # STEP3 A-22
MACRO_KEYWORDS = {}                # STEP3 R3.37-R3.40 — คำยาวเท่านั้น
SECTOR_BY_TICKER = {}              # STEP4 B3 — Thai Stock Coverage List 97 ตัว
RELATED_STOCKS = {}                # STEP3 R3.29-R3.36 — ตารางความสัมพันธ์
PERSONA_CONTENT_MAP = {}           # STEP5/STEP6 ชีต Persona กับข่าว


def _parse_dt(s): raise NotImplementedError
def _log_scale(v): raise NotImplementedError
def extract_ticker_from_slug(url): raise NotImplementedError
def extract_ticker_from_title(t): raise NotImplementedError
def is_human_verified(art): raise NotImplementedError
