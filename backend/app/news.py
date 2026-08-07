# -*- coding: utf-8 -*-
"""STEP2 + STEP3 — ดึงบทความจาก Cafe Invest API แล้วแท็ก 23 field

R2.5 - R2.9  กฎการเรียก API เชิงป้องกัน
R3.1 - R3.40 กฎการแท็ก
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from typing import Iterable

import requests

from . import db
from .mapping import Universe, map_news_symbol, map_tfex, refdata, sector_of
from .verify import grade, regrade
from .tables import (
    RETENTION_DAYS,
    ARTICLE_ASSET_CLASS_MAP,
    ASSET_CLASS_OVERRIDE_BY_SUBCATEGORY,
    CONTENT_TYPE_BY_SUBCATEGORY,
    DISCONTINUED_SUBCATEGORIES,
    IMPORTANCE_BY_CONTENT_TYPE,
    IMPORTANCE_BY_SUBCATEGORY,
    OUT_OF_SCOPE_SUBCATEGORIES,
    PRODUCT_TYPE_BLOCKED_SUBCATEGORIES,
    REALTIME_CONTENT_TYPES,
    REFERENCE_SUBCATEGORIES,
    SEGMENT_MAX,
    SEGMENT_MIN,
    SECTOR_BY_THAI_KEYWORD,
    SECTOR_KEYWORD_SUBCATEGORIES,
    SEGMENTED_SUBCATEGORIES,
    SUMMARY_CONFIRMED_SUBCATEGORIES,
    TFEX_SUBCATEGORIES,
    URGENCY_BY_CONTENT_TYPE,
    URGENCY_BY_SUBCATEGORY,
)
from . import overrides as _ov

SITE_BASE = "https://www.innovestx.co.th/cafeinvest"
API = f"{SITE_BASE}/api/cafe/v1/content/search"


def article_url(path: str | None) -> str:
    """URL เต็มของบทความบนเว็บจริง

    field url ที่ API ส่งมาเป็น path ที่ตัด /cafeinvest ออกแล้ว
    เช่น /strategy-insight/stock-strategy/offshore-stock-update/xxx-20260731
    ถ้าเอาไปต่อกับโดเมนตรง ๆ จะได้ 404 ทุกอัน ต้องเติม /cafeinvest กลับเข้าไป
    """
    p = (path or "").strip()
    if not p:
        return ""
    if p.startswith("http://") or p.startswith("https://"):
        return p
    return f"{SITE_BASE}/{p.lstrip('/')}"

# GAP-06 — API ตอบ 403 ถ้าไม่ส่ง User-Agent (spec ไม่ได้ระบุ)
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Referer": "https://www.innovestx.co.th/cafeinvest",
}
REQUIRED_FIELDS = ("id", "title", "url", "published_date", "category", "sub_category")
RATE_LIMIT_SECONDS = 0.4          # R2.6 — จำกัดอัตราการเรียกด้วยตัวเอง

_session = requests.Session()
_last_call = [0.0]


class ApiStructureChanged(RuntimeError):
    """R2.5 — field ที่จำเป็นหายหรือเปลี่ยนชนิด ให้หยุดและแจ้งเตือน ห้ามเดา"""


def _slug(v) -> str:
    """GAP-12 — category / sub_category / pillar / product_type เป็น object {id,name,slug}
    ไม่ใช่ข้อความ (reference_pipeline.py อ่านเป็นข้อความตรงๆ จะได้ค่าผิด)"""
    if isinstance(v, dict):
        return str(v.get("slug") or v.get("name") or "").strip()
    return str(v or "").strip()


def _name(v) -> str:
    if isinstance(v, dict):
        return str(v.get("name") or v.get("slug") or "").strip()
    return str(v or "").strip()


def fetch_page(limit: int = 100, page: int = 1, subcategory: str | None = None,
               category: str | None = None) -> tuple[list[dict], int]:
    gap = time.monotonic() - _last_call[0]
    if gap < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - gap)
    params = {"lang": "THA", "user_type": "visitor", "content_type": "article",
              "limit": limit, "page": page}
    if subcategory:
        params["sub_category_slug"] = subcategory
    if category:
        params["category_slug"] = category

    last_err = None
    for attempt in range(3):
        try:
            r = _session.get(API, params=params, headers=HEADERS, timeout=30)
            _last_call[0] = time.monotonic()
            r.raise_for_status()
            body = r.json()
            break
        except Exception as e:                                  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    else:
        raise RuntimeError(f"เรียก API ไม่สำเร็จ: {last_err}")   # R2.8 — ผู้เรียกใช้ข้อมูลเดิม

    if "result" not in body or "data" not in body.get("result", {}):
        raise ApiStructureChanged("โครงสร้าง result.data หายไป")
    data = body["result"]["data"]
    if data:
        missing = [f for f in REQUIRED_FIELDS if f not in data[0]]
        if missing:
            raise ApiStructureChanged(f"field ที่จำเป็นหายไป: {missing}")
    return data, int(body["result"].get("total") or 0)


# ==========================================================================
# เนื้อหาเต็มของบทความ
# ==========================================================================
#
# search API ส่ง summary_plain มาแค่ย่อหน้าแรก (median 522 ตัวอักษรทั้งคลัง)
# ตัวเลขที่ RM ใช้คุยจริง — รายได้ อัตราโต RPO อัตราต่อสัญญา หัวข้อความเสี่ยง —
# อยู่ในเนื้อหาเต็มซึ่งไม่ได้มากับ API
#
# endpoint /content/detail มีอยู่จริง (schema ที่ตอบกลับมี full_content_plain)
# แต่หาชื่อพารามิเตอร์ที่ต้องส่งไม่ได้ — ลอง 19 แบบ ตอบ 400 ทั้งหมด และไฟล์ JS
# ของเว็บไม่มีโค้ดเรียก (เรียกจากฝั่งเซิร์ฟเวอร์) จึงอ่านจากหน้าบทความแทน
# หน้าเว็บฝัง full_content_html ไว้ใน payload ของ Next.js (self.__next_f)
#
# ถ้าทีมเว็บเปลี่ยนโครงสร้าง ตัวนี้จะดึงไม่ได้ — ต้องรายงาน ห้ามเงียบ (R2.5)
# ได้ชื่อพารามิเตอร์ของ /content/detail มาเมื่อไหร่ ให้สลับมาใช้ API แทน

_RSC_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_RSC_TEXT_REF = re.compile(r'"full_content_html":"\$([0-9a-f]+)"')
_TAG = re.compile(r"<[^>]+>")
FULL_TEXT_MIN = 400          # สั้นกว่านี้ถือว่าแกะไม่สำเร็จ ไม่ใช่บทความสั้น
FULL_TEXT_PER_INGEST = 40    # เพดานต่อการกดดึงข่าวหนึ่งครั้ง (0.4 วิ/หน้า)


def _rsc_stream(html: str) -> str:
    """ต่อ payload ของ Next.js ที่กระจายอยู่หลาย script tag ให้เป็นสายเดียว"""
    out = []
    for raw in _RSC_CHUNK.findall(html):
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return "".join(out)


# แท็กที่เป็น "จุดจบของย่อหน้า/ข้อ" ในของจริง — ตัวบทความใช้ p 40 อัน br 22 li 8
# ถ้าแทนด้วยช่องว่างเหมือนแท็กอื่น ข้อย่อยของ "มุมมองของ InnovestX" จะติดกันเป็นพืด
# อ่านไม่ออกว่ามีกี่ประเด็น จึงต้องเก็บขอบเขตไว้เป็นบรรทัดใหม่
_BLOCK_END = re.compile(r"</(?:p|li|ul|ol|div|h[1-6]|tr|blockquote)\s*>|<br\s*/?>",
                        re.IGNORECASE)


def _html_to_text(html: str) -> str:
    """HTML -> ข้อความ โดยคงการขึ้นย่อหน้าไว้เป็น \\n

    ช่องว่างในบรรทัดเดียวกันยังถูกยุบเหลืออันเดียวเหมือนเดิม โค้ดที่ค้นคำในเนื้อหา
    จึงเห็นข้อความชุดเดิมทุกประการ เปลี่ยนแค่ตรงที่เคยเป็นรอยต่อของแท็กบล็อก
    """
    txt = _BLOCK_END.sub("\n", html)
    txt = _TAG.sub(" ", txt)
    txt = txt.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    txt = txt.replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
    txt = re.sub(r"[ \t ]+", " ", txt)
    txt = re.sub(r" *\n[ \n]*", "\n", txt)
    return txt.strip()


def extract_full_text(html: str) -> str:
    """ดึงเนื้อหาเต็มออกจาก HTML ของหน้าบทความ — คืนค่าว่างถ้าโครงสร้างไม่ตรง"""
    stream = _rsc_stream(html)
    if not stream:
        return ""
    ref = _RSC_TEXT_REF.search(stream)
    if not ref:
        return ""
    # chunk ของ RSC เขียนเป็น "<id>:T<ความยาว>,<เนื้อหา>" โดยความยาวเป็นเลขฐานสิบหก
    # และนับเป็น "ไบต์" ไม่ใช่ตัวอักษร — ภาษาไทยตัวละ 3 ไบต์ ถ้าตัดตามจำนวนตัวอักษร
    # จะกินไปถึง chunk ถัดไป ได้เนื้อซ้ำและ marker ของ RSC ปนมาด้วย
    # chunk ไม่ได้ขึ้นบรรทัดใหม่ทุกอัน ใช้ lookbehind กันเลข id ชนกันแทน
    # (ref=13 ต้องไม่ไปแมตช์กลาง 113:T...)
    m = re.search(rf"(?<![0-9a-f]){ref.group(1)}:T([0-9a-f]+),", stream)
    if not m:
        return ""
    n_bytes = int(m.group(1), 16)
    body = stream[m.end():].encode("utf-8")[:n_bytes].decode("utf-8", "ignore")
    return _html_to_text(body)


# ท้ายบทความมีโฆษณาแอปกับคำเตือนความเสี่ยงต่อท้ายทุกชิ้น ไม่ใช่เนื้อข่าว
# เก็บดิบไว้ทั้งก้อน (ยังไม่รู้ว่าอนาคตจะใช้อะไร) แล้วตัดตอนอ่านแทน
_PROMO = re.compile(
    r"(สนใจลงทุนใน|เปิดประสบการณ์ลงทุนไร้ขีดจำกัด|ดาวน์โหลดแอป|เปิดบัญชี\s*InnovestX"
    r"|บทความนี้จัดทำขึ้นเพื่อ|คำเตือน\s*[:：]|ผู้ลงทุนควรทำความเข้าใจลักษณะสินค้า)"
)


def clean_body(full_text: str | None) -> str:
    """ตัดท้ายที่เป็นโฆษณา/คำเตือนมาตรฐานออก เหลือเฉพาะเนื้อข่าว"""
    t = (full_text or "").strip()
    if not t:
        return ""
    m = _PROMO.search(t)
    # ตัดเฉพาะเมื่อเจอในช่วงท้าย ๆ กันกรณีข่าวพูดถึงคำเหล่านี้กลางเรื่องจริง
    if m and m.start() > len(t) * 0.5:
        t = t[:m.start()].strip()
    return t


# หัวข้อที่บทความเขียนความเสี่ยงไว้เอง — ของจริงในคลัง ไม่ใช่การเดา
_RISK_HEAD = re.compile(
    r"(ความเสี่ยงที่ต้องเฝ้าระวัง|ความเสี่ยงที่ควรติดตาม|ความเสี่ยงที่ต้องติดตาม"
    r"|ปัจจัยเสี่ยงที่ต้องติดตาม|ประเด็นที่ต้องระวัง|ความเสี่ยงสำคัญ)"
)


def risk_section(full_text: str | None) -> str:
    """คืนย่อหน้าความเสี่ยงที่บทความเขียนไว้เอง (ว่างถ้าไม่มีหัวข้อนี้)"""
    body = clean_body(full_text)
    m = _RISK_HEAD.search(body)
    if not m:
        return ""
    return body[m.end():].strip(" :·-—")


# "มุมมองของ InnovestX" — ส่วนที่นักวิเคราะห์ของบริษัทสรุปความเห็นตัวเอง
#
# ต่างจากเนื้อข่าวตรงที่ข่าวเล่าว่าเกิดอะไรขึ้น ส่วนนี้บอกว่า "แล้วเราคิดว่ายังไง"
# ซึ่งเป็นสิ่งที่ RM เอาไปพูดกับลูกค้าได้จริงและเป็นของบริษัทเราเอง ไม่ใช่ของสำนักข่าว
# จึงควรถูกยกขึ้นมาให้เห็นก่อน ไม่ใช่ฝังอยู่กลางเนื้อหาเต็มที่ไม่มีใครเลื่อนไปอ่าน
#
# full_text ถูกแบนเป็นข้อความเรียบไปแล้ว หัวข้อจึงไม่มีแท็กกำกับ ต้องหาจุดจบเอง
# จากหัวข้อถัดไปที่รู้จัก — ของจริงจบที่ "ข้อสงวนสิทธิ์" เกือบทุกฉบับ
_VIEW_HEAD = re.compile(r"(?:(\d+)\s*[).]\s*)?มุมมองของ\s*(?:InnovestX|INVX|เรา)\s*[:：]?")
_VIEW_END = re.compile(
    r"(ข้อสงวนสิทธิ์|ข้อจำกัดความรับผิดชอบ|Disclaimer|คำเตือน\s*[:：]"
    r"|ความเสี่ยงที่ต้องเฝ้าระวัง|ความเสี่ยงที่ควรติดตาม|ความเสี่ยงที่ต้องติดตาม"
    r"|ปัจจัยเสี่ยงที่ต้องติดตาม)"
)
# ต้นฉบับซอยเป็นหมวดมีเลขนำ ("6) มุมมองของ InnovestX") หมวดถัดไปจึงเป็นจุดจบที่แน่นอนกว่า
# หัวข้อท้ายบทความ — บทความยาวบางฉบับมีหลายหมวดกว่าจะถึงข้อสงวนสิทธิ์ ถ้าไม่ตัดตรงนี้
# จะกวาดมาทั้งหมด (ของจริงเคยได้ 66 ข้อจากบทความเดียว)
_NUM_HEAD = re.compile(r"^\s*(\d{1,2})\s*[).]\s*\S", re.MULTILINE)
# ไม่เจอหัวข้อจบเลย = แทบแน่ว่าจับพลาด ไม่ใช่ความเห็นยาวจริง จำกัดไว้เท่าที่สมเหตุสมผล
VIEW_MAX_POINTS = 12


def invx_view(full_text: str | None) -> str:
    """คืนส่วน "มุมมองของ InnovestX" (ว่างถ้าบทความไม่มีส่วนนี้)

    ไม่ตัดความยาวตรงนี้ — ตัดตอนแสดงผลแทน เพราะแต่ละที่ต้องการไม่เท่ากัน
    (อีเมลเอาสั้น หน้าบทความเอาเต็ม) และของที่เก็บควรเป็นของจริงเสมอ
    """
    body = clean_body(full_text)
    m = _VIEW_HEAD.search(body)
    if not m:
        return ""
    tail = body[m.end():]

    # จบที่อันไหนมาก่อน: หัวข้อท้ายบทความ หรือหมวดถัดไปที่มีเลขนำ
    ends = [e.start() for e in (_VIEW_END.search(tail),) if e]
    if m.group(1):                      # หัวข้อนี้มีเลขนำ หมวดถัดไปย่อมมีเลขเช่นกัน
        want = int(m.group(1)) + 1
        nxt = next((n.start() for n in _NUM_HEAD.finditer(tail)
                    if int(n.group(1)) == want), None)
        if nxt is not None:
            ends.append(nxt)
    text = (tail[:min(ends)] if ends else tail).strip(" :·-—\n")
    # สั้นกว่านี้แปลว่าจับได้แค่เศษหัวข้อ ไม่ใช่เนื้อความเห็นจริง
    return text if len(text) >= 40 else ""


def invx_view_points(full_text: str | None) -> list[str]:
    """ส่วนมุมมอง แยกเป็นข้อ ๆ ตามที่บทความเขียนไว้

    ต้นฉบับเขียนเป็นข้อย่อยหลายข้อ (ภาพรวม / คุณภาพงบ / เทียบคู่แข่ง / ข้อควรระวัง)
    ถ้าแสดงติดกันเป็นพืดจะอ่านไม่ออกว่ามีกี่ประเด็น จึงคืนเป็นรายการเพื่อให้หน้าจอ
    กับอีเมลขึ้นเป็นบุลเล็ตได้ตรงตามที่นักวิเคราะห์แบ่งไว้เอง
    """
    text = invx_view(full_text)
    if not text:
        return []
    parts = [p.strip(" :·-—•") for p in text.split("\n")]
    # บรรทัดสั้นมากคือเศษหัวข้อหรือช่องว่างที่หลุดมา ไม่ใช่ประเด็นจริง
    return [p for p in parts if len(p) >= 25][:VIEW_MAX_POINTS]


def fetch_full_text(url_path: str) -> tuple[str, str]:
    """โหลดหน้าบทความจริง คืน (เนื้อหาเต็ม, สาเหตุที่ไม่ได้)

    แยกสาเหตุเพราะแก้ต่างกัน: ลิงก์เสียที่ต้นทางไม่มีอะไรให้แก้ฝั่งเรา
    บทความ PDF ต้องอ่านไฟล์แนบ ส่วนโครงสร้างหน้าเปลี่ยนคือของเราต้องตามแก้
    """
    url = article_url(url_path)
    if not url:
        return "", "ไม่มี url"
    gap = time.monotonic() - _last_call[0]
    if gap < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - gap)
    try:
        r = _session.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=30)
        _last_call[0] = time.monotonic()
    except Exception as e:                                     # noqa: BLE001
        return "", f"เรียกหน้าเว็บไม่สำเร็จ: {type(e).__name__}"
    if r.status_code == 404:
        return "", "หน้าไม่มีอยู่บนเว็บ (404) — ลิงก์เสียที่ต้นทาง"
    if r.status_code != 200:
        return "", f"หน้าเว็บตอบ {r.status_code}"

    text = extract_full_text(r.text)
    if len(text) >= FULL_TEXT_MIN:
        return text, ""
    stream = _rsc_stream(r.text)
    if '"pdf_url":""' not in stream and '"pdf_url":null' not in stream:
        return "", "เนื้อหาอยู่ในไฟล์ PDF ไม่มีข้อความบนหน้าเว็บ"
    if "full_content_html" not in stream:
        return "", "โครงสร้างหน้าเว็บเปลี่ยน — หา full_content_html ไม่เจอ"
    return "", f"เนื้อหาบนหน้าเว็บสั้นผิดปกติ ({len(text)} ตัวอักษร)"


def backfill_full_text(con, limit: int | None = None, redo: bool = False) -> dict:
    """เติมเนื้อหาเต็มให้บทความที่ยังไม่เคยลอง (บทความแม่เท่านั้น ข้อย่อยใช้ของแม่)

    full_text_at ถูกบันทึกทั้งกรณีได้และไม่ได้ — ที่ลองแล้วไม่ได้จะไม่ถูกไล่ดึงซ้ำ
    ทุกรอบ ต้องสั่ง redo=True เอง
    """
    now = dt.datetime.now().isoformat(timespec="seconds")
    where = "record_type='article' AND role='content'"
    if not redo:
        where += " AND full_text_at IS NULL"
    sql = f"SELECT article_id, url, title FROM articles WHERE {where} ORDER BY trigger_at DESC"
    rows = list(con.execute(sql + (f" LIMIT {int(limit)}" if limit else "")))
    ok, failed = 0, 0
    reasons: dict[str, int] = {}
    for r in rows:
        text, problem = fetch_full_text(r["url"])
        if problem:
            failed += 1
            key = problem.split(" —")[0].split(" (")[0]
            reasons[key] = reasons.get(key, 0) + 1
            db.report_unmapped(con, "full_text", r["article_id"], "R2.5", problem,
                               ref=r["url"], now=now)
            with con:                       # จำว่าเคยลองแล้ว จะได้ไม่วนดึงซ้ำ
                con.execute("UPDATE articles SET full_text_at=? WHERE article_id=?",
                            (now, r["article_id"]))
            continue
        with con:
            con.execute("UPDATE articles SET full_text=?, full_text_at=? WHERE article_id=?",
                        (text, now, r["article_id"]))
            # ข้อย่อยอ้างเนื้อหาเต็มของแม่ ไม่ต้องโหลดซ้ำ
            con.execute("UPDATE articles SET full_text=?, full_text_at=? "
                        "WHERE parent_article_id=?", (text, now, r["article_id"]))
        ok += 1
    picks = apply_top_picks(con, only_ids=[r["article_id"] for r in rows], now=now)
    return {"tried": len(rows), "stored": ok, "failed": failed,
            "reasons": reasons, "top_picks": picks, "at": now}


def apply_top_picks(con, only_ids: list[str] | None = None, now: str = "") -> dict:
    """เติม entity จากท่อน "หุ้นเด่น" ของเนื้อหาเต็ม (GAP-23)

    เติมทับไม่ได้ ต้องรวมกับของเดิม — entity จาก API เชื่อถือได้กว่า
    บทความที่ถูกเติมจะถูกล้าง matched_at เพื่อให้รอบจับคู่ถัดไปคำนวณใหม่
    """
    now = now or dt.datetime.now().isoformat(timespec="seconds")
    aliases = build_alias_index()
    where = "full_text IS NOT NULL AND full_text<>'' AND record_type='article' AND role='content'"
    args: list = []
    if only_ids:
        where += f" AND article_id IN ({','.join('?' * len(only_ids))})"
        args += only_ids

    changed, added = 0, 0
    for r in list(con.execute(f"SELECT * FROM articles WHERE {where}", args)):
        art = dict(r)
        got = extract_top_picks(art["full_text"], aliases)
        if not got:
            continue
        have = db.jload(art["entity"], []) or []
        fresh = [(e, a, q) for e, a, q in got if e not in have]
        if not fresh:
            continue
        ents = have + [e for e, _, _ in fresh]
        ev = db.jload(art["evidence"], {}) or {}
        for e, a, quote in fresh:
            ev[e] = _ev(f"บทความระบุเป็นหุ้นเด่น: “{quote}”", a, "GAP-23")
        secs = list(dict.fromkeys((db.jload(art["sector"], []) or [])
                                  + [x for x in (sector_of(e) for e in ents) if x]))
        with con:
            con.execute("""UPDATE articles SET entity=?, evidence=?, sector=?,
                              entity_source=CASE WHEN entity_source='none' THEN 'full_text'
                                                 ELSE entity_source END,
                              entity_confidence=CASE WHEN entity_confidence='unknown'
                                                 THEN 'confirmed' ELSE entity_confidence END,
                              matched_at=NULL
                           WHERE article_id=?""",
                        (db.jdump(ents), db.jdump(ev), db.jdump(secs), art["article_id"]))
            # ข้อย่อยไม่ต้องแตะ — หุ้นเด่นเป็นของบทความแม่
        changed += 1
        added += len(fresh)
    return {"articles": changed, "entities_added": added}


def prune_old(con, days: int = 0, dry_run: bool = False) -> dict:
    """ลบข่าวที่เก่ากว่าช่วงที่เก็บ พร้อมคู่จับของมัน

    นับจาก "วันข่าวล่าสุดในฐาน" ไม่ใช่วันนี้ตามนาฬิกา — ถ้าไม่ได้ดึงข่าวหลายวัน
    การนับจากนาฬิกาจะลบของที่ยังเป็นล่าสุดอยู่ทิ้งไปหมด

    entity_pairs (ความสัมพันธ์หุ้นที่ระบบเรียนจาก co-mention) ไม่ถูกลบ เพราะเป็นความรู้
    ที่สะสมมา ไม่ใช่ตัวข่าว แต่ต้องตัด article_id ที่ชี้ของที่ไม่มีแล้วออก ไม่ให้ลิงก์พัง
    """
    days = days or RETENTION_DAYS
    latest = con.execute("SELECT MAX(substr(trigger_at,1,10)) FROM articles").fetchone()[0]
    if not latest:
        return {"cutoff": None, "articles": 0, "matches": 0, "keep_articles": 0,
                "pairs_cleaned": 0}
    cutoff = (dt.date.fromisoformat(latest) - dt.timedelta(days=days - 1)).isoformat()

    old = [r[0] for r in con.execute(
        "SELECT article_id FROM articles WHERE substr(trigger_at,1,10) < ?", (cutoff,))]
    n_match = con.execute(
        "SELECT COUNT(*) FROM matches m JOIN articles a USING(article_id) "
        "WHERE substr(a.trigger_at,1,10) < ?", (cutoff,)).fetchone()[0]
    keep = con.execute("SELECT COUNT(*) FROM articles WHERE substr(trigger_at,1,10) >= ?",
                       (cutoff,)).fetchone()[0]
    out = {"cutoff": cutoff, "articles": len(old), "matches": n_match, "keep_articles": keep,
           "pairs_cleaned": 0}
    if dry_run or not old:
        return out

    size_before = DB_SIZE_MB()
    gone = set(old)
    with con:
        for i in range(0, len(old), 400):
            chunk = old[i:i + 400]
            qs = ",".join("?" * len(chunk))
            con.execute(f"DELETE FROM matches WHERE article_id IN ({qs})", chunk)
            con.execute(f"DELETE FROM articles WHERE article_id IN ({qs})", chunk)
        # ข้อย่อยของบทความที่ถูกลบ ต้องไม่ค้างเป็นลูกกำพร้า
        con.execute("DELETE FROM matches WHERE article_id IN "
                    "(SELECT article_id FROM articles WHERE parent_article_id IS NOT NULL "
                    " AND parent_article_id NOT IN (SELECT article_id FROM articles))")
        con.execute("DELETE FROM articles WHERE parent_article_id IS NOT NULL "
                    "AND parent_article_id NOT IN (SELECT article_id FROM articles)")

        # article_ids ของตารางนี้เก็บเป็นสตริงคั่นด้วยจุลภาค (ดูตัว INSERT ที่ learn_pairs)
        # ไม่ใช่ JSON — เขียนโค้ดล้างครั้งแรกเป็น jload แล้วมันเงียบ ๆ ไม่ล้างอะไรเลย
        cleaned = 0
        for a, b, ids in con.execute("SELECT a, b, article_ids FROM entity_pairs").fetchall():
            have = [x for x in (ids or "").split(",") if x]
            keep_ids = [x for x in have if x not in gone]
            if len(keep_ids) != len(have):
                con.execute("UPDATE entity_pairs SET article_ids=? WHERE a=? AND b=?",
                            (",".join(keep_ids), a, b))
                cleaned += 1
        out["pairs_cleaned"] = cleaned

    con.execute("VACUUM")                       # คืนพื้นที่จริง ไม่ใช่แค่ปล่อยหน้าว่าง
    out["size_before_mb"] = size_before
    out["size_after_mb"] = DB_SIZE_MB()
    return out


def DB_SIZE_MB() -> float:
    try:
        return round(db.DB_PATH.stat().st_size / 1e6, 1)
    except OSError:
        return 0.0


# ==========================================================================
# Thai Stock Coverage List — สดจาก PDF รายสัปดาห์ แทนที่ STEP4 B3 ที่แช่แข็งตอนส่งมอบสเปค
# ==========================================================================
#
# recommendation-summary เป็นหมวด reference (role='reference' ไม่ส่งใคร) ที่ INVX Research
# ออก PDF "Recommendation" ทุกสัปดาห์ — เนื้อหาคือ Thai Stock Coverage List ตัวเดียวกับที่
# STEP4 ชีต B3 ให้มา แต่สดกว่า (Excel เป็น snapshot ตอนส่งมอบสเปค ไม่เคยอัปเดตอีกเลย)
# ตรวจกับของจริงแล้ว (3 ส.ค. 2569): แกะได้ 99 ตัว vs Excel 97 ตัว ไม่มีตัวไหนหายไปจากของเดิม
# มี rating เปลี่ยน 3 ตัว (KKP, TOP, DELTA) ซึ่งสมเหตุสมผลเพราะเวลาผ่านมานาน ไม่ใช่ตัวแกะพัง
#
# ล้มเหลวได้ทุกจุด (เครือข่าย, PDF format เปลี่ยน, หมวดข่าวย้ายที่) — คืนค่าว่างเสมอ ไม่ raise
# เพื่อให้ build_refdata.py ใช้ของเดิมจาก Excel ต่อได้เมื่อดึงสดไม่สำเร็จ (R2.8)

_COVERAGE_TICKER = re.compile(
    r"^([A-Z0-9][A-Z0-9]{1,7})\s+(No rec|Outperform|Underperform|Neutral|Trading Buy|Buy|Sell|Hold)"
    r"\s+([A-Z]{1,3}\*{0,2}|-)\s+([\d,]+\.\d+)(.*)$")
_COVERAGE_SECTOR = re.compile(r"^([A-Za-z][A-Za-z &/\-]{2,40}?)\s+\(?-?[\d,]+(?:\.\d+)?\)?\b")
_COVERAGE_TARGET = re.compile(r"\s*([\d,]+\.\d+)")
_PDF_URL_RE = re.compile(r'"pdf_url":"([^"]*)"')
COVERAGE_MIN_TICKERS = 50    # ต่ำกว่านี้มากถือว่าแกะพัง ไม่ใช่ของจริง (ปกติ ~97-100 ตัว)


def parse_thai_coverage_pdf(pdf_bytes: bytes) -> dict[str, dict]:
    """แกะตาราง Thai Stock Coverage List จาก PDF "Recommendation" ของ INVX Research

    คืนรูปแบบเดียวกับ build_refdata.thai_sector(): ticker -> sector/rating/esg/
    last_close/target_price — PDF มีตารางเดียวกันซ้ำสองแบบ (คอลัมน์เต็ม + คอลัมน์ย่อ)
    ใช้ first-seen-wins ต่อ ticker พอ เพราะสองแบบมีค่าตรงกันอยู่แล้ว

    ต้อง import pypdf ในฟังก์ชัน — งานนี้รันแบบ manual/ตั้งเวลาเท่านั้น ไม่ใช่ runtime หลัก
    ของระบบ จึงไม่บังคับให้ทุกเครื่องที่รัน API ต้องติดตั้ง pypdf ไว้ด้วย
    """
    import io

    from pypdf import PdfReader
    text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)

    sector, out = None, {}
    for raw in text.split("\n"):
        ln = raw.rstrip()
        if not ln.strip():
            continue
        m = _COVERAGE_TICKER.match(ln.strip())
        if m:
            tic, rec, esg, price, rest = m.groups()
            if tic in out:
                continue                       # first-seen-wins (ตารางซ้ำในไฟล์เดียวกัน)
            target = None
            if rec != "No rec":
                tm = _COVERAGE_TARGET.match(rest)
                if tm:
                    target = float(tm.group(1).replace(",", ""))
            out[tic] = {
                "sector": sector, "rating": rec,
                "esg": None if esg == "-" else esg.rstrip("*"),
                "last_close": float(price.replace(",", "")), "target_price": target,
            }
            continue
        sm = _COVERAGE_SECTOR.match(ln.strip())
        if sm and 2 < len(sm.group(1).strip()) < 45:
            sector = sm.group(1).strip()
    return out


def thai_coverage_live() -> tuple[dict[str, dict], str | None]:
    """ดึง PDF "Recommendation" ล่าสุดจาก Cafe Invest แล้วแกะเป็น Coverage List

    คืน (ผลที่แกะได้, ข้อความปัญหา) — ล้มเหลวจุดไหนคืน ({}, เหตุผล) เสมอ ไม่ raise
    เพราะตัวเรียก (build_refdata.py) ต้องใช้ของเดิมจาก Excel ต่อได้เมื่อดึงสดไม่สำเร็จ
    """
    try:
        data, _ = fetch_page(limit=1, page=1, subcategory="recommendation-summary")
    except Exception as e:                                          # noqa: BLE001
        return {}, f"เรียก API ไม่สำเร็จ: {e}"
    if not data:
        return {}, "ไม่พบบทความในหมวด recommendation-summary"

    url = article_url(data[0].get("url") or "")
    if not url:
        return {}, "บทความไม่มี url"
    try:
        r = _session.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=30)
    except Exception as e:                                          # noqa: BLE001
        return {}, f"เรียกหน้าเว็บไม่สำเร็จ: {e}"
    m = _PDF_URL_RE.search(_rsc_stream(r.text))
    if not m:
        return {}, "ไม่พบ pdf_url ในหน้าบทความ — โครงสร้างหน้าเว็บอาจเปลี่ยน"
    try:
        pr = requests.get(m.group(1), timeout=30)
        pr.raise_for_status()
    except Exception as e:                                          # noqa: BLE001
        return {}, f"ดาวน์โหลด PDF ไม่สำเร็จ: {e}"
    try:
        parsed = parse_thai_coverage_pdf(pr.content)
    except Exception as e:                                          # noqa: BLE001
        return {}, f"แกะ PDF ไม่สำเร็จ: {e}"
    if len(parsed) < COVERAGE_MIN_TICKERS:
        return {}, f"แกะได้แค่ {len(parsed)} ตัว ต่ำกว่าที่ควรมาก — โครงสร้าง PDF อาจเปลี่ยน"
    return parsed, None


# ==========================================================================
# การซอย Brief (R3.1 - R3.5)
# ==========================================================================

# GAP-13 — ในของจริงเลขข้อถัดไป "ติด" กับตัวอักษรไทยของข้อก่อนหน้า ไม่ได้เว้นวรรค
# เช่น "...Bond Yield ยังผันผวน2. ราคาน้ำมันร่วง 7%"  จึงห้ามบังคับให้มีช่องว่างข้างหน้า
# แต่ยังกันเลขกลางประโยคตาม R3.4 ด้วยการบังคับว่าหลังจุดต้องเป็นช่องว่าง (7.2 จึงไม่ติด)
# และรับเฉพาะเลขที่ไล่ลำดับ 1,2,3... เท่านั้น
_ITEM_RE = re.compile(r"(?<![\d.])(\d{1,2})\.[ \t ]+")


# คำเชื่อมที่ใช้เป็นจุดตัดหัวข้อ — ตัดตรงนี้ได้ใจความครบ ไม่ห้วน
_HEAD_BREAKS = (" หลัง", " ขณะที่", " ด้าน", " โดย", " ทั้งนี้", " ส่วน", " พร้อม",
                " เพื่อ", " และ", " แต่", " ส่งผล", " ซึ่ง", " จาก")
HEAD_MIN, HEAD_MAX = 32, 92


def segment_headline(body: str) -> str:
    """สร้างหัวข้อของข้อย่อยจากเนื้อความ

    หัวข้อเดิมเป็น "Morning Brief - ... — ข้อ 3" ซึ่งไม่บอกอะไรเลย
    คนเปิดหน้าวันนี้ต้องรู้จากหัวข้อว่าข้อนี้เรื่องอะไร ไม่ต้องคลิกเข้าไปอ่าน
    ตัดที่คำเชื่อมตัวแรกที่อยู่ในช่วงความยาวที่อ่านได้ ไม่มีก็ตัดที่ช่องว่างสุดท้าย
    """
    s = " ".join((body or "").split())
    if not s:
        return ""
    if len(s) <= HEAD_MAX:
        return s.rstrip(" ,;:·-–—")

    cut = None
    for sep in _HEAD_BREAKS:
        at = s.find(sep)
        if HEAD_MIN <= at <= HEAD_MAX and (cut is None or at < cut):
            cut = at
    if cut is None:
        cut = s.rfind(" ", 0, HEAD_MAX)
        if cut < HEAD_MIN:
            cut = HEAD_MAX
        return f"{s[:cut].rstrip(' ,;:·-–—')} …"
    return s[:cut].rstrip(" ,;:·-–—")


def retitle_segments(con) -> int:
    """เขียนหัวข้อของข้อย่อยที่เก็บไว้แล้วใหม่ — ใช้ตอน backfill ข้อมูลเก่า"""
    rows = list(con.execute(
        "SELECT article_id, segment_text, title FROM articles "
        "WHERE record_type='segment' AND segment_text IS NOT NULL AND segment_text<>''"))
    fixed = []
    for r in rows:
        head = segment_headline(r["segment_text"])
        if head and head != r["title"]:
            fixed.append((head, r["article_id"]))
    if fixed:
        with con:
            con.executemany("UPDATE articles SET title=? WHERE article_id=?", fixed)
    return len(fixed)


def split_segments(text: str) -> list[str]:
    """ซอยเป็นข้อย่อยตามเลขข้อ

    R3.4 — ตัวเลขกลางประโยค (7.2 หมื่นล้าน) ห้ามนับ จึงรับเฉพาะลำดับที่ไล่ 1,2,3...
    R3.2 — จำนวนข้อไม่คงที่ ซอยตามที่พบจริง ห้ามบังคับ 6
    """
    if not text:
        return []
    marks = [(m.start(), m.end(), int(m.group(1))) for m in _ITEM_RE.finditer(text)]
    keep, want = [], 1
    for start, end, n in marks:
        if n == want:
            keep.append((start, end))
            want += 1
    if len(keep) < 2:
        return []
    out = []
    for i, (start, end) in enumerate(keep):
        stop = keep[i + 1][0] if i + 1 < len(keep) else len(text)
        body = text[end:stop].strip()
        if body:
            out.append(body)
    return out


# ==========================================================================
# การสกัด entity
# ==========================================================================

_DATE_TOKEN = re.compile(r"^\d{6,8}$")
_STOP_SLUG = {"news", "update", "report", "daily", "weekly", "brief", "th", "thai",
              "stock", "stocks", "offshore", "toppicks", "picks", "top", "short",
              "term", "trading", "special", "analysis", "earnings", "company"}


def extract_from_slug(url: str, uni: Universe) -> list[str]:
    """สกัด ticker จาก url  เช่น thaistocktoppicks-kkp-20260721 -> KKP"""
    slug = (url or "").rstrip("/").rsplit("/", 1)[-1]
    hits = []
    for tok in slug.split("-"):
        t = tok.strip().upper()
        if not t or _DATE_TOKEN.match(t) or tok.lower() in _STOP_SLUG or len(t) < 2:
            continue
        if t in refdata()["thai_sector"] or t in uni.ids:
            hits.append(t)
        else:
            ent, _ = uni.resolve_root(t)
            if ent:
                hits.append(ent)
    return list(dict.fromkeys(hits))


_UPPER_TOKEN = re.compile(r"\b([A-Z][A-Z0-9&()\.\-]{2,})\b")


def extract_from_title(title: str, uni: Universe, fund_codes: set[str]) -> list[str]:
    """สกัดรหัสกองทุน / ticker จากชื่อบทความ (ระดับ inferred)"""
    hits = []
    for tok in _UPPER_TOKEN.findall(title or ""):
        t = tok.strip(".-")
        if t in fund_codes or t in refdata()["fund_underlying"]:
            hits.append(t)
        elif t in refdata()["thai_sector"]:
            hits.append(t)
    return list(dict.fromkeys(hits))


def build_alias_index() -> list[tuple[str, str]]:
    """C1 — (alias, entity) เรียงยาวไปสั้น

    R4.43/R4.44 — alias ต้องยาวและไม่กำกวม ห้ามใช้ตัวย่อ 2 ตัวอักษรของหุ้นนอก
    R4.45 — ตัวย่อหุ้นไทยตัวใหญ่ทั้งหมดใช้ได้
    """
    pairs = []
    for entity, info in refdata()["entity_dictionary"].items():
        for a in info["aliases"]:
            a = a.strip()
            if len(a) >= 3:
                pairs.append((a, entity))
    # R4.45 — ตัวย่อหุ้นไทยตัวใหญ่ทั้งหมดใช้เป็น alias ได้ เพราะปรากฏตรงตัวในเนื้อหาไทย
    # จำกัดที่ Coverage List 97 ตัว (มี sector และ target price ครบ) และยาว >= 3 ตาม R4.44
    seen = {a for a, _ in pairs}
    for tic in refdata()["thai_sector"]:
        if len(tic) >= 3 and tic not in seen:
            pairs.append((tic, tic))
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


def extract_from_text(text: str, aliases: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """R4.47 — คืน (entity, alias ที่ทำให้จับได้) เพื่อบันทึกหลักฐาน

    R4.44 — alias ภาษาละตินทุกตัวต้องตรงแบบคำเต็ม ไม่ใช่แค่ substring
    เดิมบังคับขอบเขตคำเฉพาะ alias ตัวพิมพ์ใหญ่ล้วน ทำให้ชื่อแบบ SpaceX / Meta
    ไปตรงกับ SpaceXAI และ MetaX (คนละบริษัท) แล้วส่งรายชื่อผิดถึง RM
    ตัวพิมพ์ใหญ่ล้วน = ตัวย่อหุ้น เทียบแบบตรงตัวพิมพ์ (R4.45)
    ชื่อผสมตัวเล็ก = ชื่อบริษัท เทียบโดยไม่สนตัวพิมพ์ (Nvidia / NVIDIA)
    ภาษาไทยไม่มีการเว้นวรรค จึงบังคับขอบเขตคำไม่ได้ — ตัวให้เกรดจะคืนบริบทให้คนดูแทน
    """
    if not text:
        return []
    low = text.lower()
    out: dict[str, str] = {}
    for alias, entity in aliases:
        if entity in out:
            continue
        if alias.isascii():
            flags = 0 if alias.isupper() else re.I
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text, flags):
                out[entity] = alias
        elif alias.lower() in low:
            out[entity] = alias
    return list(out.items())


_TFEX_CODE_RE = re.compile(r"\b([A-Z][A-Z0-9]{0,9}[FGHJKMNQUVXZ]\d{2}X?)\b")


def extract_tfex(text: str, uni: Universe) -> list[tuple[str, str]]:
    """GAP-18 — สกัดรหัสสัญญา TFEX จากสรุปบทความ แล้วถอด underlying (R4.18 - R4.22)

    คืน (entity, รหัสสัญญาที่ทำให้จับได้) เพื่อบันทึกหลักฐาน
    """
    out: dict[str, str] = {}
    for code in _TFEX_CODE_RE.findall(text or ""):
        res = map_tfex(code, uni)
        if res.ok and res.entity not in out:
            out[res.entity] = code
    return list(out.items())


# GAP-23 — บทวิเคราะห์รายกลุ่มเขียนไว้ตรง ๆ ว่า "หุ้นเด่น: BBL KTB KBANK"
# แต่ API ส่ง stock=[] มาให้ ระบบจึงเก็บได้แค่ sector=Banking แล้วจับคู่ที่ระดับ L3
# ทั้งที่ควรได้ L1 กับคนที่ถือสามตัวนั้นจริง ๆ — spec ไม่ได้พูดถึงกรณีนี้
_PICK_HEAD = re.compile(
    r"(หุ้นเด่น|หุ้นแนะนำ|หุ้นที่เราชอบ|หุ้นที่ชอบ|ตัวเลือกหลัก|เราเลือก|เราชอบ|เราแนะนำ"
    r"|top\s*picks?|our\s*picks?)", re.I)
# ตัดหน้าต่างที่หัวข้อถัดไปเสมอ ไม่ให้ไปกวาดชื่อในท่อน "ความเสี่ยงสำคัญ"
# ซึ่งพูดถึงบริษัทในเชิงลบหรือเชิงเปรียบเทียบ ไม่ใช่ตัวที่บทความเชียร์
# คำแนะนำระดับอื่น (NEUTRAL / UNDERPERFORM) ก็ต้องหยุด เพราะบทวิเคราะห์มักไล่เรียง
# "เราชอบ X (top pick) ... เราแนะนำ NEUTRAL สำหรับ Y และ Z" — Y กับ Z ไม่ใช่หุ้นเด่น
_PICK_STOP = re.compile(
    r"(ความเสี่ยง|ปัจจัยเสี่ยง|risk|ข้อควรระวัง|อย่างไรก็ตาม|ทั้งนี้"
    r"|NEUTRAL|UNDERPERFORM|UNDERWEIGHT|SELL|ถือ\b|ขาย\b|ลดน้ำหนัก"
    r"|ยกเว้น|Except(?:ing)?|ไม่รวม)", re.I)
PICK_WINDOW = 260
# ตัวย่อที่ตามด้วยคำเหล่านี้ไม่ใช่หุ้น เป็นชื่อหน่วยงานวิจัยที่บทวิเคราะห์อ้างอิงบ่อย
# (เจอจริง: "line up with SCB EIC" ทำให้ SCB กลายเป็นหุ้นเด่นของบทความสาธารณูปโภค)
_NOT_TICKER_NEXT = re.compile(r"^\s*(EIC|Research|Securities|Asset|AM)\b", re.I)


def extract_top_picks(text: str, aliases: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """คืน (entity, alias, ประโยคที่ยกมาเป็นหลักฐาน) จากท่อน "หุ้นเด่น" ของเนื้อหาเต็ม

    อ่านเฉพาะช่วงสั้น ๆ หลังคำชี้ ไม่กวาดทั้งบทความ เพราะบทวิเคราะห์กลุ่มเอ่ยชื่อ
    บริษัทอื่นได้อีกหลายที่ด้วยเจตนาต่างกัน (คู่แข่ง ตัวเทียบ ความเสี่ยง คำแนะนำระดับอื่น)
    """
    if not text:
        return []
    out: dict[str, tuple[str, str]] = {}
    for m in _PICK_HEAD.finditer(text):
        window = text[m.start():m.start() + PICK_WINDOW]
        stop = _PICK_STOP.search(window, m.end() - m.start())
        if stop:
            window = window[:stop.start()]
        for entity, alias in extract_from_text(window, aliases):
            at = window.find(alias)
            if at >= 0 and _NOT_TICKER_NEXT.match(window[at + len(alias):]):
                continue                     # ชื่อหน่วยงาน ไม่ใช่หุ้น
            out.setdefault(entity, (alias, " ".join(window.split())[:200]))
    return [(e, a, q) for e, (a, q) in out.items()]


def detect_sector_from_title(title: str) -> list[tuple[str, str]]:
    """GAP-17 — หา sector จากหัวข้อบทวิเคราะห์รายอุตสาหกรรม

    ใช้เฉพาะหัวข้อของหมวด sector_analysis และคำค้นยาวเฉพาะเจาะจงเท่านั้น (หลัก R3.37)
    """
    head = (title or "").split("–")[0].split("-")[0]
    out: dict[str, str] = {}
    for word, sector in sorted(SECTOR_BY_THAI_KEYWORD.items(), key=lambda x: -len(x[0])):
        if word in head and sector not in out:
            out[sector] = word
    return list(out.items())


def macro_keywords() -> dict[str, list[str]]:
    """คำค้น macro จาก spec + คำที่คนอนุมัติเพิ่มทีหลัง (overrides.json)"""
    out = {t: list(w) for t, w in refdata()["macro_keywords"].items()}
    for topic, words in _ov.macro_keyword().items():
        out.setdefault(topic, []).extend(w for w in words if w not in out.get(topic, []))
    return out


def detect_macro(text: str) -> tuple[list[str], dict[str, str]]:
    """R3.37 - R3.40 — หา macro_topic จากคำค้นที่ทดสอบผ่านแล้วเท่านั้น"""
    if not text:
        return [], {}
    low = text.lower()
    topics, why = [], {}
    for topic, words in macro_keywords().items():
        for w in words:
            w = w.strip()
            if not w:
                continue
            hit = (re.search(rf"\b{re.escape(w)}\b", low) if w.isascii()
                   else w.lower() in low)
            if hit:
                topics.append(topic)
                why[topic] = w
                break
    return topics, why


# ==========================================================================
# แท็กบทความ 1 ชิ้น
# ==========================================================================

def asset_classes_for(product_type: str, subcategory: str) -> list[str]:
    if subcategory in ASSET_CLASS_OVERRIDE_BY_SUBCATEGORY:
        return ASSET_CLASS_OVERRIDE_BY_SUBCATEGORY[subcategory]
    if subcategory in PRODUCT_TYPE_BLOCKED_SUBCATEGORIES:      # R2.2
        return []
    out: list[str] = []
    for part in [p.strip() for p in (product_type or "").split(",") if p.strip()]:
        out.extend(ARTICLE_ASSET_CLASS_MAP.get(part, []))
    return list(dict.fromkeys(out))


def _ev(text: str, token: str, rule: str) -> dict:
    """R4.47 — หลักฐานหนึ่งชิ้น: อ่านให้คนเข้าใจ + คำที่ทำให้จับได้ + เลขกฎ"""
    return {"text": text, "token": token, "rule": rule}


def _apply_grade(row: dict, source: str, entities: list[str], evidence: dict[str, dict],
                 title: str, uni: Universe, text: str = "") -> None:
    """GAP-21 — ให้เกรดคุณภาพหลักฐาน ไม่บล็อกการจับคู่ (uni.ids = สินทรัพย์ที่ลูกค้าถือจริง)

    ตอนนี้ยังไม่รู้สัดส่วนทั้งคลัง (R3.38) — regrade() หลัง ingest จะเติมให้
    """
    g = grade(source=source, entities=entities, evidence=evidence, title=title,
              held=uni.ids, text=text)
    row["auto_grade"] = g["grade"]
    row["auto_reason_th"] = g["reason_th"]
    row["auto_reason_en"] = g["reason_en"]
    row["auto_checks"] = db.jdump(g["checks"])


def tag(raw: dict, uni: Universe, aliases: list[tuple[str, str]], fund_codes: set[str],
        con=None, now: str = "") -> list[dict]:
    """แปลง JSON 1 ชิ้นเป็นแถว article (+ แถว segment ถ้าเป็น Brief)"""
    sub = _slug(raw.get("sub_category"))
    article_id = str(raw.get("id"))
    content_type = CONTENT_TYPE_BY_SUBCATEGORY.get(sub)
    if content_type is None:
        # R3.16 — subcategory ที่ไม่รู้จัก ห้ามเดา ให้รายงาน
        if con is not None:
            db.report_unmapped(con, "subcategory", sub or "(ว่าง)", "R3.16",
                               "subcategory ที่ไม่อยู่ในรายการที่รู้จัก", ref=article_id, now=now)
        return []

    summary = str(raw.get("summary_plain") or "")
    title = str(raw.get("title") or "")
    url = str(raw.get("url") or "")

    # --- entity จาก API (น่าเชื่อถือที่สุด) ---
    # R4.47 — หลักฐานเก็บเป็นโครงสร้าง {text, token, rule} ไม่ใช่ข้อความล้วน
    # เพราะตัวให้เกรดต้องรู้ว่า "คำไหน" ทำให้จับได้ ไม่ใช่ไปงมหาในประโยค
    entity_raw = [s.get("name") for s in (raw.get("stock") or []) if s.get("name")]
    entities, source, confidence, evidence = [], "none", "unknown", {}
    for sym in entity_raw:
        res = map_news_symbol(sym, uni)
        if res.ok:
            entities.append(res.entity)
            evidence[res.entity] = _ev(f"API ส่ง stock={sym} มาให้", sym, res.rule)
        elif con is not None:
            db.report_unmapped(con, "news_entity", str(sym), res.rule, res.note,
                               ref=article_id, now=now)
    if entities:
        source, confidence = "api", "confirmed"

    # --- ถ้า API ไม่ให้มา ลองตามลำดับความน่าเชื่อถือ ---
    if not entities and sub in TFEX_SUBCATEGORIES:
        got = extract_tfex(f"{title} {summary}", uni)
        if got:
            entities = [e for e, _ in got]
            source, confidence = "summary", "confirmed"
            evidence = {e: _ev(f"พบรหัสสัญญา {c} ในสรุปบทความ", c, "R4.18") for e, c in got}
    if not entities:
        got = extract_from_slug(url, uni)
        if got:
            slug = url.rsplit("/", 1)[-1]
            entities, source, confidence = got, "url_slug", "confirmed"
            evidence = {e: _ev(f"ticker อยู่ใน url: {slug}", e, "R3.21") for e in got}
    if not entities:
        got = extract_from_title(title, uni, fund_codes)
        if got:
            entities, source, confidence = got, "title", "inferred"
            evidence = {e: _ev(f"พบรหัส {e} ในชื่อบทความ", e, "R4.43") for e in got}
    if not entities and summary:
        got = extract_from_text(summary, aliases)
        if got:
            entities = [e for e, _ in got]
            # STEP3 ชีต "ที่มาต่อหมวด" — หมวดคริปโตเอ่ยชื่อเหรียญตรงตัว ถือเป็น confirmed
            source = "summary"
            confidence = "confirmed" if sub in SUMMARY_CONFIRMED_SUBCATEGORIES else "inferred"
            evidence = {e: _ev(f"พบชื่อ “{a}” ในสรุปบทความ", a, "R4.42") for e, a in got}

    entities = list(dict.fromkeys(entities))
    sectors = list(dict.fromkeys(s for s in (sector_of(e) for e in entities) if s))
    sector_why: dict[str, str] = {}
    if sub in SECTOR_KEYWORD_SUBCATEGORIES:
        for sec, word in detect_sector_from_title(title):
            if sec not in sectors:
                sectors.append(sec)
            sector_why[sec] = word
    macro, macro_why = detect_macro(f"{title} {summary}")

    importance = IMPORTANCE_BY_SUBCATEGORY.get(sub, IMPORTANCE_BY_CONTENT_TYPE.get(content_type, 1))
    urgency = URGENCY_BY_SUBCATEGORY.get(sub) or URGENCY_BY_CONTENT_TYPE.get(content_type, "low")
    role = "reference" if sub in REFERENCE_SUBCATEGORIES else "content"
    mode = "realtime" if content_type in REALTIME_CONTENT_TYPES else "digest"

    product_type = _name(raw.get("product_type"))
    aac = asset_classes_for(product_type, sub)

    base = {
        "article_id": article_id, "record_type": "article", "parent_article_id": None,
        "segment_no": None, "segment_text": None, "title": title, "url": url,
        "summary": summary, "trigger_at": str(raw.get("published_date") or ""),
        "display_at": str(raw.get("displayed_date") or ""),
        "pillar": _name(raw.get("pillar")), "category": _slug(raw.get("category")),
        "subcategory": sub, "source": str(raw.get("source") or ""),
        "product_type": product_type, "subcategory_name": _name(raw.get("sub_category")),
        "entity_raw": db.jdump(entity_raw), "entity": db.jdump(entities),
        "article_asset_class": db.jdump(aac), "content_type": content_type,
        "entity_source": source, "entity_confidence": confidence,
        "sector": db.jdump(sectors),
        "macro_topic": db.jdump([{"topic": t, "keyword": macro_why[t]} for t in macro]),
        "importance": importance, "urgency": urgency, "role": role, "mode": mode,
        "image_url": ((raw.get("image_16_9") or {}) or {}).get("url"),
        "read_minutes": raw.get("read_time_minute"),
    }
    # หลักฐานว่าแต่ละ entity / sector ได้มาจากอะไร — RM ต้องตอบได้ว่าทำไม
    ev_all = {**evidence,
              **{sec: _ev(f"หัวข้อบทความมีคำว่า “{w}”", w, "GAP-17")
                 for sec, w in sector_why.items()}}
    base["evidence"] = db.jdump(ev_all)
    _apply_grade(base, source, entities, ev_all, title, uni, f"{title} {summary}")

    rows = [base]

    # --- Brief: ซอยเป็นข้อย่อย แล้วจับคู่ที่ระดับข้อ (R3.1 - R3.5) ---
    if sub in SEGMENTED_SUBCATEGORIES:
        parts = split_segments(summary)
        if not parts:
            base["entity_source"] = "none"                       # R3.3 ห้ามเดา
            base["entity"] = db.jdump([])
            if con is not None:
                db.report_unmapped(con, "segment", article_id, "R3.3",
                                   "ซอย Brief เป็นข้อย่อยไม่ได้", ref=url, now=now)
        else:
            if not (SEGMENT_MIN <= len(parts) <= SEGMENT_MAX):   # R3.2
                if con is not None:
                    db.report_unmapped(con, "segment", article_id, "R3.2",
                                       f"จำนวนข้อผิดปกติ: {len(parts)} ข้อ", ref=url, now=now)
            base["entity"] = db.jdump([])                        # แม่ไม่ต้องมี entity
            base["entity_source"] = "none"
            for i, body in enumerate(parts, start=1):
                got = extract_from_text(body, aliases)
                seg_ents = [e for e, _ in got]
                seg_macro, seg_why = detect_macro(body)
                seg_src = "summary" if seg_ents else "none"
                seg_ev = {e: _ev(f"พบชื่อ “{a}” ในข้อ {i}", a, "R4.42") for e, a in got}
                seg = {
                    **base,
                    "article_id": f"{article_id}#{i}", "record_type": "segment",
                    "parent_article_id": article_id, "segment_no": i, "segment_text": body,
                    "title": segment_headline(body) or f"{title} — ข้อ {i}",
                    "entity_raw": db.jdump([]), "entity": db.jdump(seg_ents),
                    "entity_source": seg_src,
                    "entity_confidence": "inferred" if seg_ents else "unknown",
                    "sector": db.jdump([s for s in (sector_of(e) for e in seg_ents) if s]),
                    "macro_topic": db.jdump([{"topic": t, "keyword": seg_why[t]} for t in seg_macro]),
                    "evidence": db.jdump(seg_ev),
                }
                _apply_grade(seg, seg_src, seg_ents, seg_ev, body, uni, body)
                rows.append(seg)
    return rows


# ==========================================================================
# บันทึกลง DB
# ==========================================================================

FIELDS = ("article_id", "record_type", "parent_article_id", "segment_no", "segment_text",
          "title", "url", "summary", "trigger_at", "display_at", "pillar", "category",
          "subcategory", "subcategory_name", "source", "product_type", "entity_raw", "entity",
          "article_asset_class", "content_type", "entity_source", "entity_confidence",
          "sector", "macro_topic", "importance", "urgency", "role", "mode", "image_url",
          "read_minutes", "auto_grade", "auto_reason_th", "auto_reason_en", "auto_checks",
          "evidence")


def store(con, rows: Iterable[dict], now: str) -> int:
    rows = list(rows)
    if not rows:
        return 0
    with con:
        con.executemany(
            f"""INSERT INTO articles({','.join(FIELDS)}, ingested_at)
                VALUES({','.join('?' * len(FIELDS))}, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                  title=excluded.title, summary=excluded.summary,
                  display_at=excluded.display_at, entity=excluded.entity,
                  entity_source=excluded.entity_source,
                  entity_confidence=excluded.entity_confidence,
                  sector=excluded.sector, macro_topic=excluded.macro_topic,
                  importance=excluded.importance, urgency=excluded.urgency,
                  mode=excluded.mode, ingested_at=excluded.ingested_at,
                  auto_grade=excluded.auto_grade, auto_reason_th=excluded.auto_reason_th,
                  auto_reason_en=excluded.auto_reason_en, auto_checks=excluded.auto_checks,
                  evidence=excluded.evidence""",
            [tuple(r.get(f) for f in FIELDS) + (now,) for r in rows])

        # R3.29 - R3.32 — สะสมความสัมพันธ์หุ้นจาก co-mention พร้อมหลักฐาน
        # R3.29 ระบุว่าใช้ field stock จาก API เท่านั้น ห้ามใช้ entity ที่สกัดเอง
        # ไม่งั้นรายการ TFEX Top Picks (S50 GO USD SVF PTTEP) จะกลายเป็น "หุ้นที่สัมพันธ์กัน"
        for r in rows:
            if r["entity_source"] != "api":
                continue
            ents = sorted(set(db.jload(r["entity"], []) or []))
            if len(ents) < 2:
                continue
            for i, a in enumerate(ents):
                for b in ents[i + 1:]:
                    con.execute(
                        """INSERT INTO entity_pairs(a,b,n,article_ids) VALUES(?,?,1,?)
                           ON CONFLICT(a,b) DO UPDATE SET
                             n = n + 1,
                             article_ids = substr(entity_pairs.article_ids || ',' || excluded.article_ids, 1, 400)""",
                        (a, b, r["article_id"]))

    return len(rows)


def ingest_recent(con, pages: int = 3, limit: int = 100) -> dict:
    """ดึงบทความล่าสุดทั้งเว็บ (R3.15 ใช้ published_date หาของใหม่)"""
    now = dt.datetime.now().isoformat(timespec="seconds")
    uni = universe_from_db(con)
    aliases = build_alias_index()
    funds = fund_codes_from_db(con)
    total_seen, stored, skipped = 0, 0, 0
    api_total = 0
    for page in range(1, pages + 1):
        data, api_total = fetch_page(limit=limit, page=page)
        if not data:
            break
        total_seen += len(data)
        for raw in data:
            sub = _slug(raw.get("sub_category"))
            if sub in DISCONTINUED_SUBCATEGORIES or sub in OUT_OF_SCOPE_SUBCATEGORIES:
                skipped += 1
                continue
            stored += store(con, tag(raw, uni, aliases, funds, con, now), now)
    with con:
        db.set_setting(con, "news_ingested_at", now)
        db.set_setting(con, "news_api_total", api_total)
    # R3.38 ต้องรู้สัดส่วนทั้งคลังถึงจะตัดสินได้ว่าคำไหนกว้างเกิน จึงให้เกรดใหม่หลัง ingest
    regraded = regrade(con, only_missing=False)
    retitle_segments(con)          # ข้อย่อยที่เก็บไว้ก่อนหน้ายังใช้หัวข้อเดิมอยู่
    # เนื้อหาเต็มของข่าวที่เพิ่งเข้ามา — จำกัดจำนวนไว้ กดปุ่มดึงข่าวจะได้ไม่กลายเป็นการไล่โหลดทั้งคลัง
    full = backfill_full_text(con, limit=FULL_TEXT_PER_INGEST)
    # กวาดหุ้นเด่นทั้งคลังอีกรอบ ไม่ใช่เฉพาะที่เพิ่งดึง full_text ในรอบนี้
    # ของจริงที่เจอ: ข่าวได้ full_text ไปแล้วรอบก่อน แต่ตอนนั้นยังสกัดหุ้นเด่นไม่ได้
    # (ตารางชื่อพ้องเพิ่งมีตัวนั้นทีหลัง) แล้วไม่มีอะไรมาไล่ซ้ำให้อีกเลย
    # สแกนเฉพาะบทความที่มี full_text จึงถูกพอที่จะทำทุกรอบ
    picks_all = apply_top_picks(con, now=now)
    # เก็บแค่ช่วงที่ RM ใช้จริง — ถ้าไม่ลบ ทุกงานที่กวาดทั้งตารางจะช้าลงเรื่อย ๆ
    # นับจากวันข่าวล่าสุดในฐาน ไม่ใช่วันนี้ตามนาฬิกา (ดู prune_old)
    pruned = prune_old(con)
    return {"fetched": total_seen, "stored_rows": stored, "skipped_out_of_scope": skipped,
            "api_total": api_total, "grades": regraded["by_grade"],
            "full_text": {"stored": full["stored"], "failed": full["failed"]},
            "top_picks": picks_all,
            "pruned": {"articles": pruned["articles"], "matches": pruned["matches"],
                       "cutoff": pruned["cutoff"]}, "at": now}


def ingest_subcategory(con, subcategory: str, pages: int = 1, limit: int = 60) -> dict:
    """ดึงเฉพาะหมวดย่อย — ใช้กับหมวดสำคัญที่ออกน้อยจนไม่ติดมากับบทความล่าสุด

    เช่น Rebalance Report / Monthly Report ซึ่งเป็นสองหมวดเดียวที่ Fund Robo รับได้ (R6.16)
    """
    now = dt.datetime.now().isoformat(timespec="seconds")
    uni = universe_from_db(con)
    aliases = build_alias_index()
    funds = fund_codes_from_db(con)
    stored, fetched = 0, 0
    for page in range(1, pages + 1):
        data, _ = fetch_page(limit=limit, page=page, subcategory=subcategory)
        if not data:
            break
        fetched += len(data)
        for raw in data:
            stored += store(con, tag(raw, uni, aliases, funds, con, now), now)
    regraded = regrade(con, only_missing=False)
    return {"subcategory": subcategory, "fetched": fetched, "stored_rows": stored,
            "grades": regraded["by_grade"], "at": now}


def universe_from_db(con) -> Universe:
    uni = Universe()
    for r in con.execute("SELECT DISTINCT entity FROM holdings WHERE entity IS NOT NULL"):
        uni.add(r["entity"])
    for r in con.execute("SELECT DISTINCT entity FROM transactions WHERE entity IS NOT NULL"):
        uni.add(r["entity"])
    return uni


def fund_codes_from_db(con) -> set[str]:
    return {r["entity"] for r in con.execute(
        "SELECT DISTINCT entity FROM holdings WHERE entity_kind='fund' AND entity IS NOT NULL")}
