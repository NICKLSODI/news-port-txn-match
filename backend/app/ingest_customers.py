# -*- coding: utf-8 -*-
"""STEP1 + STEP5 — นำเข้าไฟล์ลูกค้า แล้วคำนวณคุณสมบัติ + persona

ทำตามกฎ R1.1 - R1.20 และ CF-01 - CF-10 / R5.1 - R5.4
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from . import db
from .mapping import Universe, map_holding, tfex_expiry
from .tables import (
    ASSET_CLASS_BY_TXT_KEY,
    ASSET_CLASS_FALLBACK,
    DORMANT_DAYS,
    PERSONA_BY_DOMINANT,
    PORTFOLIO_TIERS,
    TRADE_FREQ_BANDS,
    TXN_DIRECTION,
    WATCHLIST_WINDOW_DAYS,
)
from .mapping import sector_of

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# ชื่อคอลัมน์ในไฟล์ที่ได้รับ -> field ตาม Data Contract
HOLDING_COLS = {
    "customer_key": "customer_key",     # H-01
    "account_key": "account_key",       # H-02
    "m_id": "rm_id",                    # H-03
    "product_code": "product_code",     # H-04
    "product_txt_key": "asset_subclass",  # H-06 -> ใช้แปลงเป็น H-05
    "aum": "holding_value",             # H-07
    "thb_unrealized_avg": "unrealized_pnl",  # H-08
    "record_date": "as_of_date",        # H-09
}
TXN_COLS = {
    "customer_key": "customer_key",     # T-01
    "account_key": "account_key",       # T-02
    "m_id": "rm_id",                    # T-03
    "product_code": "product_code",     # T-04
    "product_txt_key": "asset_subclass",  # T-06
    "record_date": "txn_date",          # T-07
    "txn_type": "txn_type",             # T-08
    "confirm_unit": "txn_units",        # T-09
    "trading_value": "txn_value",       # T-10
}


def _find(patterns: list[str]) -> Path:
    for p in sorted(DATA_DIR.glob("*.xlsx")):
        low = p.name.lower()
        if any(pat in low for pat in patterns):
            return p
    raise FileNotFoundError(f"ไม่พบไฟล์ที่ตรงกับ {patterns} ใน {DATA_DIR}")


# คู่มือ mask สั่งให้ตั้งชื่อคอลัมน์ RM ว่า rm_id แต่ไฟล์จากทีม Data ใช้ m_id
# รับทั้งสองชื่อ ไม่ให้ผู้ใช้ต้องมาเดาว่าเอกสารไหนถูก
ALIASES = {"rm_id": "m_id"}


def _read(path: Path) -> pd.DataFrame:
    # keep_default_na=False — ไฟล์ต้นทางใช้คำว่า 'null' เป็นข้อความจริง (R1.1)
    df = pd.read_excel(path, sheet_name=0, dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    return apply_aliases(df)


def apply_aliases(df: pd.DataFrame) -> pd.DataFrame:
    for src, dst in ALIASES.items():
        if src in df.columns and dst not in df.columns:
            df = df.rename(columns={src: dst})
    return df


def _num(v) -> float | None:
    s = str(v).strip().replace(",", "")
    if not s or s.lower() in ("null", "none", "nan", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _date(v) -> str | None:
    s = str(v).strip()
    if not s or s.lower() in ("null", "nan", ""):
        return None
    return s[:10]


def _rename(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    missing = [c for c in mapping if c not in df.columns]
    if missing:
        raise ValueError(f"ไฟล์ขาดคอลัมน์ {missing} — ไฟล์ไม่ผ่าน Data Contract (STEP1)")
    return df[list(mapping)].rename(columns=mapping)


# ==========================================================================

def ingest(con, now: str | None = None, holdings_path: Path | None = None,
           txn_path: Path | None = None) -> dict:
    """นำเข้าไฟล์ลูกค้า — ระบุ path ตรง ๆ ได้ (ใช้ตอนอัปโหลด อ่านจากไฟล์ชั่วคราว
    ก่อนจะไปแตะไฟล์จริงใน data/) ไม่ระบุ = หาในโฟลเดอร์ data ตามเดิม
    """
    now = now or dt.datetime.now().isoformat(timespec="seconds")
    ph = holdings_path or _find(["portfolio", "port"])
    pt = txn_path or _find(["t_match", "txn", "transaction"])

    hold = _rename(_read(ph), HOLDING_COLS)
    txn = _rename(_read(pt), TXN_COLS)

    # R1.3 — แถวที่ไม่มี customer_key ระบุเจ้าของไม่ได้ ต้องทิ้งและรายงาน
    # ถ้าเก็บไว้ ทุกแถวจะรวมกันเป็น "ลูกค้า" ปลอมหนึ่งคนที่ไม่มีอยู่จริง แล้วโผล่ในรายชื่อที่ต้องโทร
    dropped_no_key = {}
    for name, df in (("holdings", hold), ("transactions", txn)):
        key = df.customer_key.astype(str).str.strip()
        bad = key.eq("") | key.str.lower().eq("null")
        n = int(bad.sum())
        if n:
            dropped_no_key[name] = n
            db.report_unmapped(con, "customer_key", "(ว่าง)", "R1.3",
                               f"{name}: {n} แถวไม่มี customer_key — ข้ามทั้งแถว", now=now)
        df.drop(df.index[bad.values], inplace=True)

    # --- R1.5 asset_class + รายงาน enum ที่ไม่รู้จัก -------------------------
    unknown_keys: set[str] = set()

    def to_class(key: str) -> str:
        k = (key or "").strip()
        if k in ASSET_CLASS_BY_TXT_KEY:
            return ASSET_CLASS_BY_TXT_KEY[k]
        unknown_keys.add(k)
        return ASSET_CLASS_FALLBACK

    hold["asset_class"] = hold.asset_subclass.map(to_class)
    txn["asset_class"] = txn.asset_subclass.map(to_class)

    for k in unknown_keys:
        db.report_unmapped(con, "asset_class", k or "(ว่าง)", "R1.5",
                           "product_txt_key ที่ไม่รู้จัก — จัดเข้า OTHER", now=now)

    # --- pass 1: แปลงรหัสแบบไม่ใช้ universe เพื่อสร้าง universe ก่อน ----------
    uni = Universe()
    for code, ac in set(zip(hold.product_code, hold.asset_class)):
        r = map_holding(code, ac)
        if r.ok and r.kind in ("stock", "crypto", "fund"):
            uni.add(r.entity)
    for code, ac in set(zip(txn.product_code, txn.asset_class)):
        r = map_holding(code, ac)
        if r.ok and r.kind in ("stock", "crypto", "fund"):
            uni.add(r.entity)

    # --- pass 2: แปลงจริง (คลี่ underlying ของ Options / DR / TFEX / KIKO) ---
    cache: dict[tuple, object] = {}

    def m(code, ac):
        key = (code, ac)
        if key not in cache:
            cache[key] = map_holding(code, ac, uni)
        return cache[key]

    data_as_of = max(
        [d for d in (_date(x) for x in hold.as_of_date) if d] +
        [d for d in (_date(x) for x in txn.txn_date) if d]
    )
    ref = dt.date.fromisoformat(data_as_of)

    with con:
        con.execute("DELETE FROM holdings")
        con.execute("DELETE FROM transactions")
        con.execute("DELETE FROM customers")

        # ---------------- holdings ----------------
        rows, skipped_r16 = [], 0
        for r in hold.itertuples(index=False):
            res = m(r.product_code, r.asset_class)
            if res.rule == "R1.6":
                skipped_r16 += 1
                continue
            if not res.ok:
                db.report_unmapped(con, "holding_code", str(r.product_code), res.rule,
                                   res.note, ref=r.asset_class, now=now)
            rows.append((r.customer_key, r.account_key, r.rm_id, r.product_code,
                         r.asset_class, r.asset_subclass, _num(r.holding_value),
                         _num(r.unrealized_pnl), _date(r.as_of_date), res.entity,
                         res.kind, res.confidence, res.rule, res.instrument_label))
        con.executemany(
            """INSERT INTO holdings(customer_key,account_key,rm_id,product_code,asset_class,
                 asset_subclass,holding_value,unrealized_pnl,as_of_date,entity,entity_kind,
                 entity_confidence,map_rule,instrument_label)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)

        # ---------------- transactions ----------------
        trows = []
        for r in txn.itertuples(index=False):
            direction = TXN_DIRECTION.get((r.txn_type or "").strip())
            if direction is None:
                db.report_unmapped(con, "txn_type", str(r.txn_type) or "(ว่าง)", "R1.5",
                                   "txn_type ที่ไม่รู้จัก", now=now)
                direction = "IGNORE"
            res = m(r.product_code, r.asset_class)
            trows.append((r.customer_key, r.account_key, r.rm_id, r.product_code,
                          r.asset_class, r.asset_subclass, _date(r.txn_date), r.txn_type,
                          direction, _num(r.txn_units), _num(r.txn_value),
                          res.entity, res.kind, res.instrument_label))
        con.executemany(
            """INSERT INTO transactions(customer_key,account_key,rm_id,product_code,asset_class,
                 asset_subclass,txn_date,txn_type,txn_direction,txn_units,txn_value,entity,
                 entity_kind,instrument_label)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", trows)

        db.set_setting(con, "data_as_of", data_as_of)
        db.set_setting(con, "holdings_as_of", max(d for d in (_date(x) for x in hold.as_of_date) if d))
        db.set_setting(con, "customers_ingested_at", now)

    stats = build_features(con, ref, now)
    stats.update({"holdings_rows": len(rows), "txn_rows": len(trows),
                  "skipped_cash_rows_R1_6": skipped_r16, "data_as_of": data_as_of,
                  "skipped_no_customer_key_R1_3": dropped_no_key,
                  "unknown_enums": sorted(unknown_keys)})
    return stats


# ==========================================================================
# STEP5 — CF-01 .. CF-10 + persona
# ==========================================================================

def build_features(con, ref: dt.date, now: str) -> dict:
    """คำนวณคุณสมบัติลูกค้าใหม่ทั้งชุด (R5.4 ห้าม cache ข้ามรอบ)"""
    holdings_as_of = dt.date.fromisoformat(db.get_setting(con, "holdings_as_of", ref.isoformat()))

    hv: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))   # CF-04
    labels: dict[str, dict[str, str]] = defaultdict(dict)
    mix: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))  # CF-02
    pnl: dict[str, float] = defaultdict(float)
    pnl_known: dict[str, bool] = defaultdict(bool)
    rm_latest: dict[str, tuple[str, str]] = {}                                  # R1.9
    tfex_net: dict[tuple[str, str], float] = defaultdict(float)                 # R1.10
    tfex_entity: dict[str, tuple[str, str]] = {}
    last_traded: dict[str, dict[str, str]] = defaultdict(dict)                  # CF-05/R6.11
    txn_count: dict[str, int] = defaultdict(int)                                # CF-06
    last_any: dict[str, str] = {}                                               # CF-07
    post_snapshot: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))  # R1.17

    for r in con.execute("SELECT * FROM holdings"):
        c, e = r["customer_key"], r["entity"]
        val = r["holding_value"] or 0.0
        mix[c][r["asset_class"]] += val
        if r["unrealized_pnl"] is not None:
            pnl[c] += r["unrealized_pnl"]
            pnl_known[c] = True
        if e:
            hv[c][e] += val
            if r["instrument_label"]:
                labels[c][e] = r["instrument_label"]
        rm_latest[c] = max(rm_latest.get(c, ("", "")), (r["as_of_date"] or "", r["rm_id"] or ""))

    for r in con.execute("SELECT * FROM transactions ORDER BY txn_date"):
        c, e, d = r["customer_key"], r["entity"], r["txn_date"]
        if r["txn_direction"] == "IGNORE":
            continue
        txn_count[c] += 1
        last_any[c] = max(last_any.get(c, ""), d or "")
        rm_latest[c] = max(rm_latest.get(c, ("", "")), (d or "", r["rm_id"] or ""))

        if r["txn_direction"] in ("DERIVATIVE_LONG", "DERIVATIVE_SHORT"):
            # R1.10 — สถานะ TFEX = Buy(Long) ลบ Sell(Short) ต่อคู่ ลูกค้า+สัญญา
            sign = 1 if r["txn_direction"] == "DERIVATIVE_LONG" else -1
            key = (c, r["product_code"] or "")
            tfex_net[key] += sign * (r["txn_units"] or 0.0)
            if e:
                tfex_entity[r["product_code"] or ""] = (e, r["instrument_label"] or "tfex")

        if e:
            last_traded[c][e] = max(last_traded[c].get(e, ""), d or "")
            # R1.17 — ธุรกรรมที่เกิดหลังวัน snapshot ถือเป็นการถือครองด้วย
            if d and dt.date.fromisoformat(d) > holdings_as_of:
                delta = (r["txn_value"] or 0.0) * (1 if r["txn_direction"] == "INCREASE" else -1)
                post_snapshot[c][e] += delta

    # R1.10 / R1.12 — สถานะ TFEX ที่ยังเปิดอยู่
    tfex_open: dict[str, dict[str, float]] = defaultdict(dict)
    for (c, contract), net in tfex_net.items():
        if abs(net) < 1e-9:
            continue                                   # เปิดแล้วปิดครบ = ไม่มีสถานะ
        exp = tfex_expiry(contract)
        if exp and dt.date(exp[0], exp[1], 1) < ref.replace(day=1):
            continue                                   # R4.21 / R1.11 หมดอายุแล้ว
        if net < 0 and contract not in tfex_entity:
            db.report_unmapped(con, "tfex", contract, "R1.12",
                               "ผลรวมติดลบแต่ไม่พบรายการเปิด — ข้อมูลไม่ครบ", ref=c, now=now)
            continue
        ent, label = tfex_entity.get(contract, (None, "tfex"))
        if ent:
            tfex_open[c][ent] = net
            labels[c][ent] = label

    # R1.17 — เติมของที่ซื้อหลัง snapshot
    for c, adds in post_snapshot.items():
        for e, delta in adds.items():
            if delta > 0 and e not in hv[c]:
                hv[c][e] = delta

    all_customers = set(hv) | set(txn_count) | set(mix) | set(rm_latest)
    rows, persona_count = [], defaultdict(int)

    for c in sorted(all_customers):
        holds = {e: v for e, v in hv[c].items()}
        for e in tfex_open.get(c, {}):
            holds.setdefault(e, 0.0)

        total = sum(v for v in mix[c].values())
        asset_mix = {k: (v / total if total else 0.0) for k, v in mix[c].items() if v}

        # CF-01 dominant_asset_class — จาก holdings ก่อน ถ้าไม่มีใช้มูลค่าเทรด (R5.2)
        dominant = max(mix[c], key=lambda k: mix[c][k], default=None) if mix[c] else None
        if not dominant or total <= 0:
            tv: dict[str, float] = defaultdict(float)
            for r in con.execute(
                    "SELECT asset_class, SUM(COALESCE(txn_value,0)) s FROM transactions "
                    "WHERE customer_key=? AND txn_direction<>'IGNORE' GROUP BY asset_class", (c,)):
                tv[r["asset_class"]] += r["s"] or 0.0
            dominant = max(tv, key=lambda k: tv[k], default=None)

        # CF-03 sector_exposure — หุ้นไทยเท่านั้น ผ่านตาราง B3
        sect: dict[str, float] = defaultdict(float)
        if total:
            for e, v in holds.items():
                s = sector_of(e)
                if s:
                    sect[s] += v / total

        # CF-07 recency
        last = last_any.get(c)
        days = (ref - dt.date.fromisoformat(last)).days if last else 9999

        # CF-06 trade_frequency
        n = txn_count[c]
        freq = "inactive"
        for lo, name in TRADE_FREQ_BANDS:
            if n >= lo:
                freq = name
        if n == 0:
            freq = "inactive"

        # CF-05 watchlist — เทรดใน 90 วันแต่ไม่ถืออยู่
        watch = {e: d for e, d in last_traded[c].items()
                 if e not in holds and d and (ref - dt.date.fromisoformat(d)).days <= WATCHLIST_WINDOW_DAYS}

        # CF-08 portfolio_tier
        tier = "small"
        for lo, name in PORTFOLIO_TIERS:
            if total >= lo:
                tier = name
                break

        # R5.1 - R5.3 persona
        if days > DORMANT_DAYS and freq == "inactive":
            persona = "DORMANT"
        elif not dominant:
            persona = "NO_PORTFOLIO"
        elif dominant in ("FUND_DIY", "FUND_ROBO"):
            persona = "FUND_ROBO" if mix[c].get("FUND_ROBO", 0) > mix[c].get("FUND_DIY", 0) else "FUND_DIY"
        else:
            persona = PERSONA_BY_DOMINANT.get(dominant, "NO_PORTFOLIO")
        persona_count[persona] += 1

        # CF-09
        state = "unknown" if not pnl_known[c] else ("profit" if pnl[c] >= 0 else "loss")

        rows.append((
            c, rm_latest.get(c, ("", ""))[1], persona, dominant, total, tier, freq, days, n,
            state, len(holds), len(watch),
            db.jdump(asset_mix), db.jdump(dict(sect)), db.jdump(holds), db.jdump(labels[c]),
            db.jdump(watch), db.jdump(last_traded[c]),
        ))

    with con:
        con.executemany(
            """INSERT INTO customers(customer_key,rm_id,persona,dominant_asset_class,
                 portfolio_value,portfolio_tier,trade_frequency,days_since_last_trade,txn_count,
                 unrealized_state,n_holdings,n_watchlist,asset_mix,sector_exposure,holdings,
                 labels,watchlist,last_traded)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
        db.set_setting(con, "persona_counts", dict(persona_count))

    return {"customers": len(rows), "persona_counts": dict(persona_count)}


def load_customers(con) -> list[dict]:
    """โหลดลูกค้าพร้อม feature ที่ decode แล้ว — ใช้ตอนจับคู่"""
    out = []
    for r in con.execute("SELECT * FROM customers"):
        d = dict(r)
        for k in ("asset_mix", "sector_exposure", "holdings", "labels", "watchlist", "last_traded"):
            d[k] = db.jload(d[k], {}) or {}
        out.append(d)
    return out
