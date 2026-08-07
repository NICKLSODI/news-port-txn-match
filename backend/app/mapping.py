# -*- coding: utf-8 -*-
"""STEP4 — Instrument Mapping & Normalization (R4.1 - R4.47)

แปลงรหัสสินทรัพย์ทั้งฝั่งข่าวและฝั่งลูกค้าให้เป็น "รหัสกลาง" เดียวกัน
รหัสกลาง:
    หุ้นไทย / คริปโต / กองทุน / ผู้ออกหุ้นกู้   ->  ตัวย่อล้วน            เช่น SCB, BTC, SCBS&P500A
    หุ้นต่างประเทศ                             ->  TICKER:mic (พิมพ์เล็ก)  เช่น NVDA:xnas, 00700:xhkg

หลักการ (R4.34 / R4.35): ไม่เข้ากฎใด หรือแปลงแล้วไม่พบของจริง -> unmapped + รายงาน ห้ามเดา
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .tables import (
    BLOOMBERG_COUNTRY,
    DR_ISSUER_SUFFIXES,
    US_MICS,
    OFFSHORE_FUND_SUFFIX,
    OFFSHORE_SECTOR,
    OPTIONS_MIC,
    PAD5_MIC,
    SUFFIX_TO_MIC,
    SUFFIX_UNSUPPORTED,
    THAI_SUFFIX,
    TFEX_MONTH_CODES,
    VENUE_PREFIXES,
)

REFDATA = Path(__file__).parent / "refdata" / "generated.json"


@lru_cache(maxsize=1)
def refdata() -> dict:
    return json.loads(REFDATA.read_text(encoding="utf-8"))


# ==========================================================================
# ผลการแปลง
# ==========================================================================

@dataclass
class MapResult:
    entity: str | None = None            # รหัสกลาง — None = unmapped
    confidence: str = "unknown"          # confirmed | inferred | unknown
    rule: str = ""                       # เลขกฎที่ใช้ เพื่ออ้างหลักฐาน
    kind: str = ""                       # stock | crypto | fund | bond | tfex | options | dr | kiko
    note: str = ""
    raw: str = ""
    instrument_label: str = ""           # ป้ายเตือน RM (R3.27, R4.12, R4.22, R4.28, R4.31)

    @property
    def ok(self) -> bool:
        return bool(self.entity)


# ==========================================================================
# ตัวช่วย
# ==========================================================================

def canon_mic(mic: str) -> str:
    """R1.2 — MIC ในไฟล์ลูกค้าปนทั้งพิมพ์เล็กพิมพ์ใหญ่ (xnas กับ XTKS) รวมเป็นพิมพ์เล็ก"""
    return mic.strip().lower()


def pad_ticker(ticker: str, mic: str) -> str:
    """R4.6 — ฮ่องกงเติมศูนย์ข้างหน้าให้ครบ 5 หลัก"""
    if mic in PAD5_MIC and ticker.isdigit():
        return ticker.zfill(5)
    return ticker


def offshore_id(ticker: str, mic: str) -> str:
    mic = canon_mic(mic)
    return f"{pad_ticker(ticker.upper(), mic)}:{mic}"


def strip_venue(code: str) -> str:
    """R4.1 — ตัด venue prefix หน้าเครื่องหมายทับ  NXB/AMD.NB -> AMD.NB"""
    if "/" in code:
        head, rest = code.split("/", 1)
        if head.upper() in VENUE_PREFIXES:
            return rest
    return code


# ==========================================================================
# จักรวาลสินทรัพย์ของลูกค้า — ใช้ตรวจว่ารหัสที่แปลงแล้วมีของจริงหรือไม่ (R3.24)
# ==========================================================================

@dataclass
class Universe:
    """ดัชนีรหัสสินทรัพย์ที่ลูกค้าถือ/เทรดจริง

    ใช้ 2 อย่าง:
      1. R3.24 — ตรวจว่ารหัสที่แปลงจากข่าวมีคนถือไหม (ไม่มี = ปกติ ไม่ใช่ error)
      2. คลี่ underlying ที่ไม่มี MIC (Options / DR / TFEX) ให้เป็นรหัสกลาง
         ถ้า root เดียวชี้ได้หลายตลาด = กำกวม -> unmapped (spec เตือนเรื่อง cross-listing)
    """
    ids: set[str] = field(default_factory=set)
    by_root: dict[str, set[str]] = field(default_factory=dict)

    def add(self, entity: str) -> None:
        self.ids.add(entity)
        root = entity.split(":", 1)[0]
        self.by_root.setdefault(root, set()).add(entity)

    def resolve_root(self, root: str, prefer_mics: tuple[str, ...] = ()) -> tuple[str | None, str]:
        """หา รหัสกลาง จาก root ที่ไม่มี MIC

        prefer_mics — จำกัดตลาดที่ยอมรับก่อน ใช้ตัดกรณีบริษัทเดียว list หลายที่
        """
        root = root.upper()
        if not prefer_mics and root in self.ids:  # หุ้นไทย/คริปโต/กองทุน — root คือรหัสกลางอยู่แล้ว
            return root, ""
        cand = self.by_root.get(root, set())
        if prefer_mics:
            # จำกัดเฉพาะตลาดที่ยอมรับ — ถ้าไม่มีเลย ถือว่าไม่พบ ห้ามตกไปใช้ตลาดอื่น
            # (VNM VN คือ Vinamilk เวียดนาม ไม่ใช่ VNM:bats ซึ่งเป็น ETF สหรัฐ)
            cand = {c for c in cand if ":" in c and c.rsplit(":", 1)[1] in prefer_mics}
            if not cand:
                return None, f"ไม่พบ {root} ในตลาด {prefer_mics}"
        if len(cand) == 1:
            return next(iter(cand)), ""
        if len(cand) > 1:
            return None, f"กำกวม — {root} พบใน {len(cand)} ตลาด: {sorted(cand)}"
        return None, f"ไม่พบ {root} ในรายการสินทรัพย์ของลูกค้า"

    def __contains__(self, entity: str) -> bool:
        return entity in self.ids


EMPTY_UNIVERSE = Universe()


# ==========================================================================
# ฝั่งลูกค้า — product_code -> รหัสกลาง
# ==========================================================================

DRX_RE = re.compile(r"^([A-Z0-9&.\-]+?)(\d{2})x\.BK$", re.I)          # R4.14  SPACEX23x.BK
DR80_RE = re.compile(r"^([A-Z][A-Z0-9&.\-]*?)(" + "|".join(sorted(DR_ISSUER_SUFFIXES)) + r")$")
TFEX_RE = re.compile(r"^([A-Z0-9&.\-]+?)([FGHJKMNQUVXZ])(\d{2})X?$")   # R4.18-R4.20
OPTION_RE = re.compile(r"^([A-Z0-9._\-]+)/\S+:" + OPTIONS_MIC + r"$", re.I)  # R4.29
BOND_TH_RE = re.compile(r"^([A-Z][A-Z&.\-]{1,})\d{2}[A-Z0-9]{1,3}$")   # R4.10  CPALL293B
KIKO_RE = re.compile(r"^([A-Z][A-Z0-9&.\-]*)\s+KIKO\b", re.I)          # GAP-05
BLOOMBERG_RE = re.compile(r"^([A-Z0-9][A-Z0-9&\-]*)[ .]([A-Z]{2})$")   # GAP-15  "ACV VN" / "7974.JP"


def map_holding(product_code: str | None, asset_class: str,
                universe: Universe = EMPTY_UNIVERSE) -> MapResult:
    """แปลง product_code ฝั่งลูกค้า -> รหัสกลาง

    universe ใช้เฉพาะตอนคลี่ underlying (Options/DR/TFEX) — pass 1 เรียกโดยไม่ต้องมีก็ได้
    """
    raw = (product_code or "").strip()
    if not raw or raw.lower() == "null":
        # R1.6 — แถวที่ product_code ว่าง (TFEX) = ยอดเงินในบัญชี ไม่ใช่การถือครอง
        return MapResult(rule="R1.6", note="product_code ว่าง — ไม่ใช่การถือครอง", raw=raw)

    # --- Options ต่างประเทศ (R4.29 - R4.31) ---
    m = OPTION_RE.match(raw)
    if m:
        root = m.group(1).upper().removesuffix("_US")          # R4.30
        # options CBOE อ้างอิงหุ้นที่ list ในสหรัฐเสมอ ใช้ตัดกรณีชนข้ามตลาด
        ent, why = universe.resolve_root(root, US_MICS)
        if ent:
            return MapResult(ent, "confirmed", "R4.30/R4.31", "options", raw=raw,
                             instrument_label="options")
        return MapResult(rule="R4.30", kind="options", raw=raw,
                         note=why or f"ถอด underlying {root} ได้ แต่คลี่รหัสกลางไม่ได้")

    # --- กองทุนต่างประเทศ .MFU (GAP-04 — spec ไม่มีกฎ) ---
    if raw.upper().endswith("." + OFFSHORE_FUND_SUFFIX):
        return MapResult(raw.upper().removesuffix("." + OFFSHORE_FUND_SUFFIX),
                         "inferred", "GAP-04", "fund", raw=raw,
                         note="ตัด .MFU — ไม่มีกฎใน STEP4")

    # --- หุ้นต่างประเทศที่มา MIC พร้อมแล้ว  NVDA:xnas ---
    if ":" in raw:
        tic, mic = raw.rsplit(":", 1)
        return MapResult(offshore_id(tic, mic), "confirmed", "R1.2", "stock", raw=raw)

    # --- รหัสแบบ Bloomberg "ACV VN" / "7974.JP" (GAP-15 / R1.2) ---
    m = BLOOMBERG_RE.match(raw)
    if m and m.group(2).upper() in BLOOMBERG_COUNTRY:
        root, cc = m.group(1).upper(), m.group(2).upper()
        mics = BLOOMBERG_COUNTRY[cc]
        ent, why = universe.resolve_root(root, mics)
        if ent:
            return MapResult(ent, "confirmed", "GAP-15/R1.2", "stock", raw=raw,
                             note=f"รหัสแบบ Bloomberg ({cc}) — รวมกับ {ent} ตาม R1.2")
        # ไม่มีตัวเดียวกันในรูปแบบ MIC ให้อ้างอิง -> สร้างรหัสกลางจากตลาดเดียวที่รหัสประเทศชี้ได้
        if len(mics) == 1:
            return MapResult(offshore_id(root, mics[0]), "inferred", "GAP-15", "stock", raw=raw,
                             note=f"รหัสแบบ Bloomberg ({cc}) ไม่พบคู่ในพอร์ต — ตั้งเป็น {mics[0]}")
        return MapResult(rule="GAP-15", kind="stock", raw=raw,
                         note=why or f"รหัสประเทศ {cc} ชี้ได้หลายตลาด: {mics}")

    # --- KIKO (GAP-05) ---
    m = KIKO_RE.match(raw)
    if m:
        ent, why = universe.resolve_root(m.group(1))
        ent = ent or m.group(1).upper()
        return MapResult(ent, "inferred", "GAP-05", "kiko", raw=raw,
                         instrument_label="kiko", note=why)

    # --- หุ้นกู้ไทย -> บริษัทผู้ออก (R4.10 - R4.13) ---
    if asset_class == "BOND_TH":
        issuer = refdata()["bond_issuer"].get(raw)
        if not issuer:
            m = BOND_TH_RE.match(raw)
            issuer = m.group(1) if m else None
        if issuer:
            return MapResult(issuer.upper(), "confirmed", "R4.10", "bond", raw=raw,
                             instrument_label="bond")
        return MapResult(rule="R4.10", kind="bond", raw=raw, note="ถอดผู้ออกไม่ได้")

    # --- ตราสารหนี้ต่างประเทศ — ไม่มีเนื้อหารองรับเลย (STEP2 ช่องว่าง 7) ---
    if asset_class == "BOND_OFFSHORE":
        return MapResult(rule="STEP2-GAP", kind="bond", raw=raw,
                         note="ตราสารหนี้ต่างประเทศ ไม่มีเนื้อหารองรับ")

    # --- กองทุนไทย (DIY / ROBO) — รหัสกองคือรหัสกลาง ---
    if asset_class in ("FUND_DIY", "FUND_ROBO"):
        return MapResult(raw.upper(), "confirmed", "R4.36", "fund", raw=raw)

    # --- คริปโต (R4.8 / R4.9) ---
    if asset_class == "DIGITAL_ASSET":
        code = raw.upper()
        if code.endswith("USD") and code != "USD" and len(code) > 3 and code != "USDT":
            code = code[:-3]
        return MapResult(code, "confirmed", "R4.8", "crypto", raw=raw)

    # --- หุ้นไทย: อาจเป็น DR ที่เทรดในไทย (R4.17 / R4.24 - R4.28) ---
    if asset_class in ("EQUITY_TH", "STRUCTURED_NOTE"):
        dr = refdata()["dr_parent"].get(raw)
        if dr:
            parent = dr["parent"]
            ent = offshore_id(*parent.rsplit(":", 1)) if ":" in parent else parent.upper()
            return MapResult(ent, "inferred", "R4.24/R4.27", "dr", raw=raw,
                             instrument_label="dr",
                             note=f"DR อ้างอิง {parent} (ที่มา {dr['source']})")
        if raw in refdata()["dr_names"]:
            return MapResult(rule="R4.27", kind="dr", raw=raw,
                             note="เป็น DR แต่ยังไม่มีในตารางชื่อพ้อง")
        m = DR80_RE.match(raw)
        if m and m.group(1) not in refdata()["thai_sector"]:
            root = m.group(1)
            ent, why = universe.resolve_root(root)
            if ent:
                return MapResult(ent, "inferred", "R4.24", "dr", raw=raw,
                                 instrument_label="dr", note=f"ถอดเลขผู้ออก -> {root}")
        return MapResult(raw.upper(), "confirmed", "R4.2/R4.4", "stock", raw=raw)

    # --- TFEX ที่มาจากฝั่งธุรกรรม (R4.18 - R4.22) ---
    if asset_class == "TFEX":
        return map_tfex(raw, universe)

    if asset_class == "OPTIONS_OFFSHORE":
        return MapResult(rule="R4.29", kind="options", raw=raw, note="รูปแบบ options ไม่ตรงกฎ")

    return MapResult(rule="R4.34", raw=raw, note=f"asset_class {asset_class} ไม่มีกฎรองรับ")


def map_tfex(raw: str, universe: Universe = EMPTY_UNIVERSE) -> MapResult:
    """R4.18 - R4.23 — ถอด underlying ของสัญญา TFEX"""
    code = raw.strip().upper()
    if re.search(r"[CP]\d{3,}$", code):
        # R4.23 — Options ปนอยู่ใน TFEX เช่น S50H26P900 ยังไม่รองรับ
        return MapResult(rule="R4.23", kind="tfex", raw=raw,
                         note="เป็น options ของ TFEX — ยังไม่มีกฎ")
    m = TFEX_RE.match(code)
    if not m:
        return MapResult(rule="R4.18", kind="tfex", raw=raw, note="รูปแบบสัญญาไม่ตรงกฎ")
    root, mon, yr = m.group(1), m.group(2), m.group(3)
    info = refdata()["tfex_underlying"].get(root)
    expiry = (2000 + int(yr), TFEX_MONTH_CODES[mon])
    if info and info["kind"] == "index":
        # ดัชนี/สินค้า (S50, GO, USD, SVF) ไม่มีหุ้นให้จับคู่ตรงตัว
        return MapResult(root, "confirmed", "R4.18", "tfex", raw=raw,
                         instrument_label="tfex_index",
                         note=f"{info['name']} หมดอายุ {expiry[1]:02d}/{expiry[0]}")
    ent, why = universe.resolve_root(root)
    ent = ent or root
    return MapResult(ent, "confirmed", "R4.18/R4.22", "tfex", raw=raw,
                     instrument_label="tfex",
                     note=f"underlying {root} หมดอายุ {expiry[1]:02d}/{expiry[0]}" +
                          (f" | {why}" if why else ""))


def tfex_expiry(raw: str) -> tuple[int, int] | None:
    """R4.21 / R1.11 — ปีเดือนหมดอายุจากรหัสสัญญา"""
    m = TFEX_RE.match(raw.strip().upper())
    if not m:
        return None
    return 2000 + int(m.group(3)), TFEX_MONTH_CODES[m.group(2)]


# ==========================================================================
# ฝั่งข่าว — stock.name -> รหัสกลาง (R4.33 ลำดับการใช้กฎ)
# ==========================================================================

def map_news_symbol(symbol: str, universe: Universe = EMPTY_UNIVERSE) -> MapResult:
    """แปลงรหัสหุ้นที่ API ส่งมา -> รหัสกลาง

    ลำดับตาม R4.33 เท่านั้น: venue prefix -> options -> DRx -> หุ้นไทย -> หุ้นนอก -> คริปโต
    """
    raw = (symbol or "").strip()
    if not raw:
        return MapResult(rule="R3.22", note="รหัสว่าง")

    code = strip_venue(raw)                                        # 1. R4.1

    if code.lower().endswith(":" + OPTIONS_MIC):                   # 2. options
        return map_holding(code, "OPTIONS_OFFSHORE", universe)

    m = DRX_RE.match(code)                                         # 3. R4.14 DRx (ก่อน A1!)
    if m:
        name = m.group(1).upper()
        dr_code = code.upper()
        hit = refdata()["dr_parent"].get(dr_code)
        parent = hit["parent"] if hit else None
        if not parent:
            from .tables import DR_NAME_ALIAS
            parent = DR_NAME_ALIAS.get(name)
        if not parent:
            ent, why = universe.resolve_root(name)
            parent = ent
        if parent:
            ent = offshore_id(*parent.rsplit(":", 1)) if ":" in parent else parent.upper()
            return MapResult(ent, "inferred", "R4.14/R4.15", "dr", raw=raw,
                             instrument_label="dr", note=f"DR {code} -> {parent}")
        return MapResult(rule="R4.15", kind="dr", raw=raw,
                         note=f"DR {code} ไม่มีในตารางชื่อพ้อง")

    if "." in code:
        ticker, suffix = code.rsplit(".", 1)
        suf = suffix.upper()

        if suf == THAI_SUFFIX:                                     # 4. R4.2 - R4.4 หุ้นไทย
            # R4.3 ตัดตัวพิมพ์เล็กต่อท้าย  DIFu.BK -> DIF   (R4.4 ห้ามตัดตัวเลข)
            base = re.sub(r"[a-z]+$", "", ticker)
            base = (base or ticker).upper()
            dr = refdata()["dr_parent"].get(base)
            if dr:
                parent = dr["parent"]
                ent = offshore_id(*parent.rsplit(":", 1)) if ":" in parent else parent.upper()
                return MapResult(ent, "inferred", "R4.24", "dr", raw=raw,
                                 instrument_label="dr", note=f"DR -> {parent}")
            return MapResult(base, "confirmed", "R4.2", "stock", raw=raw)

        if suf in SUFFIX_UNSUPPORTED:                               # R4.7
            return MapResult(rule="R4.7", raw=raw,
                             note=f"suffix .{suf} (Chi-X) ยังไม่รองรับ")

        if suf in SUFFIX_TO_MIC:                                    # 5. R4.5 / R4.6 หุ้นนอก
            return MapResult(offshore_id(ticker, SUFFIX_TO_MIC[suf]),
                             "confirmed", "R4.5", "stock", raw=raw)

        return MapResult(rule="R3.23", raw=raw,
                         note=f"suffix .{suf} ไม่อยู่ในตาราง — ต้องเพิ่มกฎก่อนใช้")

    up = code.upper()
    if up.endswith("USD") and len(up) > 3 and up != "USDT":         # 6. R4.8 คริปโต
        return MapResult(up[:-3], "confirmed", "R4.8", "crypto", raw=raw)

    if up in refdata()["thai_sector"]:                              # หุ้นไทยที่ไม่มี suffix
        return MapResult(up, "confirmed", "R4.2", "stock", raw=raw)

    ent, why = universe.resolve_root(up)
    if ent:
        return MapResult(ent, "inferred", "R3.24", "stock", raw=raw,
                         note=f"ไม่มี suffix — คลี่จากพอร์ตได้ {ent}")

    # R3.22 / R4.35 — ไม่เข้ากฎใดเลย
    return MapResult(rule="R4.35", raw=raw, note=why or "ไม่มี suffix และไม่รู้จักรหัส")


# ==========================================================================
# sector (B3) / ความสัมพันธ์หุ้น (C2)
# ==========================================================================

def sector_of(entity: str) -> str | None:
    """R3.12 / B3 — sector ของหุ้นไทย (Coverage List) + หุ้นต่างประเทศที่คนอนุมัติแล้ว

    หุ้นนอกไม่มีไฟล์ spec ต้นทางให้ดึง (Coverage List คุมแค่หุ้นไทย 97 ตัว) จึงมาจาก
    overrides.offshore_sector() — ของที่คนอนุมัติ ไม่ใช่กฎในโค้ด เหมือน sector_keyword
    ไม่ครบทุกตัวเป็นเรื่องปกติ (เหมือน Coverage List เอง) — ตัวที่ไม่มีคืน None ตามหลัก
    "ไม่มั่นใจ ไม่เดา" ไม่ใช่ตัดสิทธิ์การจับคู่ระดับอื่น (L1/L2 ยังทำงานตามปกติ)
    """
    hit = refdata()["thai_sector"].get(entity)
    if hit:
        return hit["sector"]
    return OFFSHORE_SECTOR.get(entity)


def coverage_of(entity: str) -> dict | None:
    """Rating / Target Price / ESG จาก Thai Stock Coverage List"""
    return refdata()["thai_sector"].get(entity)


@lru_cache(maxsize=1)
def related_map() -> dict[str, set[str]]:
    """C2 / R3.29 - R3.36 — หุ้นที่สัมพันธ์กัน (จับคู่ระดับรอง L4)

    seed จาก 6 กลุ่มที่พิสูจน์แล้วจาก 400 บทความ
    runtime จะโตขึ้นเองจาก co-mention ของบทความที่ ingest เข้ามา (ดู news.py)
    """
    out: dict[str, set[str]] = {}
    for grp in refdata()["related_groups"]:
        members = [m.upper() for m in grp["members"]]
        for a in members:
            out.setdefault(a, set()).update(x for x in members if x != a)
    return out
