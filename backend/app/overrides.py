# -*- coding: utf-8 -*-
"""ของที่คนอนุมัติแล้ว — เติมช่องว่างที่ spec ไม่ได้ครอบคลุม

ทำไมต้องมีไฟล์นี้แยก
--------------------
`refdata/generated.json` สร้างจากไฟล์ spec ล้วน ห้ามแก้มือ (build ทับทุกครั้ง)
ส่วน `tables.py` เป็น "กฎ" ที่ต้องรีวิวในโค้ด ไม่ควรโตขึ้นทุกครั้งที่เจอ DR ตัวใหม่

ไฟล์นี้คือชั้นที่สาม: **ข้อมูลที่คนตัดสินใจแล้ว** เช่น DR ตัวนี้อ้างอิงหุ้นตัวไหน
หมวดใหม่ควรจัดเป็น content_type อะไร แต่ละแถวเก็บว่าใครรับ เมื่อไหร่ และมาจากไหน

ที่สำคัญ: runtime ยังคงเป็นกฎล้วน ไฟล์นี้ถูกอ่านตอน import แล้วแช่แข็ง
ตัวเสนอ (scripts/propose.py) เขียนลง proposals/ ไม่ได้แตะไฟล์นี้
มีแต่ scripts/approve.py ที่คนสั่งเองเท่านั้นที่เขียนได้ (GAP-21 ยกประตูคนออกจาก
การจับคู่รายวัน ไม่ได้ห้ามมีคนตรวจตารางอ้างอิงตอน setup)
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).parent / "refdata" / "overrides.json"

SECTIONS = ("dr_alias", "subcategory", "sector_keyword", "macro_keyword", "offshore_sector")


@lru_cache(maxsize=1)
def load() -> dict:
    """อ่านไฟล์ครั้งเดียว — ไม่มีไฟล์ = ไม่มี override ไม่ใช่ error"""
    if not PATH.exists():
        return {k: {} for k in SECTIONS}
    try:
        raw = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {k: {} for k in SECTIONS}
    return {k: dict(raw.get(k) or {}) for k in SECTIONS}


def save(data: dict) -> None:
    """เขียนกลับ — เรียกจาก scripts/approve.py เท่านั้น"""
    PATH.parent.mkdir(parents=True, exist_ok=True)
    out = {k: data.get(k) or {} for k in SECTIONS}
    PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    load.cache_clear()


# --------------------------------------------------------------------------
# ตัวอ่านรายหมวด — คืนเฉพาะค่าที่ใช้จริง ตัด provenance ออก
# --------------------------------------------------------------------------

def dr_alias() -> dict[str, str]:
    """ชื่อ DR (ตัวพิมพ์ใหญ่) -> รหัสหุ้นแม่  {"BRKB": "BRK.B:xnys"}"""
    return {k.upper(): v["parent"] for k, v in load()["dr_alias"].items()
            if isinstance(v, dict) and v.get("parent")}


def subcategory() -> dict[str, dict]:
    """slug -> {content_type, importance, urgency}"""
    out = {}
    for slug, v in load()["subcategory"].items():
        if isinstance(v, dict) and v.get("content_type"):
            out[slug] = v
    return out


def sector_keyword() -> dict[str, str]:
    """คำไทยในหัวข้อ -> ชื่อ sector"""
    return {k: v["sector"] for k, v in load()["sector_keyword"].items()
            if isinstance(v, dict) and v.get("sector")}


def offshore_sector() -> dict[str, str]:
    """entity หุ้นต่างประเทศ (TICKER:MIC) -> sector — ขยาย R3.12/B3 ให้ครอบคลุมหุ้นนอก

    ไม่มีไฟล์ spec ต้นทางให้ดึงแบบ Thai Stock Coverage List (นั่นคุมแค่หุ้นไทย 97 ตัว)
    จึงเป็นของที่คนอนุมัติเหมือน dr_alias/sector_keyword ไม่ใช่กฎในโค้ด — ดูชุดตั้งต้นที่
    scripts/seed_offshore_sector.py เหมือน Coverage List เอง ไม่จำเป็นต้องครบทุกตัว
    เพิ่มได้เรื่อย ๆ ตามหุ้นที่ข่าวพูดถึงจริง
    """
    return {k: v["sector"] for k, v in load()["offshore_sector"].items()
            if isinstance(v, dict) and v.get("sector")}


def macro_keyword() -> dict[str, list[str]]:
    """ประเด็น macro -> คำค้นที่เพิ่มเข้าไป"""
    return {k: list(v["words"]) for k, v in load()["macro_keyword"].items()
            if isinstance(v, dict) and v.get("words")}


def summary() -> dict[str, int]:
    d = load()
    return {k: len(d[k]) for k in SECTIONS}
