# -*- coding: utf-8 -*-
"""ดึงข้อมูลบริษัท (sector/industry) จาก Yahoo Finance quoteSummary

ใช้เฉพาะจาก scripts/propose.py (propose_offshore_sector) — ไม่ได้อยู่ใน runtime
pipeline และไม่มี endpoint ไหนในเว็บเรียกโมดูลนี้โดยตรง Yahoo ปิดการเรียกแบบไม่มี
cookie/crumb แล้ว จึงต้องขอ session ก่อนทุกครั้งที่ crumb หมดอายุ/ยังไม่มี
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_cookie: str | None = None
_crumb: str | None = None

# MIC (ตามที่เก็บใน entity id ของระบบ) -> suffix สัญลักษณ์ที่ Yahoo ใช้
# ตลาดที่ไม่อยู่ในนี้ (เช่นเวียดนาม) ถือว่า Yahoo ไม่รองรับ ข้ามไปเงียบ ๆ
MIC_TO_YAHOO_SUFFIX = {
    "xnas": "", "xnys": "", "xase": "", "arcx": "", "bats": "",
    "xhkg": ".HK", "xtks": ".T", "xkrx": ".KS", "kosdaq": ".KQ",
    "xtai": ".TW", "sgx": ".SI", "xshg": ".SS", "xshe": ".SZ",
    "xlon": ".L", "xetr": ".DE", "xpar": ".PA", "xams": ".AS",
    "xswx": ".SW", "xmce": ".MC", "xmil": ".MI", "xasx": ".AX",
    "xnse": ".NS", "xbom": ".BO", "xtsx": ".TO", "xidx": ".JK",
}


def to_yahoo_symbol(entity: str) -> str | None:
    """"AAPL:xnas" -> "AAPL" · "09988:xhkg" -> "9988.HK" · ตลาดที่ไม่รองรับคืน None"""
    if ":" not in entity:
        return None
    root, mic = entity.split(":", 1)
    mic = mic.lower()
    if mic not in MIC_TO_YAHOO_SUFFIX:
        return None
    if mic == "xhkg" and root.isdigit():
        root = str(int(root)).zfill(4)
    return f"{root}{MIC_TO_YAHOO_SUFFIX[mic]}"


def _refresh_session() -> None:
    """ขอ cookie จาก fc.yahoo.com แล้วแลก crumb — ต้องทำก่อนเรียก quoteSummary เสมอ

    fc.yahoo.com ตอบ 404 เสมอ (หน้า error ปกติของ endpoint นี้) แต่ยังฝัง
    Set-Cookie มาด้วย — คุกกี้ตรงนี้คือของจริงที่ต้องใช้ ไม่ใช่ความล้มเหลว
    """
    global _cookie, _crumb
    req = urllib.request.Request("https://fc.yahoo.com", headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            cookies = r.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as e:
        cookies = e.headers.get_all("Set-Cookie") or []
    _cookie = "; ".join(c.split(";", 1)[0] for c in cookies)
    req = urllib.request.Request(
        "https://query1.finance.yahoo.com/v1/test/getcrumb",
        headers={"User-Agent": _UA, "Cookie": _cookie or ""},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        _crumb = r.read().decode("utf-8").strip()


def fetch_sector(symbol: str, *, retries: int = 1) -> dict | None:
    """คืน {"sector", "sector_key", "industry"} หรือ None ถ้าไม่พบ/ตลาดปิดบริการ"""
    global _cookie, _crumb
    if not _cookie or not _crumb:
        _refresh_session()
    url = ("https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
           f"{urllib.parse.quote(symbol)}?modules=assetProfile&crumb={urllib.parse.quote(_crumb or '')}")
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Cookie": _cookie or ""})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        if retries > 0:
            _cookie = _crumb = None  # crumb อาจหมดอายุ — ขอใหม่แล้วลองอีกครั้งเดียว
            time.sleep(1)
            return fetch_sector(symbol, retries=retries - 1)
        return None
    result = (data.get("quoteSummary") or {}).get("result") or []
    if not result:
        return None
    prof = result[0].get("assetProfile") or {}
    sector = prof.get("sector")
    if not sector:
        return None
    return {"sector": sector, "sector_key": prof.get("sectorKey"), "industry": prof.get("industry")}
