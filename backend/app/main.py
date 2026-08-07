# -*- coding: utf-8 -*-
"""FastAPI — News-Customer Matching

หน้าจอ RM เป็นแบบ news-centric ตาม STEP7: เปิดข่าว 1 ชิ้นเห็นรายชื่อลูกค้าที่ควรติดต่อ
ผลการจับคู่ถูกคำนวณล่วงหน้าตอน ingest แล้วเก็บในตาราง matches จึงเปิดหน้าได้เร็ว
"""
from __future__ import annotations

import datetime as dt
import tempfile
import traceback
from pathlib import Path
from typing import Literal

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import briefing, db, dividends, enrich, llm, mailer, matching, news, prices, symbols
from . import upload as uploader
from . import ingest_customers as ingest
from .mapping import coverage_of, refdata
from .tables import (
    RETENTION_DAYS,
    LEVEL_WEIGHT,
    OVERRIDE_COUNTS,
    PERSONA_LABELS,
    SCORE_THRESHOLD,
    SEVERITY_ORDER,
    SPEC_GAPS,
    UNMAPPED_NEW_DAYS,
    UNMAPPED_SEVERITY,
    UNMAPPED_SEVERITY_FALLBACK,
)

app = FastAPI(title="News-Customer Matching", version="1.0",
              description="INVX — จับคู่บทความ Cafe Invest กับลูกค้า ส่งรายชื่อให้ RM")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
# คู่มือ mask — ผู้ใช้โหลดจากหน้าเว็บไปแนบให้ Copilot พร้อมไฟล์ Portfolio + TXN
MASK_GUIDE = (Path(__file__).resolve().parents[2] / "memie"
              / "วิธี mask ด้วย Copilot บนเว็บ.md")


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


@app.middleware("http")
async def log_unhandled(request, call_next):
    """เก็บ traceback ของ 500 ลงไฟล์ — หน้าต่างคอนโซลปิดไปแล้วก็ยังตามอ่านได้"""
    try:
        return await call_next(request)
    except Exception:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with (LOG_DIR / "errors.log").open("a", encoding="utf-8") as f:
                f.write(f"\n=== {dt.datetime.now().isoformat(timespec='seconds')} "
                        f"{request.method} {request.url.path}\n")
                traceback.print_exc(file=f)
        except OSError:
            pass
        raise


@app.on_event("startup")
def _startup() -> None:
    db.init()


def con():
    return db.connect()


def rows(sql: str, params: tuple | list = ()) -> list[dict]:
    c = con()
    try:
        return [dict(r) for r in c.execute(sql, params)]
    finally:
        c.close()


def one(sql: str, params: tuple | list = ()) -> dict | None:
    r = rows(sql, params)
    return r[0] if r else None


def _within(stamp: str | None, ref: dt.date, days: int) -> bool:
    """เจอครั้งแรกภายใน N วันไหม — first_seen เก็บเป็น ISO timestamp ตัดเอาแค่วันที่"""
    if not stamp:
        return False
    try:
        return 0 <= (ref - dt.date.fromisoformat(str(stamp)[:10])).days <= days
    except ValueError:
        return False


# ==========================================================================
# สถานะระบบ
# ==========================================================================

@app.get("/api/health")
def health() -> dict:
    c = con()
    try:
        g = lambda k, d=None: db.get_setting(c, k, d)  # noqa: E731
        n = lambda sql: c.execute(sql).fetchone()[0]   # noqa: E731
        data_as_of = g("data_as_of")
        lag = None
        if data_as_of:
            lag = (dt.date.today() - dt.date.fromisoformat(data_as_of)).days
        return {
            "customers": n("SELECT COUNT(*) FROM customers"),
            "holdings": n("SELECT COUNT(*) FROM holdings"),
            "transactions": n("SELECT COUNT(*) FROM transactions"),
            "articles": n("SELECT COUNT(*) FROM articles WHERE record_type='article'"),
            "segments": n("SELECT COUNT(*) FROM articles WHERE record_type='segment'"),
            "matches": n("SELECT COUNT(*) FROM matches"),
            "unmapped": n("SELECT COALESCE(SUM(n),0) FROM unmapped"),
            "weak_evidence": n("SELECT COUNT(*) FROM articles WHERE auto_grade='weak'"),
            # R1.14 / R2.8 — ต้องบอก RM ว่าข้อมูลสดแค่ไหน ห้ามให้เข้าใจผิดว่าเป็นของวันนี้
            "customer_data_as_of": data_as_of,
            "customer_data_lag_days": lag,
            "holdings_as_of": g("holdings_as_of"),
            # ช่วงเวลาที่ไฟล์ที่อัปโหลดครอบคลุมจริง — ต่างจาก "นำเข้าเมื่อไหร่"
            # ไฟล์ที่เพิ่งอัปโหลดเมื่อวานอาจมีข้อมูลถึงแค่เดือนที่แล้วก็ได้ ต้องแยกให้เห็น
            "txn_from": n("SELECT MIN(txn_date) FROM transactions"),
            "txn_to": n("SELECT MAX(txn_date) FROM transactions"),
            "customers_ingested_at": g("customers_ingested_at"),
            "news_ingested_at": g("news_ingested_at"),
            "news_api_total": g("news_api_total"),
            "dividends_ingested_at": g("dividends_ingested_at"),
            "matched_at": g("matched_at"),
            "score_threshold": SCORE_THRESHOLD,          # R6.14 ค่าคงที่
            "persona_counts": g("persona_counts", {}),
            "overrides": OVERRIDE_COUNTS,
            "alerts": _alerts(c),
        }
    finally:
        c.close()


def _alerts(c) -> list[dict]:
    """สิ่งที่คนดูแลระบบควรถูกบอก ไม่ใช่ต้องไปเปิดหาเอง

    ตาราง unmapped มีมาตั้งแต่แรก แต่ไม่มีอะไรส่งเสียง — หมวดข่าวใหม่ที่ระบบ
    ไม่รู้จักจึงหายไปเงียบ ๆ ได้เป็นเดือน (R3.16 ข้ามทั้งบทความ) ฟังก์ชันนี้
    ยกเฉพาะเรื่องที่ต้องลงมือ ขึ้นเป็นแถบเตือนบนหัวจอทุกหน้า
    """
    out: list[dict] = []
    today = dt.date.today()

    # 1. หมวดใหม่ที่ไม่รู้จัก — ร้ายแรงที่สุด เพราะทิ้งทั้งหมวด ไม่ใช่แค่บางแถว
    unknown_subs = [dict(r) for r in c.execute(
        "SELECT raw, n, first_seen FROM unmapped WHERE bucket='subcategory' ORDER BY n DESC")]
    if unknown_subs:
        names = ", ".join(r["raw"] for r in unknown_subs[:3])
        out.append({
            "level": "high", "kind": "unknown_subcategory", "n": len(unknown_subs),
            "th": f"มีหมวดข่าวที่ระบบไม่รู้จัก {len(unknown_subs)} หมวด ({names}) "
                  f"— บทความทั้งหมวดถูกข้ามไป ยังไม่มีใครได้รับ",
            "en": f"{len(unknown_subs)} unknown content categories ({names}) — "
                  f"every article in them is being skipped",
            "to": "/reports",
        })

    # 2. ของใหม่ที่เพิ่งโผล่ — first_seen มีอยู่แล้วในตาราง แค่ไม่เคยมีใครอ่าน
    #    report_unmapped ใช้ upsert ที่รักษา first_seen ไว้ ปัญหาเดิมจึงไม่ถูกนับใหม่
    #    ทุกรอบ ingest — "ใหม่" หมายถึงเพิ่งโผล่จริง ๆ
    rows_ = [dict(r) for r in c.execute(
        "SELECT bucket, raw, first_seen FROM unmapped WHERE bucket <> 'subcategory'")]
    oldest = min((str(r["first_seen"] or "9999") for r in rows_), default="9999")
    fresh = [r for r in rows_ if _within(r["first_seen"], today, UNMAPPED_NEW_DAYS)]
    # ถ้าแถวที่เก่าที่สุดก็ยังอยู่ในกรอบเวลา แปลว่าฐานข้อมูลเพิ่งสร้าง ไม่ใช่มีของใหม่โผล่
    # จะบอกว่า "พบ 280 รายการใหม่" ก็เข้าใจผิดว่าเพิ่งเกิดปัญหาพรวดเดียว
    young_db = _within(oldest, today, UNMAPPED_NEW_DAYS)
    if fresh and not young_db:
        worst = min((UNMAPPED_SEVERITY.get(r["bucket"], UNMAPPED_SEVERITY_FALLBACK)[0]
                     for r in fresh), key=lambda s: SEVERITY_ORDER.get(s, 9))
        out.append({
            "level": worst if worst != "low" else "info", "kind": "new_unmapped",
            "n": len(fresh),
            "th": f"พบสิ่งที่อ่านไม่ออก {len(fresh)} รายการใหม่ใน {UNMAPPED_NEW_DAYS} วันที่ผ่านมา",
            "en": f"{len(fresh)} new unreadable items in the last {UNMAPPED_NEW_DAYS} days",
            "to": "/reports",
        })

    # 3. ข้อมูลลูกค้าเก่าเกิน 7 วัน (R1.14) — เดิมมีแต่ข้อความจาง ๆ บนหัวจอ
    as_of = db.get_setting(c, "data_as_of")
    if as_of:
        try:
            lag = (today - dt.date.fromisoformat(as_of)).days
        except ValueError:
            lag = None
        if lag is not None and lag > 7:
            out.append({
                "level": "medium", "kind": "stale_customer_data", "n": lag,
                "th": f"ข้อมูลลูกค้าเก่า {lag} วันแล้ว — รายชื่อที่ได้อาจไม่ตรงพอร์ตปัจจุบัน",
                "en": f"Customer data is {lag} days old — the lists may not match current portfolios",
                "to": "/upload",
            })

    return sorted(out, key=lambda a: SEVERITY_ORDER.get(a["level"], 9))


@app.get("/api/spec-gaps")
def spec_gaps() -> dict:
    """ช่องว่างของ spec ที่ระบบเติมค่าเอง — ต้องเห็นบนหน้าจอ ห้ามเงียบ"""
    gaps = sorted(SPEC_GAPS, key=lambda g: g["id"])
    return {"gaps": gaps, "n": len(gaps)}


@app.get("/api/reference")
def reference() -> dict:
    rd = refdata()
    return {
        "levels": LEVEL_WEIGHT,
        "personas": {k: {"th": v[0], "en": v[1]} for k, v in PERSONA_LABELS.items()},
        "sectors": sorted({v["sector"] for v in rd["thai_sector"].values()}),
        "coverage_list_size": len(rd["thai_sector"]),
        "dr_resolved": len(rd["dr_parent"]),
        "dr_pending": len(rd["dr_pending"]),
        "content_inventory": rd["content_inventory"],
        "macro_topics": {k: v for k, v in rd["macro_keywords"].items()},
        "macro_banned": rd["macro_banned"],
    }


# ==========================================================================
# STEP7 — จังหวะรายวันของ RM
# ==========================================================================

SLOT_SQL = """
CASE
  WHEN a.mode='realtime' THEN 'intraday'
  WHEN CAST(substr(a.trigger_at,12,2) AS INTEGER) < 12 THEN 'morning'
  ELSE 'evening'
END"""


@app.get("/api/today")
def today(date: str | None = None, rm: str | None = None) -> dict:
    """รอบเช้า / ระหว่างวัน / เย็น ตาม STEP7 ชีตจังหวะรายวัน

    R3.15 — ยึด published_date (trigger_at) เป็นตัวบอกว่าบทความเป็นของวันไหน
    ห้ามใช้ displayed_date เพราะ 150 จาก 837 บทความมีสองค่านี้คนละวัน
    ค่าเริ่มต้นคือวันนี้จริง ไม่ใช่วันล่าสุดที่มีข่าว — วันไม่มีข่าว หน้าจอว่างได้ (STEP7 ข้อ 7)
    """
    real_today = dt.date.today().isoformat()
    day = date or real_today
    args: list = [day]
    join = ""
    if rm:
        join = "AND EXISTS (SELECT 1 FROM matches m WHERE m.article_id=a.article_id AND m.rm_id=?)"
        args.append(rm)
    arts = rows(f"""
        SELECT a.article_id, a.record_type, a.parent_article_id, a.segment_no, a.title, a.url,
               a.subcategory, a.subcategory_name, a.content_type, a.mode, a.importance, a.urgency,
               a.trigger_at, a.display_at, a.entity, a.sector, a.macro_topic, a.image_url,
               a.entity_confidence, a.auto_grade, a.n_matches,
               a.ai_direction, a.ai_at, a.ai_reason_th, a.ai_reason, {SLOT_SQL} AS slot
        FROM articles a
        WHERE substr(a.trigger_at,1,10)=? AND a.role='content'
          AND NOT (a.record_type='article' AND a.subcategory IN ('morning-brief','evening-brief'))
          {join}
        ORDER BY a.importance DESC, a.n_matches DESC, a.trigger_at DESC""", args)
    buckets: dict[str, list] = {"morning": [], "intraday": [], "evening": []}
    for a in arts:
        buckets[a.pop("slot")].append(a)
    latest = one("""SELECT substr(trigger_at,1,10) d FROM articles
                    WHERE role='content' ORDER BY trigger_at DESC LIMIT 1""") or {}
    return {"date": day, "today": real_today, "is_today": day == real_today, "rm_id": rm,
            "latest_with_news": latest.get("d"),
            "counts": {k: len(v) for k, v in buckets.items()},
            "total_matches": sum(a["n_matches"] for a in arts),
            "buckets": buckets}


@app.get("/api/dates")
def dates(limit: int = 30) -> list[dict]:
    return rows("""SELECT substr(trigger_at,1,10) d, COUNT(*) articles,
                          SUM(n_matches) matches
                   FROM articles WHERE role='content' AND record_type<>'segment'
                   GROUP BY 1 ORDER BY 1 DESC LIMIT ?""", (limit,))


# ==========================================================================
# บทความ
# ==========================================================================

@app.get("/api/articles")
def articles(q: str | None = None, mode: str | None = None, subcategory: str | None = None,
             content_type: str | None = None, rm: str | None = None,
             date_from: str | None = None, date_to: str | None = None,
             has_matches: bool | None = None, record_type: str | None = None,
             sort: Literal["recent", "matches", "importance"] = "recent",
             limit: int = Query(50, le=500), offset: int = 0) -> dict:
    where = ["a.role='content'",
             "NOT (a.record_type='article' AND a.subcategory IN ('morning-brief','evening-brief'))"]
    args: list = []
    if q:
        where.append("(a.title LIKE ? OR a.entity LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    for col, val in (("a.mode", mode), ("a.subcategory", subcategory),
                     ("a.content_type", content_type), ("a.record_type", record_type)):
        if val:
            where.append(f"{col}=?")
            args.append(val)
    if date_from:
        where.append("substr(a.trigger_at,1,10)>=?")
        args.append(date_from)
    if date_to:
        where.append("substr(a.trigger_at,1,10)<=?")
        args.append(date_to)
    if has_matches:
        where.append("a.n_matches>0")
    if rm:
        where.append("EXISTS (SELECT 1 FROM matches m WHERE m.article_id=a.article_id AND m.rm_id=?)")
        args.append(rm)

    order = {"recent": "a.trigger_at DESC",
             "matches": "a.n_matches DESC, a.trigger_at DESC",
             "importance": "a.importance DESC, a.trigger_at DESC"}[sort]
    w = " AND ".join(where)
    total = one(f"SELECT COUNT(*) c FROM articles a WHERE {w}", args)["c"]
    items = rows(f"""
        SELECT a.article_id, a.record_type, a.parent_article_id, a.segment_no, a.title, a.url,
               a.subcategory, a.subcategory_name, a.content_type, a.mode, a.importance, a.urgency,
               a.trigger_at, a.display_at, a.entity, a.sector, a.macro_topic, a.image_url,
               a.entity_source, a.entity_confidence, a.auto_grade, a.auto_reason_th,
               a.auto_reason_en, a.n_matches,
               a.ai_direction, a.ai_at, a.ai_reason_th, a.ai_reason
        FROM articles a WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?""", args + [limit, offset])
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/api/articles/{article_id}")
def article(article_id: str) -> dict:
    a = one("SELECT * FROM articles WHERE article_id=?", (article_id,))
    if not a:
        raise HTTPException(404, "ไม่พบบทความ")
    # field url จาก API เป็น path ที่ตัด /cafeinvest ออกแล้ว ต่อโดเมนตรง ๆ จะ 404
    a["url_full"] = news.article_url(a.get("url"))
    a["segments"] = rows(
        """SELECT article_id, segment_no, segment_text, entity, sector, macro_topic, n_matches
           FROM articles WHERE parent_article_id=? ORDER BY segment_no""", (article_id,))
    a["level_summary"] = rows(
        "SELECT level, COUNT(*) n, ROUND(AVG(score),1) avg_score FROM matches "
        "WHERE article_id=? GROUP BY 1 ORDER BY 1", (article_id,))
    a["rm_summary"] = rows(
        "SELECT rm_id, COUNT(*) n FROM matches WHERE article_id=? GROUP BY 1 ORDER BY n DESC",
        (article_id,))
    a["persona_summary"] = rows(
        "SELECT persona, COUNT(*) n FROM matches WHERE article_id=? GROUP BY 1 ORDER BY n DESC",
        (article_id,))
    if a["parent_article_id"]:
        a["parent"] = one("SELECT article_id, title, url FROM articles WHERE article_id=?",
                          (a["parent_article_id"],))
    return a


@app.get("/api/articles/{article_id}/briefing")
def article_briefing(article_id: str) -> dict:
    """GAP-22 — ทิศทางข่าวที่มีแหล่งอ้างอิง + ประเด็นที่ควรคุย (รวม ไม่ใช่รายคน)"""
    c = con()
    try:
        row = c.execute("SELECT * FROM articles WHERE article_id=?", (article_id,)).fetchone()
        if not row:
            raise HTTPException(404, "ไม่พบบทความ")
        return briefing.briefing(c, dict(row))
    finally:
        c.close()


@app.get("/api/articles/{article_id}/matches")
def article_matches(article_id: str, rm: str | None = None, persona: str | None = None,
                    level: str | None = None, tier: str | None = None,
                    limit: int = Query(100, le=1000), offset: int = 0) -> dict:
    where, args = ["m.article_id=?"], [article_id]
    for col, val in (("m.rm_id", rm), ("m.persona", persona), ("m.level", level),
                     ("c.portfolio_tier", tier)):
        if val:
            where.append(f"{col}=?")
            args.append(val)
    w = " AND ".join(where)
    total = one(f"SELECT COUNT(*) c FROM matches m JOIN customers c USING(customer_key) WHERE {w}",
                args)["c"]
    items = rows(f"""
        SELECT m.customer_key, m.rm_id, m.persona, m.level, m.matched_entity, m.score,
               m.reason_th, m.reason_en, m.instrument_label, m.holding_value, m.evidence,
               c.portfolio_value, c.portfolio_tier, c.trade_frequency, c.days_since_last_trade,
               c.unrealized_state, c.n_holdings, c.n_watchlist
        FROM matches m JOIN customers c USING(customer_key)
        WHERE {w} ORDER BY m.score DESC LIMIT ? OFFSET ?""", args + [limit, offset])
    return {"total": total, "limit": limit, "offset": offset, "items": items}


# ==========================================================================
# ลูกค้า
# ==========================================================================

@app.get("/api/customers")
def customers(persona: str | None = None, rm: str | None = None, tier: str | None = None,
              q: str | None = None, sort: Literal["value", "matches", "recent"] = "value",
              limit: int = Query(50, le=500), offset: int = 0) -> dict:
    where, args = ["1=1"], []
    for col, val in (("persona", persona), ("rm_id", rm), ("portfolio_tier", tier)):
        if val:
            where.append(f"c.{col}=?")
            args.append(val)
    if q:
        where.append("(c.customer_key LIKE ? OR c.holdings LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    w = " AND ".join(where)
    total = one(f"SELECT COUNT(*) c FROM customers c WHERE {w}", args)["c"]
    order = {"value": "c.portfolio_value DESC", "matches": "n_matches DESC",
             "recent": "c.days_since_last_trade ASC"}[sort]
    items = rows(f"""
        SELECT c.customer_key, c.rm_id, c.persona, c.dominant_asset_class, c.portfolio_value,
               c.portfolio_tier, c.trade_frequency, c.days_since_last_trade, c.txn_count,
               c.unrealized_state, c.n_holdings, c.n_watchlist,
               (SELECT COUNT(*) FROM matches m WHERE m.customer_key=c.customer_key) n_matches
        FROM customers c WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?""", args + [limit, offset])
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/api/customers/{customer_key}")
def customer(customer_key: str) -> dict:
    c = one("SELECT * FROM customers WHERE customer_key=?", (customer_key,))
    if not c:
        raise HTTPException(404, "ไม่พบลูกค้า")
    c["holding_rows"] = rows("""
        SELECT product_code, asset_class, entity, entity_kind, instrument_label, map_rule,
               holding_value, unrealized_pnl, as_of_date
        FROM holdings WHERE customer_key=? ORDER BY holding_value DESC""", (customer_key,))
    c["recent_txn"] = rows("""
        SELECT txn_date, txn_type, txn_direction, product_code, entity, asset_class,
               txn_units, txn_value
        FROM transactions WHERE customer_key=? AND txn_direction<>'IGNORE'
        ORDER BY txn_date DESC LIMIT 40""", (customer_key,))
    c["matches"] = rows("""
        SELECT m.article_id, m.level, m.score, m.matched_entity, m.reason_th, m.reason_en,
               a.title, a.url, a.subcategory, a.trigger_at, a.importance, a.urgency
        FROM matches m JOIN articles a USING(article_id)
        WHERE m.customer_key=? ORDER BY m.score DESC LIMIT 50""", (customer_key,))

    cc = con()
    try:
        st = dividends.styles(cc, customer_key=customer_key)
        c["style"] = st[0] if st else None
        # หุ้นปันผลที่เขาถือจริง เรียงตามเงินที่จะได้ — เป็นตัวหนุนป้ายสไตล์ ไม่ใช่กล่องดำ
        c["dividend_rows"] = [dict(r) for r in cc.execute("""
            SELECT h.entity, h.holding_value, d.yield_interim, d.yield_forecast,
                   d.xd_date, d.pay_date, d.rating, d.remark,
                   h.holding_value * d.yield_interim / 100 AS dividend
            FROM holdings h
            JOIN dividends d ON d.entity = h.entity
                            AND d.report_month = (SELECT MAX(report_month) FROM dividends)
            WHERE h.customer_key = ? ORDER BY dividend DESC""", (customer_key,))]
    finally:
        cc.close()
    return c


# ==========================================================================
# มุมมอง RM
# ==========================================================================

@app.get("/api/rms")
def rms() -> list[dict]:
    return rows("""
        SELECT c.rm_id,
               COUNT(*) customers,
               ROUND(SUM(c.portfolio_value)/1e6,1) aum_mb,
               (SELECT COUNT(*) FROM matches m WHERE m.rm_id=c.rm_id) matches,
               (SELECT COUNT(DISTINCT m.article_id) FROM matches m WHERE m.rm_id=c.rm_id) articles
        FROM customers c WHERE c.rm_id<>'' GROUP BY 1 ORDER BY 1""")


@app.get("/api/rm/{rm_id}/queue")
def rm_queue(rm_id: str, date: str | None = None, sort: str = Query("value"),
             limit: int = Query(200, le=1000)) -> dict:
    """ลูกค้าที่ RM ควรโทร — เรียงตาม "เงินที่ข่าวไปแตะ" เป็นค่าเริ่มต้น

    ทำไมไม่เรียงตามคะแนน: คะแนนบอกว่าข่าวเกี่ยวกับเขาแรงแค่ไหน แต่ไม่บอกว่าคุยแล้วได้เท่าไร
    ลูกค้าคะแนน 51 ที่ถือของตัวนั้น 31 ลบ. คุ้มกว่าคะแนน 540 ที่ถือ 3 แสน
    สลับไปเรียงตามคะแนนได้ด้วย sort=score

    มูลค่าต้องรวมแบบไม่นับซ้ำ — ลูกค้าคนเดียวถือ NVDA อยู่ก้อนเดียว แต่ถ้าวันนั้นมีข่าว
    ถึง NVDA สามชิ้น การรวมตรง ๆ จะได้สามเท่า (เคยเห็นยอดโผล่เกินมูลค่าพอร์ตทั้งใบ)
    จึงยุบเป็นรายหุ้นก่อนด้วย MAX แล้วค่อยรวมข้ามหุ้น
    """
    day, args = "", [rm_id]
    if date:
        day = "AND substr(a.trigger_at,1,10)=?"
        args.append(date)
    order = "top_score DESC, matched_value DESC" if sort == "score" else \
            "matched_value DESC, top_score DESC"

    items = rows(f"""
        WITH per_entity AS (
            -- หนึ่งแถวต่อ (ลูกค้า, หุ้น) — กันการนับมูลค่าซ้ำเมื่อวันนั้นมีข่าวถึงหุ้นเดียวกันหลายชิ้น
            SELECT m.customer_key, m.matched_entity,
                   MAX(COALESCE(m.holding_value,0)) value,
                   MAX(m.score) score,
                   MIN(m.level) level,
                   COUNT(DISTINCT m.article_id) n_articles
            FROM matches m JOIN articles a USING(article_id)
            WHERE m.rm_id=? {day}
            GROUP BY m.customer_key, m.matched_entity
        ),
        agg AS (
            SELECT customer_key,
                   SUM(value) matched_value,
                   MAX(score) top_score,
                   SUM(n_articles) n_article_hits,
                   COUNT(*) n_entities
            FROM per_entity GROUP BY customer_key
        )
        SELECT g.customer_key, g.matched_value, g.top_score, g.n_entities,
               c.persona, c.portfolio_value, c.portfolio_tier, c.days_since_last_trade,
               c.unrealized_state, c.n_holdings,
               -- หุ้นที่ทำให้เข้าเกณฑ์ เรียงตามเงินที่ถือ เอาไว้ขึ้นเป็นป้ายในแถว
               (SELECT GROUP_CONCAT(x.matched_entity || '|' || CAST(x.value AS INT), ';')
                  FROM (SELECT matched_entity, value FROM per_entity pe
                        WHERE pe.customer_key=g.customer_key
                        ORDER BY value DESC LIMIT 4) x) entities,
               -- ข่าวที่ควรใช้เปิดบทสนทนา = ข่าวของหุ้นที่เขาถือหนักสุดในวันนั้น
               t.article_id top_article_id, t.title top_title, t.trigger_at top_trigger_at,
               t.reason_th top_reason_th, t.reason_en top_reason_en,
               t.matched_entity top_entity, t.level top_level,
               COALESCE(t.holding_value,0) top_entity_value
        FROM agg g
        JOIN customers c ON c.customer_key=g.customer_key
        LEFT JOIN (
            SELECT m.customer_key, m.article_id, m.matched_entity, m.level, m.holding_value,
                   m.reason_th, m.reason_en, a.title, a.trigger_at,
                   ROW_NUMBER() OVER (PARTITION BY m.customer_key
                                      ORDER BY COALESCE(m.holding_value,0) DESC, m.score DESC) rn
            FROM matches m JOIN articles a USING(article_id)
            WHERE m.rm_id=? {day}
        ) t ON t.customer_key=g.customer_key AND t.rn=1
        ORDER BY {order} LIMIT ?""", args + args + [limit])

    for it in items:
        pv = it.get("portfolio_value") or 0
        it["share_of_portfolio"] = (it["matched_value"] / pv) if pv else None
        it["entities"] = [
            {"entity": e.split("|")[0], "value": float(e.split("|")[1])}
            for e in (it.get("entities") or "").split(";") if "|" in e
        ]

    return {"rm_id": rm_id, "date": date, "sort": sort, "total": len(items),
            "value_total": sum(i["matched_value"] or 0 for i in items),
            "items": items}


@app.get("/api/rm/{rm_id}/news")
def rm_news(rm_id: str, date: str | None = None, limit: int = Query(40, le=200)) -> dict:
    """มุมข่าว — ข่าวของวันนั้นชิ้นไหนไปแตะเงินของลูกค้า RM คนนี้มากที่สุด

    ต่อข่าวหนึ่งชิ้น ลูกค้าหนึ่งคนมีได้แถวเดียว (ux_match) จึงรวม holding_value ตรง ๆ ได้
    ไม่ต้องกันซ้ำเหมือนมุมลูกค้า
    """
    day, args = "", [rm_id]
    if date:
        day = "AND substr(a.trigger_at,1,10)=?"
        args.append(date)

    arts = rows(f"""
        SELECT m.article_id, a.title, a.url, a.trigger_at, a.subcategory, a.subcategory_name,
               a.record_type, a.parent_article_id, a.segment_no,
               COUNT(DISTINCT m.customer_key) customers,
               SUM(COALESCE(m.holding_value,0)) matched_value,
               MAX(m.score) top_score,
               SUM(CASE WHEN m.level='L1_HOLD' THEN 1 ELSE 0 END) n_hold
        FROM matches m JOIN articles a USING(article_id)
        WHERE m.rm_id=? {day}
        GROUP BY m.article_id
        ORDER BY matched_value DESC, customers DESC LIMIT ?""", args + [limit])

    c = con()
    try:
        for a in arts:
            # ลูกค้ารายใหญ่สุดของข่าวชิ้นนี้ — RM เห็นเลยว่าโทรใครก่อนจากข่าวนี้
            a["top_customers"] = [dict(r) for r in c.execute("""
                SELECT m.customer_key, m.matched_entity, m.level, m.score,
                       COALESCE(m.holding_value,0) holding_value,
                       cu.portfolio_tier, cu.persona, cu.portfolio_value
                FROM matches m JOIN customers cu USING(customer_key)
                WHERE m.article_id=? AND m.rm_id=?
                ORDER BY holding_value DESC, m.score DESC LIMIT 5""",
                (a["article_id"], rm_id))]
            row = c.execute("SELECT * FROM articles WHERE article_id=?",
                            (a["article_id"],)).fetchone()
            v = briefing.analyse(dict(row)) if row else {}
            a["overall"] = v.get("overall", "unknown")
            a["strongest_tier"] = v.get("strongest_tier")
            sig = (v.get("signals") or [None])[0]
            a["why_th"] = sig["th"] if sig else None
            a["why_en"] = sig["en"] if sig else None
    finally:
        c.close()

    return {"rm_id": rm_id, "date": date, "total": len(arts),
            "value_total": sum(a["matched_value"] or 0 for a in arts), "items": arts}


@app.get("/api/rm/{rm_id}/entities")
def rm_entities(rm_id: str, date: str | None = None, limit: int = Query(40, le=200)) -> dict:
    """มุมหุ้น — ข่าวของวันนั้นทำให้ "ตัวไหน" กลายเป็นเรื่องที่ต้องโทรคุย

    ต่างจากหน้า "หาจากหุ้น" ที่ดูทีละตัวจากทั้งบริษัท — อันนี้คือรายการตัวที่ข่าวแตะ
    เฉพาะในบุ๊กของ RM คนเดียว เรียงตามเงินของเขา

    มูลค่ายุบเป็นราย (ลูกค้า, หุ้น) ก่อนรวมเหมือนมุมลูกค้า เพราะข่าวหลายชิ้นชี้หุ้นตัวเดียวกันได้

    ดึงทุกอย่างในคิวรีเดียวและวิเคราะห์บทความชิ้นละครั้ง — เวอร์ชันแรกวนยิงต่อหุ้น
    แล้วใช้เวลา 8 วินาที ซึ่งช้าเกินกว่าจะเปิดตอนเช้าทุกวัน
    """
    day, args = "", [rm_id]
    if date:
        day = "AND substr(a.trigger_at,1,10)=?"
        args.append(date)

    # หนึ่งแถวต่อ (หุ้น, ลูกค้า) พร้อมข่าวที่ทำให้เข้าเกณฑ์ — พออ่านรอบเดียวประกอบได้ทุกอย่าง
    raw = rows(f"""
        SELECT m.matched_entity entity, m.customer_key,
               MAX(COALESCE(m.holding_value,0)) value,
               MAX(m.score) score, MIN(m.level) level,
               GROUP_CONCAT(DISTINCT m.article_id) article_ids,
               cu.portfolio_tier, cu.persona, cu.portfolio_value
        FROM matches m JOIN articles a USING(article_id)
        JOIN customers cu ON cu.customer_key=m.customer_key
        WHERE m.rm_id=? {day}
        GROUP BY m.matched_entity, m.customer_key""", args)

    by_entity: dict[str, dict] = {}
    for r in raw:
        e = by_entity.setdefault(r["entity"], {
            "entity": r["entity"], "matched_value": 0.0, "customers": 0, "n_hold": 0,
            "top_score": 0.0, "top_level": "L9", "article_ids": set(), "_people": [],
        })
        e["matched_value"] += r["value"]
        e["customers"] += 1
        e["n_hold"] += 1 if r["level"] == "L1_HOLD" else 0
        e["top_score"] = max(e["top_score"], r["score"] or 0)
        e["top_level"] = min(e["top_level"], r["level"] or "L9")
        e["article_ids"].update((r["article_ids"] or "").split(","))
        e["_people"].append({
            "customer_key": r["customer_key"], "holding_value": r["value"],
            "level": r["level"], "score": r["score"], "portfolio_tier": r["portfolio_tier"],
            "persona": r["persona"], "portfolio_value": r["portfolio_value"],
        })

    items = sorted(by_entity.values(),
                   key=lambda x: (-x["matched_value"], -x["customers"]))[:limit]

    # วิเคราะห์บทความชิ้นละครั้ง แล้วแจกให้ทุกหุ้นที่อ้างถึงมัน
    need = {a for it in items for a in it["article_ids"] if a}
    view: dict[str, dict] = {}
    if need:
        c = con()
        try:
            qs = ",".join("?" * len(need))
            for row in c.execute(f"SELECT * FROM articles WHERE article_id IN ({qs})",
                                 tuple(need)):
                art = dict(row)
                v = briefing.analyse(art)
                sigs = v.get("signals") or []
                # สรุปรายวันชิ้นเดียวมีคำแนะนำของหุ้นหลายสิบตัว (ของจริง 39 สัญญาณ)
                # เก็บแยกรายหุ้นไว้ ไม่งั้นหยิบตัวแรกไปแสดงให้ทุกตัวแล้วผิดคนละบริษัท
                sig = sigs[0] if sigs else None
                by_ent: dict[str, dict] = {}
                for s in sigs:
                    e = (s.get("entity") or "").strip()
                    if e and e not in by_ent:
                        by_ent[e] = s
                view[art["article_id"]] = {
                    "article_id": art["article_id"], "title": art["title"],
                    "trigger_at": art["trigger_at"], "overall": v["overall"],
                    "content_type": art.get("content_type") or "",
                    "why_th": sig["th"] if sig else None,
                    "why_en": sig["en"] if sig else None,
                    "sig_by_entity": by_ent,
                    # หุ้นเด่นประจำวันที่บทความชี้เอง (GAP-23)
                    "top_picks": [k for k, x in (db.jload(art.get("evidence"), {}) or {}).items()
                                  if isinstance(x, dict) and x.get("rule") == "GAP-23"],
                    # ความเห็นของบ้านเราเอง — RM ใช้ตัดสินใจว่าจะพูดอะไรก่อนโทร
                    "invx_view": v.get("invx_view") or "",
                }
        finally:
            c.close()

    for it in items:
        arts = [view[a] for a in it["article_ids"] if a in view]
        arts.sort(key=lambda a: a["trigger_at"], reverse=True)
        dirs: dict[str, int] = {}
        for a in arts:
            dirs[a["overall"]] = dirs.get(a["overall"], 0) + 1
        told = {k: n for k, n in dirs.items() if k not in ("unknown", "flat")}
        # ข่าวที่ยกมาเป็นตัวเปิดเรื่อง เลือกชิ้นที่บอกทิศทางได้ก่อน ไม่ใช่ชิ้นล่าสุดเสมอ
        it["lead"] = next((a for a in arts if a["overall"] not in ("unknown", "flat")),
                          arts[0] if arts else None)
        root = it["entity"].split(":", 1)[0]
        # หุ้นเด่นต้องดูจากข่าว "ทุกชิ้น" ของวันนั้น ไม่ใช่เฉพาะชิ้นที่ถูกเลือกเป็นตัวเปิดเรื่อง
        # ชิ้นที่ประกาศหุ้นเด่น (สรุปเช้า) มักไม่ใช่ชิ้นที่บอกทิศทางแรงสุด จึงไม่ได้เป็น lead
        it["top_pick"] = any(it["entity"] in (a.get("top_picks") or [])
                             or root in (a.get("top_picks") or []) for a in arts)

        # "มีข่าวของตัวเอง" กับ "ถูกเอ่ยในสรุปรายวัน" คนละน้ำหนักกันมาก
        # ของจริงวันหนึ่ง 14 จาก 35 ตัวมาจากสรุปรายวันล้วน แล้วทุกตัวโชว์พาดหัวเดียวกัน
        # ("คาด SET แกว่งตัว…") ซึ่งไม่ได้บอกอะไรเกี่ยวกับหุ้นตัวนั้นเลย ต้องแยกให้เห็น
        it["coverage"] = "own" if any(a.get("content_type") != "daily_brief" for a in arts) \
            else "brief"
        # ชิ้นที่พูดถึงหุ้นตัวนี้โดยตรง เอาไว้ขึ้นแทนพาดหัวรวมเมื่อมาจากสรุปรายวัน
        it["lead_own"] = next((a for a in arts if a.get("content_type") != "daily_brief"), None)
        if it["lead"]:
            # แทนเหตุผลด้วยสัญญาณของหุ้นตัวนี้เอง — ตัวแรกของบทความมักเป็นของหุ้นอื่น
            by_ent = it["lead"].get("sig_by_entity") or {}
            mine = by_ent.get(it["entity"]) or by_ent.get(root)
            if not mine:
                # lead ไม่มีของตัวนี้ ลองหาจากข่าวชิ้นอื่นของวันเดียวกันก่อนยอมเว้นว่าง
                for a in arts:
                    b = a.get("sig_by_entity") or {}
                    mine = b.get(it["entity"]) or b.get(root)
                    if mine:
                        break
            if mine:
                it["lead"] = {**it["lead"], "why_th": mine["th"], "why_en": mine["en"]}
            elif by_ent:
                # บทความแจกแจงรายหุ้นแต่ไม่มีของตัวนี้ — เว้นว่างดีกว่ายืมของตัวอื่น
                it["lead"] = {**it["lead"], "why_th": None, "why_en": None}
        it["directions"] = dirs
        it["n_articles"] = len(arts)
        it["overall"] = (next(iter(told)) if len(told) == 1
                         else "mixed" if told else "unknown")
        it["top_customers"] = sorted(it.pop("_people"),
                                     key=lambda x: (-(x["holding_value"] or 0),
                                                    -(x["score"] or 0)))[:4]
        it.pop("article_ids")

    return {"rm_id": rm_id, "date": date, "total": len(by_entity),
            "value_total": sum(i["matched_value"] or 0 for i in items), "items": items}


# ==========================================================================
# STEP8 — รายงาน
# ==========================================================================

@app.get("/api/reports/unmapped")
def report_unmapped(bucket: str | None = None, severity: str | None = None,
                    limit: int = Query(200, le=2000)) -> dict:
    """STEP8 รายงาน 1-2 — เรียงตาม "ผลกระทบ" ไม่ใช่ "จำนวนครั้งที่เจอ"

    รหัสที่เจอ 84 ครั้งแต่มีคนถือ 2 คน ไม่ได้สำคัญกว่ารหัสที่เจอ 3 ครั้ง
    แต่มีคนถือ 200 คน หน้านี้จึงคำนวณผลกระทบจริงจากพอร์ตแล้วเรียงตามนั้น
    """
    where, args = ["1=1"], []
    if bucket:
        where.append("u.bucket=?")
        args.append(bucket)
    w = " AND ".join(where)

    items = rows(f"""
        SELECT u.*,
               COALESCE(h.customers, 0)  customers,
               COALESCE(h.value_mb, 0.0) value_mb,
               COALESCE(t.txn_rows, 0)   txn_rows
        FROM unmapped u
        -- ผลกระทบของรหัสสินทรัพย์ = มีใครถืออยู่จริงกี่คน คิดเป็นเงินเท่าไร
        LEFT JOIN (SELECT product_code,
                          COUNT(DISTINCT customer_key) customers,
                          ROUND(SUM(COALESCE(holding_value,0))/1e6, 2) value_mb
                   FROM holdings GROUP BY 1) h
               ON u.bucket='holding_code' AND h.product_code = u.raw
        -- ผลกระทบของ txn_type ที่ไม่รู้จัก = กี่แถวถูกตีเป็น IGNORE
        LEFT JOIN (SELECT txn_type, COUNT(*) txn_rows
                   FROM transactions GROUP BY 1) t
               ON u.bucket='txn_type' AND t.txn_type = u.raw
        WHERE {w}""", args)

    today = dt.date.today()
    # ฐานข้อมูลที่เพิ่งสร้างจะมี first_seen ใหม่หมดทุกแถว ติดป้าย "ใหม่" ทั้งตาราง
    # ก็ไม่ได้บอกอะไร — ป้ายนี้จะเริ่มมีความหมายเมื่อตารางมีอายุเกินกรอบเวลา
    oldest = min((str(r["first_seen"] or "9999") for r in items), default="9999")
    young_db = _within(oldest, today, UNMAPPED_NEW_DAYS)
    for r in items:
        sev, th, en = UNMAPPED_SEVERITY.get(r["bucket"], UNMAPPED_SEVERITY_FALLBACK)
        r["severity"], r["impact_th"], r["impact_en"] = sev, th, en
        r["is_new"] = (not young_db) and _within(r["first_seen"], today, UNMAPPED_NEW_DAYS)

    if severity:
        items = [r for r in items if r["severity"] == severity]

    # เรียง: ร้ายแรงก่อน → ของใหม่ก่อน → มูลค่าที่กระทบ → จำนวนคน → ความถี่
    items.sort(key=lambda r: (SEVERITY_ORDER.get(r["severity"], 9), not r["is_new"],
                              -r["value_mb"], -r["customers"], -r["n"]))

    by_sev: dict[str, dict] = {}
    for r in items:
        s = by_sev.setdefault(r["severity"], {"severity": r["severity"], "distinct_n": 0,
                                              "total": 0, "value_mb": 0.0, "new_n": 0})
        s["distinct_n"] += 1
        s["total"] += r["n"]
        s["value_mb"] = round(s["value_mb"] + r["value_mb"], 2)
        s["new_n"] += 1 if r["is_new"] else 0

    return {
        "by_bucket": rows("SELECT bucket, COUNT(*) distinct_n, SUM(n) total FROM unmapped "
                          "GROUP BY 1 ORDER BY total DESC"),
        "by_severity": sorted(by_sev.values(),
                              key=lambda s: SEVERITY_ORDER.get(s["severity"], 9)),
        "new_days": UNMAPPED_NEW_DAYS,
        "items": items[:limit],
    }


@app.get("/api/reports/verification")
def report_verification(grade: str | None = None, limit: int = Query(200, le=2000)) -> dict:
    """GAP-21 — บันทึกการตรวจอัตโนมัติ อ่านอย่างเดียว ไม่มีปุ่มอนุมัติ

    ทุกบทความเข้าสู่การจับคู่ไปแล้ว หน้านี้มีไว้ให้คนเปิดดูว่าอันไหนหลักฐานบาง
    """
    where, args = ["role='content'"], []
    if grade:
        where.append("auto_grade=?")
        args.append(grade)
    w = " AND ".join(where)
    return {
        "counts": rows("""SELECT COALESCE(auto_grade,'unknown') grade, COUNT(*) n,
                                 SUM(n_matches) matches
                          FROM articles WHERE role='content'
                          GROUP BY 1 ORDER BY n DESC"""),
        "items": rows(f"""SELECT article_id, record_type, segment_no, title, url, subcategory,
                                 subcategory_name, entity, entity_source, entity_confidence,
                                 auto_grade, auto_reason_th, auto_reason_en, auto_checks,
                                 evidence, trigger_at, n_matches
                          FROM articles WHERE {w}
                          ORDER BY CASE auto_grade WHEN 'weak' THEN 0 WHEN 'auto_verified' THEN 1
                                                   ELSE 2 END,
                                   n_matches DESC, trigger_at DESC
                          LIMIT ?""", args + [limit]),
    }


@app.get("/api/reports/coverage")
def report_coverage() -> dict:
    """STEP8 รายงานข้อ 4 — ลูกค้า/กลุ่มที่ระบบไม่เคยจับคู่ให้เลย (อาจมีช่องว่างเนื้อหา)"""
    return {
        "by_persona": rows("""
            SELECT c.persona,
                   COUNT(*) customers,
                   SUM(CASE WHEN x.n IS NULL THEN 1 ELSE 0 END) never_matched,
                   ROUND(SUM(c.portfolio_value)/1e6,1) aum_mb
            FROM customers c
            LEFT JOIN (SELECT customer_key, COUNT(*) n FROM matches GROUP BY 1) x
                   ON x.customer_key=c.customer_key
            GROUP BY 1 ORDER BY never_matched DESC"""),
        "by_asset_class": rows("""
            SELECT h.asset_class,
                   COUNT(DISTINCT h.customer_key) customers,
                   COUNT(DISTINCT h.entity) instruments,
                   ROUND(SUM(h.holding_value)/1e6,1) value_mb,
                   COUNT(DISTINCT CASE WHEN m.entity IS NOT NULL THEN h.entity END) covered
            FROM holdings h
            LEFT JOIN (SELECT DISTINCT matched_entity entity FROM matches) m ON m.entity=h.entity
            GROUP BY 1 ORDER BY value_mb DESC"""),
        "top_uncovered": rows("""
            SELECT h.entity, h.asset_class, COUNT(DISTINCT h.customer_key) customers,
                   ROUND(SUM(h.holding_value)/1e6,2) value_mb
            FROM holdings h
            WHERE h.entity IS NOT NULL
              AND h.entity NOT IN (SELECT DISTINCT matched_entity FROM matches)
            GROUP BY 1 ORDER BY value_mb DESC LIMIT 40"""),
    }


@app.get("/api/reports/related")
def report_related(min_count: int = 2, limit: int = Query(100, le=1000)) -> dict:
    """C2 — ความสัมพันธ์หุ้นที่ระบบเรียนเองจาก co-mention (R3.29 - R3.36)"""
    return {"min_count": min_count,
            "seed_groups": refdata()["related_groups"],
            "learned": rows("SELECT a, b, n, article_ids FROM entity_pairs WHERE n>=? "
                            "ORDER BY n DESC LIMIT ?", (min_count, limit))}


# ==========================================================================
# มุมมองรายสินทรัพย์ — เริ่มจากชื่อหุ้น ไม่ใช่เริ่มจากข่าว
# ==========================================================================
#
# หน้าจอหลักเป็น news-centric ตาม STEP7 แต่ RM ถามกลับทางด้วย:
# "ลูกค้าคนไหนถือ NVDA เยอะสุด แล้วสัปดาห์นี้ข่าวมันไปทางไหน"
# หน้านี้ตอบคำถามนั้น โดยประกอบจากของที่มีอยู่แล้ว ไม่มีการคำนวณใหม่

@app.get("/api/entities")
def entity_search(q: str | None = None, limit: int = Query(20, le=100)) -> list[dict]:
    """ค้นชื่อสินทรัพย์จากที่ลูกค้าถืออยู่จริง เรียงตามจำนวนคนถือ"""
    args: list = []
    where = "entity IS NOT NULL AND entity<>''"
    if q:
        where += " AND UPPER(entity) LIKE ?"
        args.append(f"%{q.upper()}%")
    args.append(limit)
    return rows(f"""SELECT entity, COUNT(DISTINCT customer_key) holders,
                           COALESCE(SUM(holding_value),0) value
                    FROM holdings WHERE {where}
                    GROUP BY entity ORDER BY holders DESC, value DESC LIMIT ?""", args)


@app.get("/api/entities/highlights")
def entity_highlights(days: int = Query(1, ge=1, le=RETENTION_DAYS),
                      week: int = Query(7, ge=1, le=RETENTION_DAYS),
                      limit: int = Query(12, le=50), rm: str | None = None) -> dict:
    """สินทรัพย์ที่ควรสนใจวันนี้ — ประกอบจากข่าว + พอร์ตลูกค้า

    ต้องอธิบายได้ทุกแถวว่าทำไมขึ้นมา ไม่ใช่คะแนนลอย ๆ จึงส่งเหตุผลกลับไปด้วย
    (ทิศทาง + ประโยคที่อ้างอิง + จำนวนคนถือ + จำนวนคนที่เข้าเกณฑ์วันนี้)

    ไม่ส่ง rm = ภาพรวมทั้งบริษัท (ค่าเริ่มต้น สำหรับคนที่ไม่ได้ดูแลพอร์ตเอง)
    ส่ง rm = นับเฉพาะลูกค้าของผู้ดูแลคนนั้น และเรียงตามมูลค่าที่เขาถือเป็นตัวแรก

    ประกาศ route นี้ก่อน /api/entities/{entity} เพราะ FastAPI จับตามลำดับ
    ไม่งั้นคำว่า highlights จะกลายเป็นชื่อสินทรัพย์
    """
    c = con()
    try:
        today = dt.date.today().isoformat()
        since = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
        since_week = (dt.date.today() - dt.timedelta(days=week - 1)).isoformat()

        # ---- ข่าวช่วงที่ขอ: เก็บทิศทางต่อสินทรัพย์ พร้อมประโยคหลักฐาน ----
        per: dict[str, dict] = {}
        for a in c.execute("""SELECT * FROM articles WHERE role='content'
                              AND substr(trigger_at,1,10) >= ?""", (since_week,)):
            art = dict(a)
            ents = db.jload(art.get("entity"), []) or []
            if not ents:
                continue
            v = briefing.analyse(art)
            recent = art["trigger_at"][:10] >= since
            best = min((s["tier"] for s in v["signals"]), default=9)
            sig = next((s for s in v["signals"] if s["tier"] == best), None)
            for e in ents:
                p = per.setdefault(e, {"entity": e, "news_week": 0, "news_recent": 0,
                                       "directions": {}, "best_tier": 9, "why_th": None,
                                       "why_en": None, "phrase": None, "overall": "unknown",
                                       "article_id": None, "title": None, "matched_news": 0})
                p["news_week"] += 1
                if recent:
                    p["news_recent"] += 1
                    p["matched_news"] += art["n_matches"] or 0
                    d = v["overall"]
                    p["directions"][d] = p["directions"].get(d, 0) + 1
                    if best < p["best_tier"]:
                        p.update({"best_tier": best, "overall": d,
                                  "article_id": art["article_id"], "title": art["title"],
                                  "why_th": sig["th"] if sig else None,
                                  "why_en": sig["en"] if sig else None,
                                  "phrase": (sig or {}).get("phrase")})

        # ---- ฝั่งพอร์ต: ใครถือ มูลค่า และกำไรขาดทุนรวมของตัวนั้น ----
        port = {r["entity"]: dict(r) for r in c.execute(f"""
            SELECT entity, COUNT(DISTINCT customer_key) holders,
                   COALESCE(SUM(holding_value),0) value,
                   SUM(unrealized_pnl) pnl
            FROM holdings WHERE entity IS NOT NULL AND entity<>''
              {"AND rm_id=?" if rm else ""}
            GROUP BY entity""", (rm,) if rm else ())}

        # ---- ลูกค้าที่เข้าเกณฑ์จากข่าววันนี้ นับตามสินทรัพย์ที่ทำให้เข้าเกณฑ์ ----
        matched = {r["matched_entity"]: r["n"] for r in c.execute(f"""
            SELECT m.matched_entity, COUNT(DISTINCT m.customer_key) n
            FROM matches m JOIN articles a ON a.article_id=m.article_id
            WHERE substr(a.trigger_at,1,10) >= ? {"AND m.rm_id=?" if rm else ""}
            GROUP BY 1""", (since, rm) if rm else (since,))}

        def merge(e: str, p: dict) -> dict:
            h = port.get(e, {})
            return {**p, "holders": h.get("holders", 0), "value": h.get("value", 0),
                    "pnl": h.get("pnl"), "matched_today": matched.get(e, 0)}

        # 1) ข่าววันนี้ + มีลูกค้าถือ — เรียงตามจำนวนคนที่เข้าเกณฑ์ แล้วค่อยจำนวนคนถือ
        #    แต่ถ้าเจาะดูของผู้ดูแลคนเดียว เอามูลค่าขึ้นก่อน เพราะเขาต้องเลือกว่าจะโทรใครก่อน
        #    จากเงินที่เสี่ยงอยู่ ไม่ใช่จากหัวจำนวนคน
        live = [merge(e, p) for e, p in per.items() if p["news_recent"]]
        in_port = sorted([x for x in live if x["holders"]],
                         key=(lambda x: (-x["value"], -x["matched_today"], -x["holders"])) if rm
                         else (lambda x: (-x["matched_today"], -x["holders"], -x["value"])))

        # 2) ข่าววันนี้แต่ยังไม่มีใครถือ — โอกาสเสนอของใหม่ (L2 watchlist ก็อยู่กลุ่มนี้)
        not_held = sorted([x for x in live if not x["holders"]],
                          key=lambda x: (x["best_tier"], -x["news_recent"]))

        # 3) ข่าวลบวันนี้ + ลูกค้าถืออยู่และรวมแล้วขาดทุน — คุยก่อนลูกค้าโทรมาถาม
        risk = sorted(
            [x for x in in_port
             if x["overall"] == "down" and x["pnl"] is not None and x["pnl"] < 0],
            key=lambda x: x["pnl"])

        # 4) สัปดาห์นี้ถูกพูดถึงบ่อยสุด — บอกว่าประเด็นไหนกำลังเดิน
        attention = sorted([merge(e, p) for e, p in per.items() if p["news_week"] >= 2],
                           key=lambda x: (-x["news_week"], -x["holders"]))

        # 5) ถือเยอะสุดในพอร์ตรวม — ไว้ไล่ดูตอนไม่มีข่าว
        top_held = sorted(({"entity": e, **v} for e, v in port.items()),
                          key=(lambda x: (-x["value"], -x["holders"])) if rm
                          else (lambda x: (-x["holders"], -x["value"])))

        return {
            "date": today, "days": days, "week": week, "rm": rm,
            "with_news_in_portfolio": in_port[:limit],
            "with_news_not_held": not_held[:limit],
            "negative_and_losing": risk[:limit],
            "most_talked_this_week": attention[:limit],
            "most_held": top_held[:limit],
        }
    finally:
        c.close()


@app.get("/api/entities/{entity}/chart")
def entity_chart(entity: str, range: str = Query("6mo"), force: bool = False) -> dict:
    """ข้อมูลกราฟ — คืนรูปแบบเดียว หน้าเว็บดู provider แล้วเลือกวาด

    tradingview = ส่งแค่ชื่อสัญลักษณ์ widget ไปดึงข้อมูลของตัวเองที่ฝั่งเบราว์เซอร์
    yahoo       = เราดึงแท่งเทียนมาให้ พร้อมวันที่มีข่าวถึงตัวนี้เพื่อปักหมุดบนกราฟ
    """
    who = symbols.provider(entity)
    out: dict = {"entity": entity, "provider": who, "range": range,
                 "tradingview": symbols.to_tradingview(entity),
                 "symbol": symbols.to_yahoo(entity), "note": None}
    if who == "none":
        out["note"] = "ไม่มีข้อมูลกราฟสำหรับตัวนี้ (กองทุนไทยและตราสารเฉพาะ)"
        return out
    if who == "tradingview":
        return out

    c = con()
    try:
        out.update(prices.series(c, out["symbol"], range, force))
        bars = (out.get("series") or {}).get("bars") or []
        if bars:
            out["news_marks"] = _news_marks(c, entity, since=bars[0]["d"])
        return out
    finally:
        c.close()


def _news_marks(c, entity: str, since: str) -> list[dict]:
    """วันที่มีข่าวถึง entity นี้ + ทิศทางที่ระบบอ่านได้ — ใช้ปักหมุดบนกราฟ

    ของชิ้นนี้ไม่มีในบริการกราฟภายนอก เพราะข่าวกับทิศทางเป็นข้อมูลของระบบเอง
    """
    marks: dict[str, dict] = {}
    for a in c.execute("""SELECT * FROM articles WHERE role='content'
                          AND substr(trigger_at,1,10) >= ?
                          AND EXISTS (SELECT 1 FROM json_each(entity) WHERE value = ?)
                          ORDER BY trigger_at""", (since, entity)):
        art = dict(a)
        day = art["trigger_at"][:10]
        v = briefing.analyse(art)
        m = marks.setdefault(day, {"d": day, "n": 0, "dirs": {}, "title": art["title"],
                                   "article_id": art["article_id"]})
        m["n"] += 1
        m["dirs"][v["overall"]] = m["dirs"].get(v["overall"], 0) + 1
    return list(marks.values())


@app.get("/api/entities/{entity}")
def entity_view(entity: str, days: int = Query(7, ge=1, le=RETENTION_DAYS),
                limit: int = Query(50, le=500), rm: str | None = None) -> dict:
    """ทุกอย่างที่ระบบรู้เกี่ยวกับสินทรัพย์หนึ่งตัว — ใครถือ ข่าวว่าอะไร ไปทางไหน

    rm ที่ส่งมาเป็นตัวกรองชั่วคราวของหน้าจอ ไม่ใช่ตัวตนของผู้ใช้ —
    ต้องกรองที่ SQL เพราะ holders มี LIMIT ถ้ากรองทีหลังลูกค้าของ RM ที่ไม่ติด
    อันดับรวมจะหายไปเงียบ ๆ ส่วนยอดรวมทั้งบริษัทยังคืนเสมอเพื่อให้เทียบสัดส่วนได้
    """
    c = con()
    try:
        holders = [dict(r) for r in c.execute(f"""
            SELECT h.customer_key, c.rm_id, c.persona, c.portfolio_value, c.portfolio_tier,
                   c.unrealized_state, c.days_since_last_trade, c.n_holdings,
                   SUM(h.holding_value) holding_value,
                   -- ห้าม COALESCE เป็นศูนย์ — "ไม่มีข้อมูล" ต่างจาก "เท่าทุน"
                   -- ไฟล์พอร์ตส่ง thb_unrealized_avg มาเฉพาะบางชนิดสินทรัพย์ (H-08 ไม่บังคับ)
                   SUM(h.unrealized_pnl) unrealized_pnl,
                   GROUP_CONCAT(DISTINCT NULLIF(h.instrument_label,'')) labels,
                   GROUP_CONCAT(DISTINCT h.product_code) product_codes
            FROM holdings h JOIN customers c ON c.customer_key=h.customer_key
            WHERE h.entity=? {"AND c.rm_id=?" if rm else ""}
            GROUP BY h.customer_key
            ORDER BY holding_value DESC LIMIT ?""",
            (entity, rm, limit) if rm else (entity, limit))]
        for h in holders:
            pv = h["portfolio_value"] or 0
            h["share_of_portfolio"] = (h["holding_value"] or 0) / pv if pv else None
            h["labels"] = [x for x in (h["labels"] or "").split(",") if x]

        tot = one("""SELECT COUNT(DISTINCT customer_key) holders,
                            COALESCE(SUM(holding_value),0) value
                     FROM holdings WHERE entity=?""", (entity,)) or {}

        # แยกตามผู้ดูแล — เรียงตามมูลค่า ไม่ใช่จำนวนคน เพราะสองอย่างนี้ชี้คนละคน
        # (PTT: RM003 ถือ 11 คนแต่ 7.7 ลบ. · RM002 ถือ 8 คนแต่ 19.9 ลบ.)
        by_rm = [dict(r) for r in c.execute("""
            WITH book AS (SELECT rm_id, SUM(portfolio_value) bv FROM customers
                          WHERE rm_id <> '' GROUP BY rm_id)
            SELECT c.rm_id,
                   COUNT(DISTINCT h.customer_key) customers,
                   COALESCE(SUM(h.holding_value),0) value,
                   -- ห้าม COALESCE เป็นศูนย์ ด้วยเหตุผลเดียวกับข้างบน
                   SUM(h.unrealized_pnl) unrealized_pnl,
                   COUNT(h.unrealized_pnl) n_with_pnl,
                   COUNT(*) n_rows,
                   book.bv book_value
            FROM holdings h
            JOIN customers c ON c.customer_key = h.customer_key
            LEFT JOIN book ON book.rm_id = c.rm_id
            WHERE h.entity = ?
            GROUP BY c.rm_id
            ORDER BY value DESC""", (entity,))]
        for r in by_rm:
            bv = r["book_value"] or 0
            r["share_of_book"] = (r["value"] or 0) / bv if bv else None

        # เคยเทรดใน 90 วันแต่ตอนนี้ไม่ถือ (CF-05) — คนกลุ่มนี้คุยง่ายเพราะรู้จักของอยู่แล้ว
        watchers = [dict(r) for r in c.execute(f"""
            SELECT customer_key, rm_id, persona, portfolio_value, days_since_last_trade,
                   json_extract(watchlist, '$."' || ? || '"') last_traded
            FROM customers
            WHERE json_extract(watchlist, '$."' || ? || '"') IS NOT NULL
              {"AND rm_id=?" if rm else ""}
            ORDER BY last_traded DESC LIMIT 30""",
            (entity, entity, rm) if rm else (entity, entity))]

        # ข่าวที่พูดถึงตัวนี้ในช่วงที่ขอ พร้อมทิศทางของแต่ละชิ้น
        since = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
        arts = [dict(r) for r in c.execute("""
            SELECT * FROM articles
            WHERE role='content' AND substr(trigger_at,1,10) >= ?
              AND EXISTS (SELECT 1 FROM json_each(entity) WHERE value = ?)
            ORDER BY trigger_at DESC""", (since, entity))]
        today = dt.date.today().isoformat()
        news, roll = [], {"up": 0, "down": 0, "mixed": 0, "flat": 0,
                          "position_dependent": 0, "unknown": 0}
        for a in arts:
            v = briefing.analyse(a)
            roll[v["overall"]] = roll.get(v["overall"], 0) + 1
            news.append({
                "article_id": a["article_id"], "title": a["title"], "url": a["url"],
                "subcategory": a["subcategory"], "subcategory_name": a["subcategory_name"],
                "trigger_at": a["trigger_at"], "record_type": a["record_type"],
                "parent_article_id": a["parent_article_id"], "segment_no": a["segment_no"],
                "n_matches": a["n_matches"], "auto_grade": a["auto_grade"],
                "is_today": a["trigger_at"][:10] == today,
                "overall": v["overall"], "strongest_tier": v["strongest_tier"],
                "signals": [{k: s.get(k) for k in ("tier", "kind", "direction", "th", "en",
                                                   "phrase", "source_th", "source_en")}
                            for s in v["signals"]],
            })

        # ทิศทางของ "วันนี้" ใช้เฉพาะข่าววันนี้ที่มีหลักฐาน ไม่ยุบข่าวเก่ามารวม
        td = [n for n in news if n["is_today"] and n["overall"] not in ("unknown", "flat")]
        today_dir = td[0]["overall"] if len(
            {n["overall"] for n in td}) == 1 and td else ("mixed" if td else "unknown")

        cov = coverage_of(entity) or {}
        return {
            "entity": entity,
            "coverage": {k: cov.get(k) for k in ("sector", "rating", "target_price",
                                                 "last_close", "esg")} if cov else None,
            "holders": holders,
            "holders_total": tot.get("holders", 0),
            "value_total": tot.get("value", 0),
            "by_rm": by_rm,
            "rm": rm,
            "watchers": watchers,
            "news": news,
            "news_days": days,
            "direction_today": today_dir,
            "direction_week": roll,
        }
    finally:
        c.close()


# ==========================================================================
# งานเบื้องหลัง
# ==========================================================================

@app.post("/api/ingest/customers")
def do_ingest_customers() -> dict:
    c = con()
    try:
        return ingest.ingest(c)
    finally:
        c.close()


# --------------------------------------------------------------------------
# อัปโหลดไฟล์ลูกค้า — ต้องมาเป็นคู่เสมอ (HOLDINGS + TRANSACTIONS) และผ่าน STEP1
# --------------------------------------------------------------------------

def _save_upload(f: UploadFile, dest: Path) -> int:
    size = 0
    with dest.open("wb") as out:
        while chunk := f.file.read(1024 * 1024):
            size += len(chunk)
            if size > uploader.MAX_BYTES:
                raise HTTPException(413, f"ไฟล์ {f.filename} ใหญ่เกิน "
                                         f"{uploader.MAX_BYTES // 1024 // 1024} MB")
            out.write(chunk)
    return size


def _stage(portfolio: UploadFile, txn: UploadFile, tmp: Path) -> tuple[Path, Path, dict]:
    """เขียนไฟล์ที่อัปโหลดลงที่พักชั่วคราว แล้วตรวจตามสัญญาข้อมูล"""
    p_name = portfolio.filename or "portfolio.xlsx"
    t_name = txn.filename or "txn.xlsx"
    p_path, t_path = tmp / "portfolio.xlsx", tmp / "txn.xlsx"
    _save_upload(portfolio, p_path)
    _save_upload(txn, t_path)
    return p_path, t_path, uploader.check_pair(p_path, t_path, p_name, t_name)


@app.get("/api/mask-guide", include_in_schema=False)
def mask_guide():
    """ส่งไฟล์คู่มือ mask ให้โหลด — ชื่อไฟล์ปลายทางเป็น ASCII กัน header เพี้ยน"""
    if not MASK_GUIDE.exists():
        raise HTTPException(404, f"ไม่พบไฟล์คู่มือที่ {MASK_GUIDE}")
    return FileResponse(MASK_GUIDE, media_type="text/markdown; charset=utf-8",
                        filename="วิธี mask ด้วย Copilot บนเว็บ.md")


@app.post("/api/upload/check")
def do_upload_check(portfolio: UploadFile = File(...), txn: UploadFile = File(...)) -> dict:
    """ตรวจอย่างเดียว ไม่แตะข้อมูลจริง — ให้ผู้ใช้เห็นปัญหาก่อนตัดสินใจ"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        _, _, report = _stage(portfolio, txn, Path(d))
        return report


@app.post("/api/upload")
def do_upload(portfolio: UploadFile = File(...), txn: UploadFile = File(...),
              match: bool = Form(True)) -> dict:
    """ตรวจ -> เก็บไฟล์ชุดเดิมเข้า archive -> นำเข้า -> จับคู่ใหม่ทั้งหมด

    ไฟล์ที่ตรวจไม่ผ่านจะไม่ถูกติดตั้ง ข้อมูลเดิมในระบบไม่ถูกแตะต้อง
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        p_path, t_path, report = _stage(portfolio, txn, Path(d))
        if not report["ok"]:
            raise HTTPException(422, {"message": "ไฟล์ไม่ผ่านสัญญาข้อมูล STEP1 — ยังไม่ได้นำเข้า",
                                      "report": report})

        # นำเข้าจากไฟล์ชั่วคราวก่อน ยังไม่แตะ data/ — พังตรงนี้ข้อมูลเดิมยังอยู่ครบ
        c = con()
        try:
            ingested = ingest.ingest(c, holdings_path=p_path, txn_path=t_path)
            out: dict = {"report": report, "ingested": ingested}
            if match:
                # ลูกค้าเปลี่ยนทั้งชุด ผลจับคู่เดิมใช้ต่อไม่ได้ ต้องคำนวณใหม่ทุกบทความ
                m = matching.run_for_articles(c)
                out["matched"] = {"articles_matched": m["articles_matched"],
                                  "matches": m["matches"]}
        finally:
            c.close()

        # นำเข้าสำเร็จแล้วค่อยเก็บไฟล์ชุดใหม่ไว้ใน data/ สำหรับรอบถัดไป
        out["installed"] = uploader.install(p_path, t_path)
        return out


@app.get("/api/ai/health")
def ai_health(date: str | None = None) -> dict:
    """บอกหน้าเว็บว่าเครื่องนี้สั่ง Claude Code ได้ไหม และยังมีข่าวรออ่านอยู่กี่ชิ้น

    date="today" นับเฉพาะข่าวของวันล่าสุดที่มีในฐาน — ปุ่มบนแถบสั่งอ่าน "ข่าววันนี้"
    แต่ตัวเลขข้างปุ่มเคยนับทั้งคลัง เลยขยับทีละนิดจนดูเหมือนไม่ทำงาน
    ทั้งที่อ่านครบวันนี้แล้ว ตัวเลขต้องนับของชุดเดียวกับที่ปุ่มสั่งทำ
    """
    day = date
    if day == "today":
        day = (one("""SELECT substr(trigger_at,1,10) d FROM articles
                      WHERE role='content' ORDER BY trigger_at DESC LIMIT 1""") or {}).get("d")
    where, args = "", []
    if day:
        where = "AND substr(trigger_at,1,10)=?"
        args = [day]

    c = con()
    try:
        total = one(f"""SELECT COUNT(*) n FROM articles WHERE role='content' {where}
                        AND ((record_type='article' AND full_text IS NOT NULL AND full_text<>'')
                          OR (record_type='segment' AND segment_text IS NOT NULL
                              AND segment_text<>''))""", args) or {}
        # นับ "อ่านแล้ว" เฉพาะในกลุ่มที่อ่านได้จริง — ไม่งั้นตัวหน้า slash จะเกินตัวหลังได้
        done = one(f"""SELECT COUNT(*) n FROM articles WHERE ai_at IS NOT NULL {where}
                       AND role='content'
                       AND ((record_type='article' AND full_text IS NOT NULL AND full_text<>'')
                         OR (record_type='segment' AND segment_text IS NOT NULL
                             AND segment_text<>''))""", args) or {}
        withdir = one(f"""SELECT COUNT(*) n FROM articles
                          WHERE ai_direction IS NOT NULL AND ai_direction<>'unknown'
                          {where}""", args) or {}
        # AI-02 — "อ่านแล้วแต่ไม่สรุปทิศทาง" ต้องแยกให้เห็นว่าเพราะอะไร
        # ไม่งั้นตัวเลข read กับ with_direction ที่ห่างกันจะถูกอ่านว่าระบบพัง
        reasons = {r["ai_reason"]: r["n"] for r in rows(
            f"""SELECT ai_reason, COUNT(*) n FROM articles
                WHERE ai_reason IS NOT NULL AND ai_reason<>'' {where}
                GROUP BY 1 ORDER BY 2 DESC""", args)}
        return {**llm.available(), "date": day, "readable": total.get("n", 0),
                "read": done.get("n", 0), "with_direction": withdir.get("n", 0),
                "no_call_reasons": reasons}
    finally:
        c.close()


@app.post("/api/ai/enrich")
def ai_enrich(limit: int = Body(10, embed=True), redo: bool = Body(False, embed=True),
              target: str = Body("auto", embed=True),
              match: bool = Body(True, embed=True),
              workers: int = Body(4, embed=True),
              date: str | None = Body(None, embed=True)) -> dict:
    """ให้ Claude Code บนเครื่องอ่านข่าวเชิงลึก แล้วจับคู่ใหม่ถ้ามี entity เพิ่ม (AI-01)

    ใช้สิทธิ์ claude login ของเครื่อง ไม่มี API key และไม่มีบิลต่อ token
    งานนี้ช้า (ราว 15-25 วินาทีต่อชิ้น) จึงยิงขนานหลายเส้นและจำกัดจำนวนต่อครั้ง
    ให้หน้าจอกดซ้ำได้
    """
    c = con()
    try:
        day = date
        if day == "today":
            day = c.execute("SELECT MAX(substr(trigger_at,1,10)) FROM articles").fetchone()[0]
        res = enrich.enrich_batch(c, limit=min(limit, 40), redo=redo, target=target,
                                  date=day, workers=min(max(int(workers), 1), 8))
        if match and res.get("entities_added"):
            res["rematch"] = matching.run_for_articles(c, only_unmatched=True)
        return res
    finally:
        c.close()


@app.post("/api/ingest/news")
def do_ingest_news(pages: int = Body(3, embed=True), limit: int = Body(100, embed=True),
                   subcategory: str | None = Body(None, embed=True),
                   match: bool = Body(True, embed=True)) -> dict:
    """ดึงข่าว แล้วจับคู่บทความที่เพิ่งเข้ามาต่อทันที (match=false ถ้าต้องการแค่ดึง)

    ข่าวที่ยังไม่จับคู่จะไม่มีรายชื่อลูกค้าเลย คนกดปุ่มดึงข่าวย่อมคาดว่าเห็นรายชื่อ
    จึงต่อ matching ให้ในคำสั่งเดียว (only_unmatched — ของเก่าไม่ถูกคำนวณซ้ำ)
    """
    c = con()
    try:
        if subcategory:
            now = dt.datetime.now().isoformat(timespec="seconds")
            uni = news.universe_from_db(c)
            aliases = news.build_alias_index()
            funds = news.fund_codes_from_db(c)
            stored = 0
            for page in range(1, pages + 1):
                data, _ = news.fetch_page(limit=limit, page=page, subcategory=subcategory)
                if not data:
                    break
                for raw in data:
                    stored += news.store(c, news.tag(raw, uni, aliases, funds, c, now), now)
            out = {"subcategory": subcategory, "stored_rows": stored}
        else:
            out = news.ingest_recent(c, pages=pages, limit=limit)

        if match:
            m = matching.run_for_articles(c, only_unmatched=True)
            out["matched"] = {"articles_matched": m["articles_matched"], "matches": m["matches"]}
        return out
    except news.ApiStructureChanged as e:
        raise HTTPException(502, f"โครงสร้าง API เปลี่ยน (R2.5): {e}") from e
    finally:
        c.close()


@app.post("/api/match")
def do_match(threshold: float | None = Body(None, embed=True),
             only_unmatched: bool = Body(False, embed=True)) -> dict:
    c = con()
    try:
        return matching.run_for_articles(c, threshold=threshold, only_unmatched=only_unmatched)
    finally:
        c.close()


# ==========================================================================
# ปันผล (INVX Data Book รายเดือน — ดู dividends.py)
# ==========================================================================

@app.post("/api/ingest/dividends")
def do_ingest_dividends() -> dict:
    """ดึง Data Book เดือนล่าสุดจากเว็บเอง แกะตาราง "ตามรอยหุ้นปันผล" แล้วบันทึก

    รายงานออกเดือนละครั้ง ปุ่มนี้จึงกดเดือนละครั้งพอ กดซ้ำได้ (เขียนทับเดือนเดิม)
    """
    c = con()
    try:
        return dividends.ingest(c)
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    finally:
        c.close()


# ==========================================================================
# อีเมลถึง RM — หัวหน้าทีมเป็นคนกดส่ง (ดู mailer.py)
# ==========================================================================

def _latest_news_day() -> str | None:
    return (one("""SELECT substr(trigger_at,1,10) d FROM articles
                   WHERE role='content' ORDER BY trigger_at DESC LIMIT 1""") or {}).get("d")


def _books(rm_ids: list[str], day: str | None) -> tuple[str, list[dict]]:
    """ข้อมูลไฟล์แนบของ RM แต่ละคน — หนึ่งไฟล์ต่อคน ครบทุกแถวไม่ตัด"""
    day = day or _latest_news_day() or dt.date.today().isoformat()
    c = con()
    try:
        divs = mailer.dividend_map(c)
        out = []
        for rm_id in rm_ids:
            rows_ = mailer.detail_rows(c, rm_id, day, divs)
            seen: dict[str, dict] = {}
            for r in rows_:                       # แถวแรกของแต่ละหุ้นคือตัวแทนของหุ้นนั้น
                seen.setdefault(r["entity"], r)
            out.append({
                "rm_id": rm_id,
                "report_name": f"MatchPort_{rm_id}_{day}.html",
                "rows": rows_, "entities": len(seen),
                "value_total": sum(v["entity_value"] for v in seen.values()),
                "top": list(seen.values())[:5],
            })
        return day, out
    finally:
        c.close()


@app.get("/api/mail/config")
def mail_config() -> dict:
    c = con()
    try:
        return {**mailer.config(c), **mailer.health(),
                "rms": [r["rm_id"] for r in rows(
                    "SELECT DISTINCT rm_id FROM customers WHERE rm_id<>'' ORDER BY 1")]}
    finally:
        c.close()


@app.put("/api/mail/config")
def set_mail_config(recipients: list[str] = Body(..., embed=True)) -> dict:
    """เก็บแค่รายชื่อผู้รับ — ส่งผ่าน Outlook ที่ล็อกอินอยู่ จึงไม่มีรหัสผ่านให้เก็บเลย"""
    seen: list[str] = []
    for v in recipients:
        e = str(v).strip()
        if e and e.lower() not in {x.lower() for x in seen}:
            seen.append(e)
    c = con()
    try:
        with c:
            db.set_setting(c, "mail_recipients", seen)
        return {**mailer.config(c), **mailer.health()}
    finally:
        c.close()


@app.get("/api/mail/preview")
def mail_preview(date: str | None = None) -> dict:
    """ตัวอย่างอีเมลก่อนส่ง — ไม่ส่งอะไรทั้งนั้น ไม่แตะ Outlook ด้วย"""
    c = con()
    try:
        cfg = mailer.config(c)
    finally:
        c.close()
    targets = [r["rm_id"] for r in rows(
        "SELECT DISTINCT rm_id FROM customers WHERE rm_id<>'' ORDER BY 1")]
    day, books = _books(targets, date)
    c = con()
    try:
        fresh = mailer.freshness(c, day)
    finally:
        c.close()
    mail = mailer.compose_team(day, books, mailer.stale_warning(fresh))
    return {"date": day, **mail, "recipients": cfg["recipients"],
            "freshness": fresh, "warning": mailer.stale_warning(fresh),
            "files": [{"rm_id": b["rm_id"], "report": b["report_name"],
                       "rows": len(b["rows"]), "entities": b["entities"],
                       "value_total": b["value_total"]}
                      for b in books]}


@app.get("/api/mail/file")
def mail_file(rm: str, date: str | None = None):
    """โหลดไฟล์แนบมาดูก่อน — ไฟล์เดียวกับที่จะถูกแนบไปกับอีเมลจริง ไม่ได้สร้างใหม่คนละชุด"""
    day, books = _books([rm], date)
    b = books[0]
    c = con()
    try:
        warn = mailer.stale_warning(mailer.freshness(c, day))
        profiles = mailer.customer_profiles(
            c, sorted({r["customer_key"] for r in b["rows"]}), mailer.dividend_map(c))
    finally:
        c.close()
    return Response(
        content=mailer.render_report(rm, day, b["rows"], warn, profiles),
        media_type="text/html; charset=utf-8")


@app.post("/api/mail/send")
def mail_send(to: list[str] = Body(..., embed=True),
              rm_ids: list[str] = Body(..., embed=True),
              date: str | None = Body(None, embed=True),
              send_stale: bool = Body(False, embed=True)) -> dict:
    """ส่งอีเมลฉบับเดียวถึงผู้รับทุกคน แนบทั้งไฟล์อ่าน (.html) และไฟล์ข้อมูล (.csv) รายทีม

    ต้องระบุทั้งผู้รับและทีมที่จะแนบเสมอ ไม่มีค่าปริยาย — ส่งแล้วเรียกคืนไม่ได้
    การเผลอกดจึงไม่ควรกลายเป็นการส่งข้อมูลทั้งบริษัทออกไป

    ถ้าข้อมูลไม่ใช่ของวันนี้จะถูกปฏิเสธ เว้นแต่ส่ง send_stale มาด้วย — กันเคสที่พบบ่อยที่สุด
    คือเช้านี้ยังไม่มีใครกดดึงข่าว แล้วส่งคิวโทรของเมื่อวานออกไปโดยไม่มีใครทันสังเกต
    ด่านนี้อยู่ฝั่งเซิร์ฟเวอร์ ไม่ใช่แค่ป้ายเตือนบนหน้าจอ เพราะป้ายเตือนถูกมองข้ามได้
    """
    addrs = [e.strip() for e in to if str(e).strip()]
    if not addrs:
        raise HTTPException(400, "ไม่ได้ระบุอีเมลผู้รับ")
    if not rm_ids:
        raise HTTPException(400, "ไม่ได้เลือกว่าจะแนบข้อมูลของทีมไหน")

    c = con()
    try:
        day, books = _books(rm_ids, date)
        fresh = mailer.freshness(c, day)
        warn = mailer.stale_warning(fresh)
        if warn and not send_stale:
            raise HTTPException(409, warn)

        mail = mailer.compose_team(day, books, warn)
        # แนบเฉพาะไฟล์อ่าน — ไฟล์ .html มีครบทั้งภาพรวมและหน้าลูกค้ารายคนแล้ว
        # (ยังโหลด .csv จากหน้าเว็บได้ถ้าอยากทำงานต่อใน Excel แต่ไม่ต้องแนบไปทุกฉบับ)
        divs = mailer.dividend_map(c)
        files: list[tuple[str, bytes]] = []
        for b in books:
            profiles = mailer.customer_profiles(
                c, sorted({r["customer_key"] for r in b["rows"]}), divs)
            files.append((b["report_name"],
                          mailer.render_report(b["rm_id"], day, b["rows"], warn, profiles)))
        joined = "; ".join(addrs)

        try:
            mailer.send_mail(joined, mail["subject"], mail["html"], files)
        except mailer.OutlookUnavailable as e:
            mailer.log(c, "team", joined, False, str(e)[:300])
            raise HTTPException(503, str(e)) from e
        except RuntimeError as e:
            mailer.log(c, "team", joined, False, str(e)[:300])
            raise HTTPException(502, str(e)) from e

        now = dt.datetime.now().isoformat(timespec="seconds")
        mailer.log(c, "team", joined, True, f"{len(files)} ไฟล์ · {day}")
        with c:
            db.set_setting(c, "mail_sent_at", now)
            db.set_setting(c, "mail_recipients", addrs)
        return {"at": now, "date": day, "to": addrs, "subject": mail["subject"],
                "files": [f[0] for f in files], "was_stale": bool(warn)}
    finally:
        c.close()


@app.get("/api/dividends/styles")
def dividend_styles(rm: str | None = None, month: str | None = None) -> dict:
    """ภาพรวมสไตล์พอร์ตทั้งฐาน + คนที่ได้ปันผลเยอะสุด

    "ยังบอกไม่ได้" เป็นคำตอบที่ถูกต้อง ไม่ใช่ช่องว่างที่ต้องเติม — Data Book ครอบคลุม
    แค่หุ้นไทย ลูกค้าที่ถือแต่หุ้นนอกจึงวัดสไตล์จากข้อมูลชุดนี้ไม่ได้จริง ๆ
    """
    c = con()
    try:
        items = dividends.styles(c, month=month)
        if rm:
            items = [r for r in items if r["rm_id"] == rm]
        counts: dict[str, int] = {}
        for r in items:
            counts[r["style"]] = counts.get(r["style"], 0) + 1
        known = [r for r in items if r["style"] != "unknown"]
        return {
            "month": items[0]["month"] if items else None,
            "median_yield": items[0]["median_yield"] if items else 0.0,
            "coverage_min": dividends.COVERAGE_MIN,
            "labels": {k: v for k, v in dividends.STYLES.items()},
            "counts": counts,
            "customers": len(items),
            "measurable": len(known),
            "total_interim": sum(r["interim"] for r in items),
            "top": sorted(known, key=lambda r: -r["interim"])[:50],
        }
    finally:
        c.close()


@app.get("/api/dividends")
def dividend_table(month: str | None = None, rm: str | None = None) -> dict:
    """ตารางปันผลของเดือน + ผลกระทบจริงกับพอร์ตลูกค้า

    เงินปันผลที่ลูกค้าจะได้ = holding_value x yield_interim / 100
    เพราะ units = holding_value / price และ dividend = units x dps = holding_value x (dps/price)
    จึงไม่ต้องรู้จำนวนหุ้น — ใช้ได้กับทุกแถวที่ผ่านด่านตรวจ dps/price = yield แล้ว
    """
    c = con()
    try:
        month = month or (one("SELECT MAX(report_month) m FROM dividends") or {}).get("m")
        if not month:
            return {"month": None, "items": [], "total_dividend": 0.0,
                    "as_of": None, "months": []}

        # ลำดับ arg ต้องเรียงตามตำแหน่งใน SQL — rm อยู่ใน JOIN ซึ่งมาก่อน month ใน WHERE
        join = "AND h.rm_id = ?" if rm else ""
        args: list = ([rm] if rm else []) + [month]
        items = rows(f"""
            SELECT d.entity, d.price, d.rating, d.dps, d.yield_interim, d.xd_date,
                   d.pay_date, d.period, d.yield_forecast, d.remark,
                   COUNT(DISTINCT h.customer_key)              AS customers,
                   COALESCE(SUM(h.holding_value), 0)           AS held_value,
                   COALESCE(SUM(h.holding_value), 0) * d.yield_interim / 100 AS dividend
            FROM dividends d
            LEFT JOIN holdings h ON h.entity = d.entity {join}
            WHERE d.report_month = ?
            GROUP BY d.entity
            ORDER BY dividend DESC, d.yield_forecast DESC""", args)
        return {
            "month": month,
            "as_of": (one("SELECT as_of FROM dividends WHERE report_month=? LIMIT 1",
                          (month,)) or {}).get("as_of"),
            "months": [r["m"] for r in rows(
                "SELECT DISTINCT report_month m FROM dividends ORDER BY 1 DESC")],
            "total_dividend": sum(i["dividend"] for i in items),
            "held_count": sum(1 for i in items if i["customers"]),
            "items": items,
        }
    finally:
        c.close()


# ==========================================================================
# frontend
# ==========================================================================

if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        # เส้นทาง /api/... ที่ไม่มีจริงต้องตอบ 404 ไม่ใช่ส่งหน้าเว็บกลับไปให้คนเข้าใจผิดว่าสำเร็จ
        if path.startswith("api/"):
            raise HTTPException(404, f"ไม่มี endpoint /{path}")
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
