# -*- coding: utf-8 -*-
"""ราคาแท่งเทียนย้อนหลังจาก Yahoo Finance — ใช้กับหุ้นไทย

ทำไมหุ้นไทยต้องใช้ทางนี้: widget ของ TradingView แบบฝังฟรีไม่ให้ข้อมูลตลาด SET
(ขึ้นว่า "สัญลักษณ์นี้มีเฉพาะใน TradingView เท่านั้น" แล้วกราฟว่าง) ส่วนหุ้นต่างประเทศ
กับคริปโตใช้ widget ได้ปกติ — ดู symbols.py ที่เป็นตัวตัดสินว่าตัวไหนไปทางไหน

ทำไมไม่ยิงจากเบราว์เซอร์ตรง ๆ:
  1. Yahoo ไม่ส่ง CORS ให้ เบราว์เซอร์ยิงข้ามโดเมนไม่ได้
  2. เก็บ cache ในฐานข้อมูลเดียวกัน เปิดหน้าเดิมซ้ำไม่ต้องยิงใหม่
  3. ถ้าวันหน้าเปลี่ยนไปใช้ feed ที่บริษัทมีสิทธิ์ใช้ (SET / Refinitiv) แก้ไฟล์นี้ไฟล์เดียว

ข้อควรรู้: endpoint chart ของ Yahoo เป็นของสาธารณะแต่ไม่ใช่ API ที่มีสัญญา
ใช้กับเครื่องมือภายในได้ แต่ห้ามเอาข้อมูลไปแจกจ่ายต่อ
"""
from __future__ import annotations

import datetime as dt
import json
import time

import requests

CHART_API = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}
CACHE_TTL_SECONDS = 30 * 60          # แท่งรายวันไม่ต้องสดกว่านี้
CACHE_VERSION = "v2"                 # เปลี่ยนเมื่อรูปแบบ payload เปลี่ยน (v1 = ราคาปิดเท่านั้น)
RATE_LIMIT_SECONDS = 0.3
_last_call = [0.0]
_session = requests.Session()

RANGES = {"1mo": "1d", "3mo": "1d", "6mo": "1d", "1y": "1d", "2y": "1wk", "5y": "1wk"}


def _fetch(symbol: str, rng: str) -> dict | None:
    gap = time.monotonic() - _last_call[0]
    if gap < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - gap)
    try:
        r = _session.get(CHART_API.format(symbol=symbol), headers=HEADERS, timeout=20,
                         params={"range": rng, "interval": RANGES.get(rng, "1d")})
        _last_call[0] = time.monotonic()
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:                                # noqa: BLE001
        return None


def _parse(payload: dict) -> dict | None:
    res = ((payload or {}).get("chart") or {}).get("result") or []
    if not res:
        return None
    q = res[0]
    meta = q.get("meta") or {}
    ts = q.get("timestamp") or []
    quote = ((q.get("indicators") or {}).get("quote") or [{}])[0]
    o, h, l, c, v = (quote.get(k) or [] for k in ("open", "high", "low", "close", "volume"))

    bars = []
    for i, t in enumerate(ts):
        row = [x[i] if i < len(x) else None for x in (o, h, l, c)]
        if any(x is None for x in row):               # วันหยุด/วันที่ตลาดไม่มีการซื้อขาย
            continue
        bars.append({"d": dt.datetime.utcfromtimestamp(t).date().isoformat(),
                     "o": row[0], "h": row[1], "l": row[2], "c": row[3],
                     "v": (v[i] if i < len(v) else None) or 0})
    if len(bars) < 2:
        return None

    first, last = bars[0]["c"], bars[-1]["c"]
    return {
        "bars": bars,
        "last": last,
        "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
        "change_pct": (last / first - 1) if first else None,
        "day_change_pct": (last / bars[-2]["c"] - 1) if bars[-2]["c"] else None,
        "w52_low": meta.get("fiftyTwoWeekLow"), "w52_high": meta.get("fiftyTwoWeekHigh"),
    }


def series(con, symbol: str, rng: str = "6mo", force: bool = False) -> dict:
    """แท่งเทียนของสัญลักษณ์ Yahoo — อ่านจาก cache ถ้ายังไม่หมดอายุ"""
    rng = rng if rng in RANGES else "6mo"
    out: dict = {"cached": False, "series": None, "note": None, "fetched_at": None}

    key = f"{symbol}|{rng}|{CACHE_VERSION}"
    row = con.execute("SELECT fetched_at, payload FROM price_cache WHERE k=?", (key,)).fetchone()
    now = dt.datetime.now()
    if row and not force:
        try:
            age = (now - dt.datetime.fromisoformat(row["fetched_at"])).total_seconds()
        except ValueError:
            age = CACHE_TTL_SECONDS + 1
        if age <= CACHE_TTL_SECONDS:
            out.update({"cached": True, "fetched_at": row["fetched_at"],
                        "series": json.loads(row["payload"])})
            return out

    parsed = _parse(_fetch(symbol, rng) or {})
    if not parsed:
        if row:                                      # ยิงไม่ได้ ใช้ของเก่าไปก่อน ดีกว่าจอว่าง
            out.update({"cached": True, "fetched_at": row["fetched_at"],
                        "series": json.loads(row["payload"]),
                        "note": "ดึงราคาใหม่ไม่สำเร็จ กำลังแสดงข้อมูลที่เก็บไว้ก่อนหน้า"})
            return out
        out["note"] = "ดึงราคาจาก Yahoo Finance ไม่สำเร็จ"
        return out

    stamp = now.isoformat(timespec="seconds")
    with con:
        con.execute("INSERT INTO price_cache(k, symbol, range_, fetched_at, payload) "
                    "VALUES(?,?,?,?,?) ON CONFLICT(k) DO UPDATE SET "
                    "fetched_at=excluded.fetched_at, payload=excluded.payload",
                    (key, symbol, rng, stamp, json.dumps(parsed, ensure_ascii=False)))
    out.update({"fetched_at": stamp, "series": parsed})
    return out
