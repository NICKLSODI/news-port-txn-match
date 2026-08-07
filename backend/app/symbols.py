# -*- coding: utf-8 -*-
"""ตัวตัดสินว่ากราฟของแต่ละ entity มาจากไหน — สำหรับหน้า "หาจากหุ้น"

entity ในระบบเป็นรูปแบบ TICKER:MIC (หุ้นนอก) หรือชื่อเปล่า (หุ้นไทย คริปโต กองทุน)
ผู้ให้บริการทั้งสองใช้รูปแบบสัญลักษณ์คนละแบบ จึงมีตารางแปลงอยู่ที่นี่ทั้งคู่

  ตลาดที่ widget ฟรีของ TradingView ให้ข้อมูล -> widget (ข้อมูลของ TradingView เอง)
  ตลาดที่เหลือ + หุ้นไทย                      -> Yahoo Finance เราวาดแท่งเทียนเอง (prices.py)
  กองทุนไทย / ตราสารเฉพาะ                     -> ไม่มีกราฟ ทั้งสองที่ไม่มีข้อมูล

TV_OK มาจากการทดลองยิงจริงทีละตลาด (ดู scratchpad/probe_venues.py) ไม่ใช่การเดา
ตลาดนอกลิสต์นี้ widget จะขึ้นกล่อง "สัญลักษณ์นี้มีเฉพาะใน TradingView เท่านั้น"
แล้วกราฟว่างเปล่า — SET HKEX TSE LSE EURONEXT SGX KRX TWSE NSE ล้วนถูกกัน
ถ้าวันหน้าบริษัทซื้อสิทธิ์ข้อมูลกับ TradingView ให้เพิ่มตลาดเข้า TV_OK ได้เลย
"""
from __future__ import annotations

# MIC ที่ระบบใช้ (ดู tables.SUFFIX_TO_MIC) -> ชื่อตลาดของ TradingView
MIC_TO_TRADINGVIEW = {
    "xnas": "NASDAQ", "xnys": "NYSE", "arcx": "AMEX", "xase": "AMEX", "bats": "AMEX",
    "xhkg": "HKEX", "xtks": "TSE", "xlon": "LSE", "xpar": "EURONEXT",
    "xetr": "XETR", "xswx": "SIX", "xvtx": "SIX", "xtsx": "TSX", "tsxv": "TSXV",
    "xasx": "ASX", "sgx": "SGX", "xkrx": "KRX", "kosdaq": "KRX", "xtai": "TWSE",
    "xstc": "HOSE", "upcom": "HNX", "xshe": "SZSE", "xshg": "SSE",
    "xmil": "MIL", "xams": "EURONEXT", "xhel": "OMXHEX", "xmce": "BME",
    "xnse": "NSE", "xbom": "BSE", "xidx": "IDX", "xkls": "MYX", "xphs": "PSE",
}

# ตลาดที่ยืนยันด้วยการทดลองแล้วว่า widget ฟรีแสดงข้อมูลได้จริง
TV_OK = {"NASDAQ", "NYSE", "AMEX", "XETR", "ASX", "TSX", "IDX", "SZSE", "SSE", "MIL", "CRYPTO"}

# MIC -> suffix ของ Yahoo (สหรัฐไม่มี suffix)
MIC_TO_YAHOO = {
    "xnas": "", "xnys": "", "arcx": "", "xase": "", "bats": "",
    "xhkg": ".HK", "xtks": ".T", "xlon": ".L", "xpar": ".PA", "xetr": ".DE",
    "xswx": ".SW", "xvtx": ".SW", "xtsx": ".TO", "tsxv": ".V", "xasx": ".AX",
    "sgx": ".SI", "xkrx": ".KS", "kosdaq": ".KQ", "xtai": ".TW", "xstc": ".VN",
    "upcom": ".VN", "xshe": ".SZ", "xshg": ".SS", "xmil": ".MI", "xams": ".AS",
    "xhel": ".HE", "xmce": ".MC", "xnse": ".NS", "xbom": ".BO", "xidx": ".JK",
    "xkls": ".KL", "xphs": ".PS",
}

CRYPTO = {"BTC", "ETH", "XRP", "SOL", "DOGE", "ADA", "BNB", "AVAX", "DOT", "LTC",
          "LINK", "MATIC", "TRX", "TON", "SUI", "NEAR", "APT", "USDT", "USDC"}


def is_thai(entity: str) -> bool:
    """หุ้นไทยในระบบเป็นชื่อเปล่าไม่มี MIC — กองทุนไทยมีวงเล็บหรือขีดจึงคัดออก"""
    e = (entity or "").strip()
    return bool(e) and ":" not in e and e not in CRYPTO and e.isalnum() \
        and e.upper() == e and len(e) <= 8


def to_tradingview(entity: str) -> str | None:
    """คืน VENUE:TICKER เท่าที่ widget ฟรีแสดงได้ ไม่งั้นคืน None"""
    e = (entity or "").strip()
    if not e:
        return None
    if ":" in e:
        sym, mic = e.rsplit(":", 1)
        venue = MIC_TO_TRADINGVIEW.get(mic.lower())
        if not venue or venue not in TV_OK:
            return None
        if mic.lower() == "xhkg":
            sym = sym.lstrip("0")                    # 00700 -> HKEX:700
        return f"{venue}:{sym}"
    if e in CRYPTO:
        return f"CRYPTO:{e}USD"
    return None                                      # SET ถูกกันในเวอร์ชันฝังฟรี


def to_yahoo(entity: str) -> str | None:
    """คืนสัญลักษณ์ Yahoo (None = Yahoo ไม่มีตัวนี้ เช่นกองทุนไทย)"""
    e = (entity or "").strip()
    if not e:
        return None
    if ":" in e:
        sym, mic = e.rsplit(":", 1)
        suffix = MIC_TO_YAHOO.get(mic.lower())
        if suffix is None:
            return None
        if mic.lower() == "xhkg":
            sym = sym.lstrip("0").rjust(4, "0")      # 00700 -> 0700.HK
        return f"{sym}{suffix}"
    if e in CRYPTO:
        return f"{e}-USD"
    return f"{e}.BK" if is_thai(e) else None


def provider(entity: str) -> str:
    """'tradingview' | 'yahoo' | 'none' — กราฟของตัวนี้มาจากไหน"""
    if to_tradingview(entity):
        return "tradingview"
    if to_yahoo(entity):
        return "yahoo"
    return "none"
