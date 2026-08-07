# -*- coding: utf-8 -*-
"""ตาราง "ตามรอยหุ้นปันผล" จาก INVX Data Book รายเดือน

ทำไมไม่ใช้ AI อ่าน
------------------
ตารางนี้มีรูปแบบตายตัวทุกบรรทัด อ่านด้วยกฎได้ตรง ๆ AI มีไว้อ่านของที่ไม่มีรูปแบบ
(ข่าว) ใช้กับตารางแบบนี้คือเพิ่มโอกาสพลาดฟรี ๆ กับตัวเลขที่ RM เอาไปคุยกับลูกค้า

ด่านตรวจ
--------
ตัวเลขการเงินอ่านผิดแล้วเสียหายจริง (RM ไปบอกลูกค้าว่าจะได้ปันผลเท่าไหร่)
จึงตรวจตัวเลขกันเองก่อนลงฐาน ไม่ต้องเชื่อตัวแกะ:

  1. dps / price ต้องเท่ากับ yield_interim ที่รายงานเขียน
     — สมการเดียวยืนยันสามช่องพร้อมกัน อ่านเพี้ยนช่องไหนก็ไม่ผ่าน
     ค่าคลาดเคลื่อนคิดจากการปัดเศษที่รายงานแสดงจริง ไม่ใช่ค่าคงที่ที่ตั้งเอง
     (SIRI 0.05/1.51 = 3.31% แต่รายงานเขียน 3.0 เพราะ dps จริงคือ ~0.045
      หุ้นราคาถูกคลาดได้เยอะกว่าหุ้นราคาแพงมาก ใช้ค่าคงที่จะตกด่านทั้งที่ถูก)

  2. yield_forecast >= yield_interim — ทั้งปีต้องไม่น้อยกว่างวดเดียว จับกรณีสลับคอลัมน์

  3. remark ต้องเป็น Official หรือ Estimated เท่านั้น — กันบรรทัดที่แกะเลื่อนช่อง

แถวที่ตกด่านไม่ถูกทิ้งเงียบ — คืนออกไปให้ผู้เรียกบันทึกลง unmapped ให้คนดู
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3

from . import news

SUBCATEGORY = "monthly-report"
PAGE_MIN_ROWS = 40          # หน้าตารางจริงมี ~78 แถว ต่ำกว่านี้มากถือว่าแกะพัง

# บรรทัดหนึ่ง: <ตัวย่อ> <ราคา> <คำแนะนำ> แล้วที่เหลือค่อยซอยทีหลัง
# ผูกกับคำแนะนำสามคำนี้เพราะเป็นตัวยืนยันว่าเป็นแถวข้อมูลจริง ไม่ใช่หัวตารางหรือเชิงอรรถ
_ROW = re.compile(
    r"^([A-Z][A-Z0-9&.\-]{1,14})\s+([\d,]+\.?\d*)\s+"
    r"(Outperform|Neutral|Underperform)\s+(.+)$"
)
_MONTH_TH = {"มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5,
             "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10,
             "พฤศจิกายน": 11, "ธันวาคม": 12}


def _round_step(shown: str) -> float:
    """ครึ่งหนึ่งของหน่วยที่เล็กที่สุดที่ตัวเลขนั้น "แสดง" ไว้

    '0.05' แสดงทศนิยม 2 ตำแหน่ง ของจริงจึงอยู่ในช่วง ±0.005
    '0.0219' แสดง 4 ตำแหน่ง ช่วงแคบกว่ามาก — ต้องอ่านจากสตริง ไม่ใช่เดาเอา
    """
    return 10 ** -len(shown.split(".")[1]) / 2 if "." in shown else 0.5


def parse_page(text: str) -> tuple[list[dict], list[dict]]:
    """แกะข้อความหนึ่งหน้า -> (แถวที่ผ่านด่าน, แถวที่ตกด่านพร้อมเหตุผล)"""
    rows: list[dict] = []
    bad: list[dict] = []
    for raw in text.split("\n"):
        m = _ROW.match(raw.strip())
        if not m:
            continue
        tic, price_s, rating, rest = m.groups()
        f = rest.split()
        if len(f) < 6:
            bad.append({"entity": tic, "why": "ช่องไม่ครบ", "line": raw.strip()})
            continue

        # นับจากซ้าย 4 ช่อง นับจากขวา 2 ช่อง ที่เหลือตรงกลางคือ "ผลดำเนินงาน"
        # ซึ่งมีเว้นวรรคได้ (เช่น "Apr 26 - Sep 26") จึงนับปลายทั้งสองด้านแทนการ split ตรง ๆ
        dps_s, yint_s, xd, pay = f[0], f[1], f[2], f[3]
        remark, fc_s = f[-1], f[-2]
        period = " ".join(f[4:-2])
        try:
            price = float(price_s.replace(",", ""))
            dps, y_int, y_fc = float(dps_s), float(yint_s), float(fc_s)
        except ValueError:
            bad.append({"entity": tic, "why": "ตัวเลขอ่านไม่ออก", "line": raw.strip()})
            continue

        if remark not in ("Official", "Estimated"):
            bad.append({"entity": tic, "why": f"remark ผิดรูป: {remark}", "line": raw.strip()})
            continue
        if price <= 0:
            bad.append({"entity": tic, "why": "ราคาเป็นศูนย์", "line": raw.strip()})
            continue

        calc = dps / price * 100
        tol = _round_step(yint_s) + _round_step(dps_s) / price * 100
        if abs(calc - y_int) > tol:
            bad.append({"entity": tic, "line": raw.strip(),
                        "why": f"dps/ราคา = {calc:.2f}% ไม่ตรงกับ {y_int}% ที่รายงานเขียน"})
            continue
        if y_fc < y_int:
            bad.append({"entity": tic, "line": raw.strip(),
                        "why": f"69F {y_fc}% น้อยกว่างวดนี้ {y_int}% — คอลัมน์อาจสลับ"})
            continue

        rows.append({"entity": tic, "price": price, "rating": rating, "dps": dps,
                     "yield_interim": y_int, "xd_date": xd, "pay_date": pay,
                     "period": period, "yield_forecast": y_fc, "remark": remark,
                     "source_line": raw.strip()})
    return rows, bad


def parse_pdf(pdf_bytes: bytes) -> tuple[list[dict], list[dict], str | None]:
    """หาหน้า "ตามรอยหุ้นปันผล" ใน PDF แล้วแกะ -> (ผ่าน, ตก, วันที่ข้อมูล)

    ต้อง import pypdf ในฟังก์ชัน — งานนี้รันเดือนละครั้ง ไม่ใช่ runtime หลัก
    จึงไม่บังคับให้ทุกเครื่องที่รัน API ต้องมี pypdf (แพตเทิร์นเดียวกับ news.py)
    """
    import io

    from pypdf import PdfReader

    best: tuple[list[dict], list[dict]] = ([], [])
    as_of = None
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        text = page.extract_text() or ""
        rows, bad = parse_page(text)
        # ตารางปันผลกระจายอยู่หน้าเดียว เลือกหน้าที่แกะได้มากสุดแทนการยึดเลขหน้า
        # (เลขหน้าขยับได้ทุกเดือนตามเนื้อหาที่เพิ่ม/ลด)
        if len(rows) > len(best[0]):
            best = (rows, bad)
            m = re.search(r"INVX\s+(\d{1,2}\s+[ก-๙.]+\s+\d{2})", text)
            as_of = m.group(1) if m else None
    return best[0], best[1], as_of


def _month_from_title(title: str) -> str:
    """'INVX Data Book - เดือนสิงหาคม 2569' -> '2026-08' (พ.ศ. -> ค.ศ.)"""
    m = re.search(r"เดือน\s*([ก-๙]+)\s*(\d{4})", title or "")
    if not m or m.group(1) not in _MONTH_TH:
        return dt.date.today().strftime("%Y-%m")
    return f"{int(m.group(2)) - 543:04d}-{_MONTH_TH[m.group(1)]:02d}"


def fetch_latest() -> tuple[list[dict], list[dict], dict]:
    """ดึง Data Book เดือนล่าสุดจาก Cafe Invest แล้วแกะตารางปันผล

    คืน (ผ่านด่าน, ตกด่าน, ข้อมูลต้นทาง) — ล้มเหลวจุดไหน raise RuntimeError
    พร้อมบอกว่าพังตรงไหน ผู้เรียกเอาไปแสดงบนหน้าจอได้เลย
    """
    data, _ = news.fetch_page(limit=1, page=1, subcategory=SUBCATEGORY)
    if not data:
        raise RuntimeError(f"ไม่พบบทความในหมวด {SUBCATEGORY}")
    art = data[0]
    page_url = news.article_url(art.get("url") or "")
    if not page_url:
        raise RuntimeError("บทความไม่มี url")

    r = news._session.get(page_url, headers={**news.HEADERS, "Accept": "text/html"}, timeout=30)
    r.raise_for_status()
    m = news._PDF_URL_RE.search(news._rsc_stream(r.text))
    if not m:
        raise RuntimeError("ไม่พบ pdf_url ในหน้าบทความ — โครงสร้างหน้าเว็บอาจเปลี่ยน")

    pdf_url = m.group(1)
    pr = news._session.get(pdf_url, headers=news.HEADERS, timeout=60)
    pr.raise_for_status()
    rows, bad, as_of = parse_pdf(pr.content)
    if len(rows) < PAGE_MIN_ROWS:
        raise RuntimeError(f"แกะได้แค่ {len(rows)} แถว ต่ำกว่าที่ควรมาก "
                           f"— โครงสร้าง PDF อาจเปลี่ยน (ไม่บันทึกทับของเดิม)")

    src = {"title": art.get("title") or "", "published_date": art.get("published_date"),
           "report_month": _month_from_title(art.get("title") or ""),
           "as_of": as_of, "pdf_url": pdf_url, "page_url": page_url}
    return rows, bad, src


# ==========================================================================
# สไตล์พอร์ต — ปันผลหรือเก็งกำไร
# ==========================================================================
#
# สองแกน ไม่ใช่ตัวเลขเดียว:
#   แกนตั้ง  yield ทั้งปีของพอร์ต (ถ่วงน้ำหนักด้วยมูลค่าที่ถือ)
#   แกนนอน  ความถี่เทรด — ใช้ trade_frequency ที่คำนวณไว้แล้วตอน ingest ลูกค้า
#
# ทำไมต้องมี "ไม่รู้"
# ------------------
# Data Book ครอบคลุมแค่หุ้นไทย แต่ลูกค้าส่วนใหญ่เป็น US_OFFSHORE
# ของจริง: มีลูกค้าถือ holdings 1057 คน แต่แตะหุ้นในรายงานเกิน 30% แค่ 110 คน
# ถ้าแปะป้ายให้ทุกคนจะได้ "เก็งกำไร" เกลื่อนจอ ทั้งที่ความจริงคือเราไม่มีข้อมูลปันผล
# ของสิ่งที่เขาถือ — คนละเรื่องกับการรู้ว่าเขาถือของที่ไม่จ่ายปันผล
COVERAGE_MIN = 0.30

STYLES = {
    "income":     {"th": "นักลงทุนปันผล",     "en": "income"},
    "div_trader": {"th": "เก็บปันผลแบบเทรด",  "en": "dividend trader"},
    "growth":     {"th": "ถือยาวหวังราคา",    "en": "growth"},
    "speculate":  {"th": "เก็งกำไร",          "en": "speculative"},
    "unknown":    {"th": "ยังบอกไม่ได้",      "en": "unknown"},
}
_ACTIVE = ("very_active", "active")


def _label(y_port: float | None, coverage: float, freq: str, median: float) -> str:
    if y_port is None or coverage < COVERAGE_MIN:
        return "unknown"
    hot = freq in _ACTIVE
    return ("div_trader" if hot else "income") if y_port >= median \
        else ("speculate" if hot else "growth")


def styles(con: sqlite3.Connection, customer_key: str | None = None,
           month: str | None = None) -> list[dict]:
    """สไตล์พอร์ตรายคน — ส่ง customer_key มาก็ได้คนเดียว

    เส้นแบ่ง "yield สูง/ต่ำ" ใช้ค่ากลางของฐานลูกค้าเองที่คำนวณสด ไม่ใช่เลขที่ตั้งเอง
    — อธิบายได้ว่า "สูงกว่าครึ่งหนึ่งของลูกค้าที่วัดได้" และขยับตามพอร์ตจริงเมื่อของเปลี่ยน
    """
    month = month or (con.execute(
        "SELECT MAX(report_month) FROM dividends").fetchone() or [None])[0]
    if not month:
        return []

    rows = [dict(r) for r in con.execute("""
        SELECT h.customer_key, c.rm_id, c.persona, c.trade_frequency, c.portfolio_value,
               SUM(CASE WHEN d.entity IS NOT NULL THEN h.holding_value ELSE 0 END) AS covered,
               SUM(h.holding_value)                                                AS total,
               SUM(COALESCE(d.yield_forecast, 0) * h.holding_value) / 100          AS annual,
               SUM(COALESCE(d.yield_interim, 0) * h.holding_value) / 100           AS interim
        FROM holdings h
        JOIN customers c USING (customer_key)
        LEFT JOIN dividends d ON d.entity = h.entity AND d.report_month = ?
        GROUP BY h.customer_key""", (month,))]

    for r in rows:
        r["coverage"] = r["covered"] / r["total"] if r["total"] else 0.0
        # หารด้วย "มูลค่าที่มีข้อมูล" ไม่ใช่ทั้งพอร์ต — ไม่งั้นพอร์ตที่ครอบคลุม 20%
        # จะโชว์ yield ต่ำเทียมทั้งที่ของที่วัดได้อาจให้ปันผลสูง จึงต้องคู่กับ coverage เสมอ
        r["yield_portfolio"] = (r["annual"] / r["covered"] * 100) if r["covered"] else None

    ok = sorted(r["yield_portfolio"] for r in rows
                if r["yield_portfolio"] is not None and r["coverage"] >= COVERAGE_MIN)
    median = ok[len(ok) // 2] if ok else 0.0

    for r in rows:
        r["style"] = _label(r["yield_portfolio"], r["coverage"], r["trade_frequency"] or "", median)
        r["median_yield"] = median
        r["month"] = month
    if customer_key:
        return [r for r in rows if r["customer_key"] == customer_key]
    return rows


def store(con: sqlite3.Connection, rows: list[dict], src: dict) -> int:
    """เขียนทับเดือนเดียวกัน — ดึงซ้ำได้ ไม่เกิดของซ้อน"""
    now = dt.datetime.now().isoformat(timespec="seconds")
    with con:
        con.executemany("""
            INSERT INTO dividends (entity, report_month, price, rating, dps, yield_interim,
                                   xd_date, pay_date, period, yield_forecast, remark,
                                   as_of, source_url, source_line, ingested_at)
            VALUES (:entity, :report_month, :price, :rating, :dps, :yield_interim,
                    :xd_date, :pay_date, :period, :yield_forecast, :remark,
                    :as_of, :source_url, :source_line, :ingested_at)
            ON CONFLICT(entity, report_month) DO UPDATE SET
                price=excluded.price, rating=excluded.rating, dps=excluded.dps,
                yield_interim=excluded.yield_interim, xd_date=excluded.xd_date,
                pay_date=excluded.pay_date, period=excluded.period,
                yield_forecast=excluded.yield_forecast, remark=excluded.remark,
                as_of=excluded.as_of, source_url=excluded.source_url,
                source_line=excluded.source_line, ingested_at=excluded.ingested_at
        """, [{**r, "report_month": src["report_month"], "as_of": src.get("as_of"),
               "source_url": src.get("pdf_url"), "ingested_at": now} for r in rows])
    return len(rows)


def ingest(con: sqlite3.Connection) -> dict:
    """ดึง + แกะ + ตรวจ + บันทึก ครบในคำสั่งเดียว (ตัวที่ปุ่มบนหน้าจอเรียก)"""
    from . import db as _db

    rows, bad, src = fetch_latest()
    stored = store(con, rows, src)
    now = dt.datetime.now().isoformat(timespec="seconds")

    # แถวที่ตกด่านต้องมีคนเห็น ไม่ใช่หายเงียบ — ช่องทางเดียวกับของที่ระบบอ่านไม่ออกอยู่แล้ว
    with con:
        for b in bad:
            _db.report_unmapped(con, "dividend", f"{b['entity']} — {b['why']}", "DIV-01",
                                "แถวในตารางปันผลไม่ผ่านด่านตรวจตัวเลข จึงไม่ถูกบันทึก",
                                ref=src.get("pdf_url") or "", now=now)
        _db.set_setting(con, "dividends_ingested_at", now)
    return {"report_month": src["report_month"], "title": src["title"],
            "as_of": src.get("as_of"), "stored": stored, "rejected": len(bad),
            "rejected_rows": bad[:20], "at": now}
