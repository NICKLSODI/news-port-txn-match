# -*- coding: utf-8 -*-
"""ตรวจไฟล์ที่ผู้ใช้อัปโหลด ก่อนปล่อยเข้าระบบ (STEP1 Data Contract + ภาคผนวก PII)

หลักการ: **ไม่ผ่าน = ไม่รับ** ไม่เดาแทนผู้ใช้ ไม่ซ่อมไฟล์ให้เอง (หลักการข้อ 3)
รับได้เฉพาะคู่ไฟล์ — HOLDINGS (Portfolio) กับ TRANSACTIONS (TXN) ที่ปิดบังแล้ว

error   = บล็อก นำเข้าไม่ได้
warning = นำเข้าได้ แต่ต้องรู้ว่าจะเสียอะไร
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path

import pandas as pd

from .ingest_customers import ALIASES, DATA_DIR, HOLDING_COLS, TXN_COLS, apply_aliases
from .tables import ASSET_CLASS_BY_TXT_KEY, TXN_DIRECTION

MAX_BYTES = 80 * 1024 * 1024          # ไฟล์ TXN จริงราว 12 MB — เผื่อโตได้อีกหลายเท่า
SAMPLE_ROWS = 4000                     # จำนวนแถวที่สแกนหา PII แบบละเอียด
ARCHIVE = DATA_DIR / "archive"

# ---------------------------------------------------------------- คอลัมน์ที่ต้องมี
# ชื่อ field ตาม Data Contract -> ชื่อคอลัมน์ที่ต้องมีในไฟล์ (ingest ใช้ชื่อฝั่งซ้าย)
REQUIRED = {
    "portfolio": list(HOLDING_COLS),
    "txn": list(TXN_COLS),
}
FIELD_ID = {
    "portfolio": {"customer_key": "H-01", "account_key": "H-02", "m_id": "H-03",
                  "product_code": "H-04", "product_txt_key": "H-06", "aum": "H-07",
                  "thb_unrealized_avg": "H-08", "record_date": "H-09"},
    "txn": {"customer_key": "T-01", "account_key": "T-02", "m_id": "T-03",
            "product_code": "T-04", "product_txt_key": "T-06", "record_date": "T-07",
            "txn_type": "T-08", "confirm_unit": "T-09", "trading_value": "T-10"},
}

# ---------------------------------------------------------------- คอลัมน์ PII ที่ห้ามมี
# ภาคผนวก PII ของ STEP1 — สี่ตัวแรกคือชื่อจริงในไฟล์ต้นทางของ INVX
FORBIDDEN_COLS = {
    "cardid": "เลขบัตรประชาชน",
    "cust_name_th": "ชื่อ-นามสกุลลูกค้า",
    "cust_name": "ชื่อลูกค้า",
    "customer_name": "ชื่อลูกค้า",
    "account": "เลขบัญชีจริง",
    "account_no": "เลขบัญชีจริง",
    "acct_no": "เลขบัญชีจริง",
    "marketing_name_th": "ชื่อ RM",
    "marketing_name": "ชื่อ RM",
    "rm_name": "ชื่อ RM",
    "citizen_id": "เลขบัตรประชาชน",
    "national_id": "เลขบัตรประชาชน",
    "id_card": "เลขบัตรประชาชน",
    "passport": "เลขพาสปอร์ต",
    "tax_id": "เลขผู้เสียภาษี",
    "phone": "เบอร์โทร",
    "mobile": "เบอร์โทร",
    "tel": "เบอร์โทร",
    "email": "อีเมล",
    "address": "ที่อยู่",
    "birth_date": "วันเกิด",
    "birthdate": "วันเกิด",
    "dob": "วันเกิด",
}

_ID13 = re.compile(r"(?<!\d)\d{13}(?!\d)")            # เลขบัตรประชาชนไทย
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?<!\d)0\d{8,9}(?!\d)")
_THAI = re.compile(r"[฀-๿]")
_DATE10 = re.compile(r"^\d{4}-\d{2}-\d{2}")
# รหัสแทนตัวจริงยอมรับได้หลายแบบ (CUST00001 หรือ hash) แต่ห้ามเป็นเลขล้วนยาว ๆ
# เพราะนั่นคือเลขบัตร/เลขบัญชีจริง และห้ามมีช่องว่างเพราะนั่นคือชื่อคน
_KEY_BAD = re.compile(r"\s|^\d{9,}$")
_XLERR = re.compile(r"#(N/A|REF!|VALUE!|NAME\?|DIV/0!|NUM!|NULL!)")


class Report(dict):
    """dict ธรรมดา แต่เพิ่มเมธอดสั้น ๆ ให้เขียนโค้ดตรวจอ่านง่าย"""

    def err(self, code: str, th: str, en: str, detail=None) -> None:
        self["errors"].append({"code": code, "th": th, "en": en, "detail": detail})

    def warn(self, code: str, th: str, en: str, detail=None) -> None:
        self["warnings"].append({"code": code, "th": th, "en": en, "detail": detail})


def _new_report(kind: str, filename: str, size: int) -> Report:
    return Report(kind=kind, filename=filename, size=size, rows=0, sheet=None,
                  columns=[], errors=[], warnings=[], stats={})


def _norm(c: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", str(c).strip().lower())


def check_excel(path: Path, kind: str, filename: str, size: int) -> tuple[Report, pd.DataFrame | None]:
    """ตรวจไฟล์เดียว — คืน report ที่ frontend เอาไปแสดงได้ตรง ๆ พร้อม DataFrame ที่อ่านแล้ว

    คืน df ออกมาด้วยเพราะไฟล์ TXN จริงหลายสิบเมกะไบต์ อ่านซ้ำรอบสองแพงเกินจำเป็น
    """
    rep = _new_report(kind, filename, size)

    if size > MAX_BYTES:
        rep.err("too_big", f"ไฟล์ใหญ่เกิน {MAX_BYTES // 1024 // 1024} MB",
                f"File exceeds {MAX_BYTES // 1024 // 1024} MB", {"size": size})
        return rep, None
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        rep.err("not_xlsx", "รับเฉพาะไฟล์ .xlsx (Save As จาก Excel)",
                "Only .xlsx is accepted (Save As from Excel)")
        return rep, None

    try:
        # ต้องปิด handle ให้เรียบร้อย ไม่งั้น Windows ลบไฟล์ชั่วคราวไม่ได้ (WinError 32)
        with pd.ExcelFile(path) as xl:
            rep["sheet"] = str(xl.sheet_names[0])
            rep["all_sheets"] = [str(s) for s in xl.sheet_names]
            df = xl.parse(xl.sheet_names[0], dtype=str, keep_default_na=False)
    except Exception as e:                                     # noqa: BLE001
        rep.err("unreadable", f"เปิดไฟล์ไม่ได้: {e}", f"Cannot open the file: {e}")
        return rep, None

    df.columns = [str(c).strip() for c in df.columns]
    rep["columns"] = list(df.columns)
    # คู่มือ mask ตั้งชื่อคอลัมน์ RM ว่า rm_id — รับให้เท่ากับ m_id แล้วบอกผู้ใช้ว่ารับให้
    renamed = {s: d for s, d in ALIASES.items() if s in df.columns and d not in df.columns}
    if renamed:
        df = apply_aliases(df)
        for src, dst in renamed.items():
            rep.warn("column_alias", f"ไฟล์ใช้ชื่อคอลัมน์ {src} — ระบบอ่านเป็น {dst} ให้",
                     f"The file uses {src} — read as {dst}", {"from": src, "to": dst})
    rep["rows"] = int(len(df))
    if not len(df):
        rep.err("empty", "ไฟล์ไม่มีข้อมูล (แถวว่าง)", "The file has no data rows")
        return rep, df

    # ---------------- ชีตแปลงกลับต้องไม่ติดมา (กฎเหล็กข้อ 2) ----------------
    leaked = [s for s in rep["all_sheets"][1:] if _norm(s) in
              ("customer_map", "account_map", "rm_map", "map", "mapping")]
    if leaked:
        rep.err("map_sheet_leaked",
                f"มีชีตตารางแปลงกลับติดมาด้วย: {', '.join(leaked)} — ห้ามส่งออกจากทีม Data",
                f"Re-identification map sheets are still inside: {', '.join(leaked)}",
                {"sheets": leaked})

    # ---------------- คอลัมน์ PII ที่ห้ามมี ----------------
    norm_map = {_norm(c): c for c in df.columns}
    for bad, what in FORBIDDEN_COLS.items():
        if bad in norm_map:
            rep.err("pii_column", f"ยังมีคอลัมน์ {norm_map[bad]} ({what}) — ต้องลบก่อนส่ง",
                    f"Column {norm_map[bad]} ({what}) must be removed before upload",
                    {"column": norm_map[bad]})

    # ---------------- คอลัมน์ที่สัญญาข้อมูลบังคับ ----------------
    missing = [c for c in REQUIRED[kind] if c not in df.columns]
    if missing:
        rep.err("missing_columns",
                f"ขาดคอลัมน์ {', '.join(missing)}",
                f"Missing columns: {', '.join(missing)}",
                {"columns": missing, "field_ids": [FIELD_ID[kind].get(c) for c in missing]})

    # ตรวจต่อได้เท่าที่คอลัมน์มี
    def col(name: str) -> pd.Series | None:
        return df[name] if name in df.columns else None

    # ---------------- สูตรที่ยังไม่ paste as values ----------------
    # Excel เก็บทั้งสูตรและค่าที่คำนวณไว้ อ่านออกมาจึงอาจได้ค่าปกติ ค่าว่าง หรือ #N/A
    # ทั้งสามแบบแปลว่าไฟล์ยังผูกกับชีตตารางแปลงอยู่ ไม่ปลอดภัยที่จะเอาเข้าระบบ
    head = df.head(SAMPLE_ROWS)
    for name in ("customer_key", "account_key", "m_id"):
        s = col(name)
        if s is None:
            continue
        vals = s.head(SAMPLE_ROWS).astype(str)
        n = int(vals.str.startswith("=").sum())
        if n:
            rep.err("formula_left", f"คอลัมน์ {name} ยังเป็นสูตร ({n} แถว) — ต้องแปลงเป็นค่าคงที่",
                    f"Column {name} still holds formulas ({n} rows) — paste as values first",
                    {"column": name, "rows": n})
        errv = sorted({v for v in vals.tolist() if _XLERR.search(v)})[:5]
        if errv:
            rep.err("formula_error",
                    f"คอลัมน์ {name} มีค่าผิดพลาดจากสูตร ({', '.join(errv)}) "
                    "— ตารางแปลงหาไม่เจอ ต้องแก้แล้ว paste as values",
                    f"Column {name} contains formula errors ({', '.join(errv)}) — the lookup failed",
                    {"column": name, "samples": errv})

    # ---------------- รหัสแทนตัวจริง ----------------
    ck = col("customer_key")
    if ck is not None:
        vals = ck.astype(str).str.strip()
        blank = int(((vals == "") | (vals.str.lower() == "null")).sum())
        rep["stats"]["blank_customer_key"] = blank
        if blank == len(vals):
            rep.err("customer_key_all_blank", "ทุกแถวไม่มี customer_key — ระบุลูกค้าไม่ได้เลย (R1.3)",
                    "No row has a customer_key — customers cannot be identified (R1.3)")
        elif blank:
            rep.warn("customer_key_blank",
                     f"customer_key ว่าง {blank} แถว — ระบบข้ามแถวเหล่านี้ ระบุเจ้าของไม่ได้ (R1.3)",
                     f"{blank} rows have no customer_key — skipped, no owner to attribute them to (R1.3)",
                     {"rows": blank})
        uniq = vals[vals != ""].unique().tolist()
        rep["stats"]["customers"] = len(uniq)
        bad_shape = [v for v in uniq[:5000] if _KEY_BAD.search(v)][:8]
        if bad_shape:
            rep.err("customer_key_shape",
                    f"customer_key ยังเป็นค่าจริง เช่น {', '.join(bad_shape)} "
                    "— ต้องแทนด้วยรหัสที่คงที่ทุกรอบ เช่น CUST00001 (R1.3)",
                    f"customer_key still holds real values, e.g. {', '.join(bad_shape)} "
                    "— replace with a stable surrogate key such as CUST00001 (R1.3)",
                    {"samples": bad_shape})
        thai = [v for v in uniq[:5000] if _THAI.search(v)][:5]
        if thai:
            rep.err("customer_key_name", "customer_key มีตัวอักษรไทย — น่าจะเป็นชื่อคน ไม่ใช่รหัส",
                    "customer_key contains Thai letters — that looks like a name, not a key",
                    {"samples": thai})

    rm = col("m_id")
    if rm is not None:
        uniq = rm.astype(str).str.strip().unique().tolist()
        rep["stats"]["rms"] = len([v for v in uniq if v])
        thai = [v for v in uniq if _THAI.search(v)][:5]
        if thai:
            rep.err("rm_name", f"m_id ยังเป็นชื่อ RM เช่น {', '.join(thai)} — ต้องแปลงเป็นรหัส (R1.9)",
                    f"m_id still holds RM names, e.g. {', '.join(thai)} — use a code instead (R1.9)",
                    {"samples": thai})

    ak = col("account_key")
    if ak is not None:
        uniq = [v for v in ak.astype(str).str.strip().unique().tolist() if v]
        digits = [v for v in uniq if v.isdigit() and len(v) >= 7][:5]
        if digits:
            rep.err("account_raw", f"account_key ยังเป็นเลขบัญชีจริง เช่น {', '.join(digits)} — ต้องแปลงเป็นรหัส",
                    f"account_key still looks like a real account number, e.g. {', '.join(digits)}",
                    {"samples": digits})

    # ---------------- สแกนค่าทุกคอลัมน์หา PII ที่หลงมา ----------------
    for c in head.columns:
        joined = "\n".join(head[c].astype(str).head(SAMPLE_ROWS).tolist())
        if _ID13.search(joined):
            rep.err("pii_value_id", f"คอลัมน์ {c} มีเลข 13 หลัก — น่าจะเป็นเลขบัตรประชาชน",
                    f"Column {c} contains a 13-digit number that looks like a citizen ID",
                    {"column": c})
        if _EMAIL.search(joined):
            rep.err("pii_value_email", f"คอลัมน์ {c} มีอีเมล", f"Column {c} contains an email address",
                    {"column": c})
        if _PHONE.search(joined) and c not in ("product_code",):
            rep.warn("pii_value_phone", f"คอลัมน์ {c} มีเลขที่ดูเหมือนเบอร์โทร — ช่วยตรวจอีกครั้ง",
                     f"Column {c} has values that look like phone numbers — please double-check",
                     {"column": c})

    # ---------------- วันที่ ----------------
    dcol = "record_date"
    s = col(dcol)
    if s is not None:
        vals = s.astype(str).str.strip()
        bad = [v for v in vals.head(SAMPLE_ROWS).unique().tolist() if v and not _DATE10.match(v)][:5]
        if bad:
            rep.err("date_format", f"{dcol} ต้องเป็น YYYY-MM-DD เจอ {', '.join(bad)}",
                    f"{dcol} must be YYYY-MM-DD, found {', '.join(bad)}", {"samples": bad})
        ok = [v[:10] for v in vals.tolist() if _DATE10.match(v)]
        if ok:
            rep["stats"]["date_min"], rep["stats"]["date_max"] = min(ok), max(ok)

    # ---------------- product_code (R1.1 / R1.6) ----------------
    pc = col("product_code")
    if pc is not None:
        vals = pc.astype(str).str.strip()
        blank = int(((vals == "") | (vals.str.lower() == "null")).sum())
        rep["stats"]["blank_product_code"] = blank
        if blank:
            rep.warn("blank_product_code",
                     f"product_code ว่าง {blank} แถว — ระบบข้ามให้ตาม R1.6 (ยอดเงินคงเหลือ ไม่ใช่การถือครอง)",
                     f"{blank} rows have no product_code — skipped under R1.6 (cash balance, not a holding)",
                     {"rows": blank})
        if blank == len(vals):
            rep.err("all_blank_product_code", "ทุกแถวไม่มี product_code — เชื่อมกับข่าวไม่ได้เลย (R1.1)",
                    "Every row is missing product_code — nothing can be linked to news (R1.1)")

    # ---------------- enum ----------------
    tk = col("product_txt_key")
    if tk is not None:
        unknown = sorted({v.strip() for v in tk.astype(str).tolist()
                          if v.strip() and v.strip() not in ASSET_CLASS_BY_TXT_KEY})
        if unknown:
            rep.warn("unknown_asset_enum",
                     f"product_txt_key ที่ระบบไม่รู้จัก {len(unknown)} ค่า — จัดเข้า OTHER และออกรายงาน (R1.5)",
                     f"{len(unknown)} unknown product_txt_key values — filed under OTHER and reported (R1.5)",
                     {"samples": unknown[:12]})

    tt = col("txn_type")
    if tt is not None:
        unknown = sorted({v.strip() for v in tt.astype(str).tolist()
                          if v.strip() and v.strip() not in TXN_DIRECTION})
        if unknown:
            rep.warn("unknown_txn_type",
                     f"txn_type ที่ระบบไม่รู้จัก {len(unknown)} ค่า — จะไม่ถูกนับเป็นการเทรด (R1.5)",
                     f"{len(unknown)} unknown txn_type values — they will not count as trades (R1.5)",
                     {"samples": unknown[:12]})

    # ---------------- ตัวเลข ----------------
    for name in ("aum", "trading_value", "confirm_unit", "thb_unrealized_avg"):
        s = col(name)
        if s is None:
            continue
        vals = s.astype(str).str.strip().str.replace(",", "", regex=False)
        bad = [v for v in vals.head(SAMPLE_ROWS).unique().tolist()
               if v and v.lower() not in ("null", "none", "nan", "-") and not _isnum(v)][:5]
        if bad:
            rep.warn("non_numeric", f"{name} มีค่าที่ไม่ใช่ตัวเลข เช่น {', '.join(bad)} — จะถูกอ่านเป็นค่าว่าง",
                     f"{name} has non-numeric values, e.g. {', '.join(bad)} — read as empty",
                     {"column": name, "samples": bad})

    rep["ok"] = not rep["errors"]
    return rep, df


def _isnum(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def cross_check(port: Report, txn: Report, port_df: pd.DataFrame | None,
                txn_df: pd.DataFrame | None) -> dict:
    """ตรวจความสอดคล้องระหว่างสองไฟล์ — R1.3 (รหัสเดียวกัน) และ R1.4 (ช่วงวันที่)"""
    out: dict = {"errors": [], "warnings": [], "stats": {}}

    def add(bucket: str, code: str, th: str, en: str, detail=None):
        out[bucket].append({"code": code, "th": th, "en": en, "detail": detail})

    if not (port["ok"] and txn["ok"]) or port_df is None or txn_df is None:
        out["ok"] = False
        return out

    a = set(port_df["customer_key"].astype(str).str.strip()) - {"", "null"}
    b = set(txn_df["customer_key"].astype(str).str.strip()) - {"", "null"}
    both = a & b
    out["stats"] = {"customers_portfolio": len(a), "customers_txn": len(b),
                    "customers_both": len(both),
                    "only_portfolio": len(a - b), "only_txn": len(b - a)}

    if not both:
        add("errors", "key_mismatch",
            "customer_key ของสองไฟล์ไม่ตรงกันเลย — ต้อง mask ด้วยตารางแปลงชุดเดียวกัน (R1.3)",
            "The two files share no customer_key — mask both with the same map (R1.3)")
    elif len(both) < 0.5 * min(len(a), len(b)):
        add("warnings", "key_overlap_low",
            f"ลูกค้าที่อยู่ทั้งสองไฟล์มีแค่ {len(both)} จาก {min(len(a), len(b))} — เช็กว่าใช้ตารางแปลงชุดเดียวกันไหม",
            f"Only {len(both)} of {min(len(a), len(b))} customers appear in both files — same map?")

    # R1.4 — ช่วงวันที่ของสองไฟล์ควรใกล้กัน
    hs, ts = port["stats"].get("date_max"), txn["stats"].get("date_max")
    if hs and ts:
        gap = abs((dt.date.fromisoformat(ts) - dt.date.fromisoformat(hs)).days)
        out["stats"]["date_gap_days"] = gap
        if gap > 31:
            add("warnings", "date_gap",
                f"วันข้อมูลของสองไฟล์ห่างกัน {gap} วัน (holdings {hs} · txn {ts}) — ควรส่งพร้อมกัน (R1.4)",
                f"The two files are {gap} days apart (holdings {hs} · txn {ts}) — send them together (R1.4)")

    out["ok"] = not out["errors"]
    return out


def check_pair(port_path: Path, txn_path: Path, port_name: str, txn_name: str) -> dict:
    port, port_df = check_excel(port_path, "portfolio", port_name, port_path.stat().st_size)
    txn, txn_df = check_excel(txn_path, "txn", txn_name, txn_path.stat().st_size)
    cross = cross_check(port, txn, port_df, txn_df)
    return {"ok": bool(port["ok"] and txn["ok"] and cross["ok"]),
            "portfolio": port, "txn": txn, "cross": cross}


PORT_NAME = "portfolio_masked.xlsx"
TXN_NAME = "txn_masked.xlsx"


def install(port_path: Path, txn_path: Path, now: str | None = None) -> dict:
    """สำเนาไฟล์ชุดเดิมเข้า archive แล้ววางไฟล์ใหม่เป็นชื่อมาตรฐานที่ ingest หาเจอ

    เรียกหลังนำเข้าสำเร็จแล้วเท่านั้น และห้ามโยน exception —
    ถ้าไฟล์เดิมถูก Excel เปิดค้างอยู่ Windows จะลบ/เขียนทับไม่ได้ (WinError 32)
    กรณีนั้นรายงานกลับไปให้ผู้ใช้ปิดไฟล์แล้วอัปโหลดซ้ำ ไม่ใช่พังทั้งคำขอ
    """
    now = now or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = ARCHIVE / now
    archived, problems, stale = [], [], []

    olds = sorted(DATA_DIR.glob("*.xlsx"))
    if olds:
        dest.mkdir(parents=True, exist_ok=True)
    for old in olds:
        try:
            shutil.copy2(old, dest / old.name)          # อ่านอย่างเดียว ปลอดภัยเสมอ
            archived.append(old.name)
        except OSError as e:
            problems.append({"file": old.name, "step": "archive", "error": str(e)})

    for src, name in ((port_path, PORT_NAME), (txn_path, TXN_NAME)):
        try:
            shutil.copyfile(src, DATA_DIR / name)
        except OSError as e:
            problems.append({"file": name, "step": "replace", "error": str(e)})

    # ไฟล์ชื่ออื่นที่ค้างอยู่ต้องออกจาก data/ ไม่งั้นรอบหน้า _find อาจหยิบไฟล์เก่า
    for old in olds:
        if old.name in (PORT_NAME, TXN_NAME):
            continue
        try:
            old.unlink()
            stale.append(old.name)
        except OSError as e:
            problems.append({"file": old.name, "step": "remove_stale", "error": str(e)})

    return {"archived": archived, "removed_stale": stale,
            "archive_dir": str(dest) if archived else None,
            "portfolio": PORT_NAME, "txn": TXN_NAME, "problems": problems}
