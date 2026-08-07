# -*- coding: utf-8 -*-
"""ตัวเสนอ — ใช้ LLM ช่วยเติมช่องว่างที่ spec ไม่ครอบคลุม

    python -m scripts.propose dr           # DR ที่ยังถอดหุ้นแม่ไม่ได้ (R4.27)
    python -m scripts.propose subcategory  # หมวดข่าวใหม่ที่ระบบไม่รู้จัก (R3.16)
    python -m scripts.propose sector       # คำค้น sector ที่ยังไม่ครอบคลุม (GAP-17)
    python -m scripts.propose offshore     # sector หุ้นนอกจาก Yahoo Finance (B3) — ไม่ใช้ LLM

    เพิ่ม --dry-run เพื่อดูว่าจะถามอะไร โดยไม่เรียก API

อยู่ตรงไหนของระบบ
-----------------
    unmapped ──> [ตัวเสนอ: LLM] ──> proposals/*.json ──> [คนกดรับ] ──> overrides.json
                                                                            │
                                            runtime ยังเป็นกฎล้วน <─────────┘

**สคริปต์นี้ไม่ได้อยู่ใน runtime** รันมือเมื่อ unmapped โตขึ้น ไม่มีอะไรใน pipeline
เรียกมัน และไม่มีอะไรในหน้าเว็บกดมันได้ ผลลัพธ์เป็นแค่ "ข้อเสนอ" ที่รอคนอ่าน

ทำไมถึงปลอดภัยพอ
----------------
1. LLM ไม่ได้ตัดสิน — มันเสนอ ส่วนที่ตัดสินว่ารับหรือไม่คือคน (scripts/approve.py)
2. คำตอบถูกตรวจด้วยโค้ดก่อนถึงมือคน — รหัสที่เสนอต้องมีอยู่จริงในพอร์ตลูกค้า
   (R3.24) ไม่งั้นทิ้งทันที LLM จะเดามั่วยังไงก็หลุดด่านนี้ไม่ได้
3. ต่อให้คนเผลอรับของผิด build_refdata.py ยังมีด่าน Universe ซ้ำอีกชั้น
4. เสนอได้เฉพาะสิ่งที่ตรวจสอบได้ — เรื่องที่ต้องใช้ข้อมูลภายใน (fund master,
   ความหมายของ txn_type ที่เป็น null) ไม่อยู่ในขอบเขตของสคริปต์นี้
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import db, overrides                               # noqa: E402
from app.mapping import refdata                             # noqa: E402
from app.news import universe_from_db                       # noqa: E402
from app.tables import (                                    # noqa: E402
    CONTENT_TYPE_BY_SUBCATEGORY,
    IMPORTANCE_BY_CONTENT_TYPE,
    SECTOR_BY_THAI_KEYWORD,
    URGENCY_BY_CONTENT_TYPE,
)

OUT_DIR = ROOT / "proposals"
MODEL = "claude-opus-5"


# ==========================================================================
# ตัวเรียก LLM — ที่เดียวในโปรเจกต์ที่คุยกับโมเดล
# ==========================================================================

def ask(system: str, user: str, schema: dict, *, dry_run: bool = False,
        max_tokens: int = 16000) -> dict:
    """ถามครั้งเดียว บังคับให้ตอบเป็น JSON ตาม schema

    ใช้ output_config.format แทนการขอ JSON ในคำสั่ง — โมเดลจึงตอบผิดรูปไม่ได้
    ไม่ต้องมี pydantic เพิ่มใน requirements
    """
    if dry_run:
        print("=" * 70)
        print("[system]\n" + system)
        print("-" * 70)
        print("[user]\n" + (user[:4000] + " …ตัดแสดง…" if len(user) > 4000 else user))
        print("=" * 70)
        return {}

    try:
        import anthropic
    except ImportError:
        sys.exit("ต้องติดตั้งก่อน:  pip install anthropic")

    client = anthropic.Anthropic()      # อ่าน ANTHROPIC_API_KEY หรือโปรไฟล์ ant auth
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.AuthenticationError:
        sys.exit("ไม่มีสิทธิ์เรียก API — ตั้ง ANTHROPIC_API_KEY หรือรัน `ant auth login` ก่อน")

    # ต้องเช็ค stop_reason ก่อนอ่าน content เสมอ — ถ้าโดนปฏิเสธ content จะว่าง
    if resp.stop_reason == "refusal":
        sys.exit(f"โมเดลปฏิเสธคำขอ (category={getattr(resp.stop_details, 'category', None)})")

    text = next((b.text for b in resp.content if b.type == "text"), "")
    if not text:
        sys.exit(f"ไม่ได้ข้อความกลับมา (stop_reason={resp.stop_reason})")

    usage = resp.usage
    print(f"  โมเดล {resp.model} · เข้า {usage.input_tokens:,} / ออก {usage.output_tokens:,} token")
    return json.loads(text)


def write(kind: str, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = OUT_DIR / f"{kind}-{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


# ==========================================================================
# 1. DR ที่ยังถอดหุ้นแม่ไม่ได้ (R4.27)
# ==========================================================================

DR_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "รหัส DR ที่ถาม"},
                    "kind": {
                        "type": "string",
                        "enum": ["single_stock", "index_or_etf", "commodity", "unknown"],
                        "description": "DR ตัวนี้อ้างอิงอะไร",
                    },
                    "ticker": {
                        "type": "string",
                        "description": "ตัวย่อหุ้นแม่ในตลาดที่ list เช่น 'MU', '0700', '6861'. "
                                       "เว้นเป็นค่าว่างถ้า kind ไม่ใช่ single_stock",
                    },
                    "exchange": {
                        "type": "string",
                        "description": "ตลาดที่หุ้นแม่ list อยู่ เช่น NASDAQ, NYSE, HKEX, TSE, "
                                       "KRX, TWSE, HOSE, SGX, XETRA. ว่างได้ถ้าไม่ใช่หุ้น",
                    },
                    "company": {"type": "string", "description": "ชื่อเต็มของสิ่งที่อ้างอิง"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reasoning": {"type": "string", "description": "สั้น ๆ ว่าอ่านรหัสยังไง"},
                },
                "required": ["code", "kind", "ticker", "exchange", "company",
                             "confidence", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

DR_SYSTEM = """คุณกำลังช่วยทีมข้อมูลของบริษัทหลักทรัพย์ไทยถอดความหมายของรหัส DR
(Depositary Receipt) ที่ซื้อขายในตลาดหลักทรัพย์แห่งประเทศไทย

รูปแบบรหัส: <ชื่อย่อผู้ออก/สินทรัพย์อ้างอิง><เลขผู้ออก 2 หลัก>
ตัวอย่างที่ยืนยันแล้ว: TENCENT80 -> Tencent (00700 HKEX) · MICRON80 -> Micron (MU NASDAQ)

หน้าที่ของคุณคือบอกว่าแต่ละรหัส "อ้างอิงอะไร" เท่านั้น

กฎที่ต้องทำตามอย่างเคร่งครัด:
1. ถ้าอ้างอิงหุ้นรายตัว ให้ kind = single_stock แล้วระบุ ticker ตามที่ใช้จริงใน
   ตลาดที่หุ้นตัวนั้น list อยู่ (ฮ่องกงใช้ตัวเลข เช่น 0700 ไม่ใช่ TENCENT)
2. ถ้าอ้างอิงดัชนี ETF กองทุน หรือตะกร้าหุ้น ให้ kind = index_or_etf และเว้น
   ticker กับ exchange เป็นค่าว่าง — อย่าพยายามเลือกหุ้นตัวใดตัวหนึ่งมาแทน
   (เช่นรหัสที่ขึ้นต้นด้วยชื่อประเทศหรือชื่อดัชนี มักเป็น ETF ไม่ใช่หุ้นรายตัว)
3. ถ้าอ้างอิงทองคำ น้ำมัน หรือสินค้าโภคภัณฑ์ ให้ kind = commodity และเว้น ticker
4. ถ้าไม่แน่ใจว่าเป็นตัวไหน ให้ kind = unknown และเว้น ticker — ห้ามเดา
   การตอบ unknown ไม่ใช่ความล้มเหลว การเดาผิดต่างหากที่เป็นปัญหา เพราะจะทำให้
   ลูกค้าได้รับข่าวของบริษัทที่ตัวเองไม่ได้ถือ
5. confidence = high เฉพาะเมื่อคุณมั่นใจจริงว่ารหัสนี้คือบริษัทนั้น"""


def propose_dr(args) -> None:
    con = db.connect()
    try:
        uni = universe_from_db(con)
        impact = {r["product_code"]: (r["customers"], r["value_mb"]) for r in con.execute("""
            SELECT product_code, COUNT(DISTINCT customer_key) customers,
                   ROUND(SUM(COALESCE(holding_value,0))/1e6, 2) value_mb
            FROM holdings GROUP BY 1""")}
    finally:
        con.close()

    rd = refdata()
    pending = list(rd["dr_pending"])
    if not pending:
        print("ไม่มี DR ค้างอยู่ — ไม่มีอะไรให้เสนอ")
        return

    # เรียงตามผลกระทบจริง ไม่ใช่ตามลำดับในไฟล์ — ตัวที่มีคนถือเยอะควรได้รับความสนใจก่อน
    for p in pending:
        p["customers"], p["value_mb"] = impact.get(p["code"], (0, 0.0))
    pending.sort(key=lambda p: (-p["value_mb"], -p["customers"]))
    if args.limit:
        pending = pending[:args.limit]

    # ตัวอย่างจริงจาก spec — ให้โมเดลเห็นว่ารูปแบบคำตอบที่ถูกต้องหน้าตาเป็นยังไง
    solved = [(c, i["parent"]) for c, i in list(rd["dr_parent"].items())[:25]]

    user = (
        "รหัส DR ที่ถอดหุ้นแม่ไม่ได้ (เรียงตามมูลค่าที่ลูกค้าถือ):\n"
        # dr_pending มีสองแบบ: ไม่มีในตารางชื่อพ้องเลย กับเคยชี้ไปรหัสที่ไม่มีใครถือ
        # แบบหลังต้องบอกโมเดลด้วยว่าเคยเดาว่าอะไรแล้วพลาด จะได้ไม่เสนอซ้ำรอยเดิม
        + "\n".join(f"  {p['code']:<14} ชื่อที่ถอดได้: {(p.get('name') or '-'):<12} "
                    f"ลูกค้า {p['customers']} คน {p['value_mb']:.2f} ลบ."
                    + (f"  [เคยเดาว่า {p['parent']} แต่ไม่มีลูกค้าถือรหัสนั้น]"
                       if p.get("parent") else "")
                    for p in pending)
        + "\n\nตัวอย่างรหัสที่ถอดสำเร็จแล้ว (รหัส DR -> หุ้นแม่):\n"
        + "\n".join(f"  {c} -> {parent}" for c, parent in solved)
        + f"\n\nตอบให้ครบทั้ง {len(pending)} รหัส"
    )
    print(f"ถาม {len(pending)} รหัส DR …")
    got = ask(DR_SYSTEM, user, DR_SCHEMA, dry_run=args.dry_run)
    if not got:
        return

    # ---- ด่านตรวจ: คำตอบต้องชี้ไปรหัสที่มีคนถือจริง ----
    # ตรงนี้คือจุดที่ทำให้ทั้งกระบวนการปลอดภัย ไม่ใช่ความเก่งของโมเดล
    accepted, rejected = {}, []
    for it in got.get("items", []):
        code = (it.get("code") or "").strip().upper()
        base = {k: it.get(k) for k in ("kind", "company", "confidence", "reasoning")}
        if it.get("kind") != "single_stock" or not it.get("ticker"):
            rejected.append({**base, "code": code,
                             "why": f"ไม่ใช่หุ้นรายตัว (kind={it.get('kind')}) — "
                                    f"ระบบยังไม่มีกฎรองรับ DR แบบนี้"})
            continue
        ent, why = _resolve(uni, it["ticker"], it.get("exchange", ""))
        if not ent:
            rejected.append({**base, "code": code, "ticker": it["ticker"],
                             "exchange": it.get("exchange"),
                             "why": why or "ไม่พบรหัสนี้ในพอร์ตลูกค้า (R3.24)"})
            continue
        cust, val = impact.get(code, (0, 0.0))
        accepted[_alias_key(code)] = {
            **base, "parent": ent, "dr_code": code, "ticker": it["ticker"],
            "exchange": it.get("exchange"), "customers": cust, "value_mb": val,
        }

    payload = {"kind": "dr_alias", "model": MODEL,
               "at": dt.datetime.now().isoformat(timespec="seconds"),
               "asked": len(pending), "accepted": accepted, "rejected": rejected}
    path = write("dr", payload)
    print(f"\nผ่านด่านตรวจ {len(accepted)} · ตกด่าน {len(rejected)}")
    print(f"เขียนไว้ที่ {path}")
    print("อ่านแล้วกดรับด้วย:  python -m scripts.approve dr " + path.name)


# ตลาดที่ชื่อมนุษย์ชี้ไป — ใช้จำกัดขอบเขตตอนคลี่ ไม่ให้ข้ามตลาดมั่ว
EXCHANGE_MICS = {
    "NASDAQ": ("xnas",), "NYSE": ("xnys",), "AMEX": ("xase",), "ARCA": ("arcx",),
    "BATS": ("bats",), "US": ("xnas", "xnys", "arcx", "bats", "xase"),
    "HKEX": ("xhkg",), "HKSE": ("xhkg",), "SEHK": ("xhkg",),
    "TSE": ("xtks",), "TYO": ("xtks",), "JPX": ("xtks",),
    "KRX": ("xkrx", "kosdaq"), "KOSPI": ("xkrx",), "KOSDAQ": ("kosdaq",),
    "TWSE": ("xtai",), "TPEX": ("xtai",),
    "SGX": ("sgx",), "HOSE": ("xstc",), "HNX": ("xstc",), "UPCOM": ("upcom",),
    "SSE": ("xshg",), "SZSE": ("xshe",), "LSE": ("xlon",),
    "XETRA": ("xetr",), "FWB": ("xetr",), "EURONEXT": ("xpar", "xams"),
    "PARIS": ("xpar",), "AMSTERDAM": ("xams",), "SIX": ("xswx",),
    "BME": ("xmce",), "BORSA": ("xmil",), "ASX": ("xasx",),
    "NSE": ("xnse",), "BSE": ("xbom",), "TSX": ("xtsx",), "IDX": ("xidx",),
}


def _resolve(uni, ticker: str, exchange: str) -> tuple[str | None, str]:
    """แปลง (ticker, ชื่อตลาด) ที่โมเดลตอบ -> รหัสกลางที่มีคนถือจริง

    ไม่เชื่อคำตอบของโมเดลเลย — ทุกเส้นทางจบที่การตรวจกับ Universe
    """
    tic = (ticker or "").strip().upper()
    if not tic:
        return None, "ไม่ได้ระบุ ticker"
    mics = EXCHANGE_MICS.get((exchange or "").strip().upper(), ())

    # 1. ตรงตัวอยู่แล้ว (โมเดลตอบเป็น TICKER:mic มาเลย)
    if ":" in tic and tic.lower() in {e.lower() for e in uni.ids}:
        return next(e for e in uni.ids if e.lower() == tic.lower()), ""

    # 2. คลี่ตามตลาดที่ระบุ
    #    ฮ่องกงเติมศูนย์ 5 หลัก (R4.6) · ตัวคั่นในตัวย่อไม่ตรงกันระหว่างผู้ให้ข้อมูล
    #    (โมเดลตอบ BRK.B ส่วนพอร์ตเก็บ BRKb) จึงต้องลองแบบตัดตัวคั่นด้วย
    cands = [tic]
    if tic.isdigit():
        cands.append(tic.zfill(5))
    flat = tic.replace(".", "").replace("-", "").replace(" ", "")
    if flat != tic:
        cands.append(flat)

    why = ""
    for cand in cands:
        ent, why = uni.resolve_root(cand, mics)
        if ent:
            return ent, ""
        if mics:
            ent, _ = uni.resolve_root(cand)    # ไม่จำกัดตลาด ถ้าชี้ได้ตัวเดียวก็รับ
            if ent:
                return ent, ""
    return None, why or f"ไม่พบ {tic} ในรายการสินทรัพย์ของลูกค้า"


def _alias_key(dr_code: str) -> str:
    """ตารางชื่อพ้องคีย์ด้วย "ชื่อ" ไม่ใช่รหัสเต็ม — ตัดเลขผู้ออกท้ายออก (R4.25)"""
    from app.tables import DR_ISSUER_SUFFIXES
    for suf in sorted(DR_ISSUER_SUFFIXES, key=len, reverse=True):
        if dr_code.endswith(suf) and len(dr_code) > len(suf):
            return dr_code[: -len(suf)]
    return dr_code


# ==========================================================================
# 2. หมวดข่าวใหม่ที่ระบบไม่รู้จัก (R3.16)
# ==========================================================================

SUB_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subcategory": {"type": "string"},
                    "content_type": {"type": "string",
                                     "description": "ต้องเป็นค่าที่มีอยู่แล้วเท่านั้น"},
                    "importance": {"type": "integer", "description": "1 ถึง 5"},
                    "urgency": {"type": "string", "enum": ["now", "this_week", "low"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["subcategory", "content_type", "importance", "urgency",
                             "confidence", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

SUB_SYSTEM = """คุณกำลังช่วยจัดชั้นหมวดเนื้อหาใหม่ของเว็บบทวิเคราะห์การลงทุน
ระบบจับคู่ข่าวกับลูกค้าใช้ content_type ตัดสินว่าข่าวชิ้นนั้นควรส่งถึงลูกค้ากลุ่มไหน
และควรด่วนแค่ไหน หมวดที่ยังไม่ถูกจัดชั้นจะถูกข้ามทั้งหมวด ไม่มีใครได้รับเลย

กฎ:
1. content_type ต้องเลือกจากรายการที่มีอยู่แล้วเท่านั้น ห้ามคิดค่าใหม่
2. เทียบเคียงกับหมวดเดิมที่ใกล้เคียงที่สุด แล้วบอกในเหตุผลว่าเทียบกับหมวดไหน
3. importance: 5 = ผลประกอบการหรือ corporate action, 4 = ข่าวบริษัทและบทวิเคราะห์
   รายตัว, 3 = บทวิเคราะห์กลุ่ม/กองทุน/สรุปประจำวัน, 2 = มหภาคและรายงานพิเศษ,
   1 = แนวโน้มระยะยาว เรื่องเล่า ภาษี
4. urgency: now = ต้องรู้วันนี้, this_week = สัปดาห์นี้, low = ไม่เร่ง
5. ถ้าดูจากชื่อหมวดแล้วเดาไม่ออกจริง ๆ ให้ confidence = low และเลือกค่าที่
   อนุรักษ์นิยมที่สุด (importance ต่ำ urgency low) ผิดทางต่ำเสียหายน้อยกว่าผิดทางสูง"""


def propose_subcategory(args) -> None:
    con = db.connect()
    try:
        unknown = [dict(r) for r in con.execute(
            "SELECT raw, n, sample_ref FROM unmapped WHERE bucket='subcategory' ORDER BY n DESC")]
    finally:
        con.close()
    if not unknown:
        print("ไม่มีหมวดที่ระบบไม่รู้จัก — ไม่มีอะไรให้เสนอ")
        return

    known = sorted(set(CONTENT_TYPE_BY_SUBCATEGORY.values()))
    examples = {}
    for slug, ct in CONTENT_TYPE_BY_SUBCATEGORY.items():
        examples.setdefault(ct, []).append(slug)

    user = (
        "หมวดใหม่ที่ยังไม่ถูกจัดชั้น:\n"
        + "\n".join(f"  {u['raw']}  (พบ {u['n']} ครั้ง)" for u in unknown)
        + "\n\ncontent_type ที่มีอยู่ (เลือกจากรายการนี้เท่านั้น) พร้อมหมวดตัวอย่าง:\n"
        + "\n".join(f"  {ct:<18} importance={IMPORTANCE_BY_CONTENT_TYPE.get(ct, '?')} "
                    f"urgency={URGENCY_BY_CONTENT_TYPE.get(ct, '?'):<10} "
                    f"เช่น {', '.join(examples[ct][:4])}"
                    for ct in known)
    )
    print(f"ถาม {len(unknown)} หมวด …")
    got = ask(SUB_SYSTEM, user, SUB_SCHEMA, dry_run=args.dry_run)
    if not got:
        return

    accepted, rejected = {}, []
    for it in got.get("items", []):
        slug = (it.get("subcategory") or "").strip()
        if it.get("content_type") not in known:
            rejected.append({**it, "why": f"content_type '{it.get('content_type')}' "
                                          f"ไม่มีอยู่ในระบบ — ห้ามสร้างใหม่เอง"})
            continue
        if not 1 <= int(it.get("importance") or 0) <= 5:
            rejected.append({**it, "why": "importance ต้องอยู่ระหว่าง 1-5"})
            continue
        accepted[slug] = {k: it[k] for k in ("content_type", "importance", "urgency",
                                             "confidence", "reasoning")}

    payload = {"kind": "subcategory", "model": MODEL,
               "at": dt.datetime.now().isoformat(timespec="seconds"),
               "asked": len(unknown), "accepted": accepted, "rejected": rejected,
               "note": "PERSONA_CONTENT_MAP ไม่ถูกแตะ — ถ้า content_type ที่เลือกไม่ได้อยู่ใน "
                       "persona ไหนเลย หมวดนี้จะยังไม่ถึงใคร ต้องตัดสินใจแยกว่ากลุ่มไหนควรได้"}
    path = write("subcategory", payload)
    print(f"\nผ่านด่านตรวจ {len(accepted)} · ตกด่าน {len(rejected)}")
    print(f"เขียนไว้ที่ {path}")
    print("อ่านแล้วกดรับด้วย:  python -m scripts.approve subcategory " + path.name)


# ==========================================================================
# 3. คำค้น sector ที่ยังไม่ครอบคลุม (GAP-17)
# ==========================================================================

SECTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string",
                                "description": "คำไทยที่ยกมาจากหัวข้อตรงตัว ยาวอย่างน้อย 5 ตัวอักษร"},
                    "sector": {"type": "string", "description": "ต้องตรงกับรายการที่ให้ไว้"},
                    "from_title": {"type": "string", "description": "หัวข้อที่ยกคำนี้มา"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["keyword", "sector", "from_title", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

SECTOR_SYSTEM = """คุณกำลังช่วยหาคำค้นภาษาไทยที่ใช้ระบุกลุ่มอุตสาหกรรมจากหัวข้อ
บทวิเคราะห์รายอุตสาหกรรม บทความกลุ่มนี้ไม่ได้เอ่ยชื่อหุ้นตรง ๆ ระบบจึงต้องอ่าน
ชื่อกลุ่มจากหัวข้อแทน หัวข้อที่ไม่มีคำไหนตรงเลยจะจับคู่กับลูกค้าไม่ได้

กฎ:
1. ยกคำมาจากหัวข้อ "ตรงตัว" เท่านั้น ห้ามแปลง ห้ามย่อ ห้ามคิดคำใหม่
2. คำต้องยาวอย่างน้อย 5 ตัวอักษรและเจาะจงพอ คำกว้างอย่าง "ตลาด" "หุ้น"
   "เศรษฐกิจ" "การลงทุน" ใช้ไม่ได้ เพราะจะไปตรงกับบทความเกือบทุกชิ้น
3. sector ต้องตรงกับรายการที่ให้ไว้เป๊ะ ๆ ห้ามสร้างชื่อกลุ่มใหม่
4. หัวข้อไหนไม่มีคำที่ระบุกลุ่มได้ชัด ให้ข้ามไป อย่าฝืนหาคำมาใส่
5. ถ้าคำนั้นมีอยู่ในรายการคำค้นเดิมแล้ว ไม่ต้องเสนอซ้ำ"""


def propose_sector(args) -> None:
    con = db.connect()
    try:
        blind = [dict(r) for r in con.execute("""
            SELECT article_id, title FROM articles
            WHERE content_type='sector_analysis' AND role='content'
              AND (sector IS NULL OR sector IN ('', '[]'))
            ORDER BY trigger_at DESC LIMIT 60""")]
        total_articles = con.execute(
            "SELECT COUNT(*) FROM articles WHERE role='content'").fetchone()[0]
        titles = [r[0] or "" for r in con.execute(
            "SELECT title FROM articles WHERE role='content'")]
    finally:
        con.close()

    if not blind:
        print("บทวิเคราะห์รายอุตสาหกรรมทุกชิ้นระบุกลุ่มได้แล้ว — ไม่มีอะไรให้เสนอ")
        return

    sectors = sorted({v["sector"] for v in refdata()["thai_sector"].values()})
    user = (
        "หัวข้อบทวิเคราะห์รายอุตสาหกรรมที่ระบบยังอ่านกลุ่มไม่ออก:\n"
        + "\n".join(f"  {b['title']}" for b in blind)
        + "\n\nกลุ่มอุตสาหกรรมที่ใช้ได้ (ต้องตรงเป๊ะ):\n"
        + "\n".join(f"  {s}" for s in sectors)
        + "\n\nคำค้นที่มีอยู่แล้ว (ไม่ต้องเสนอซ้ำ):\n  "
        + " · ".join(sorted(SECTOR_BY_THAI_KEYWORD))
    )
    print(f"ถาม {len(blind)} หัวข้อ …")
    got = ask(SECTOR_SYSTEM, user, SECTOR_SCHEMA, dry_run=args.dry_run)
    if not got:
        return

    # ---- ด่านตรวจ R3.38: คำที่ติดเกิน 30% ของคลังถือว่ากว้างเกินจนใช้ไม่ได้ ----
    accepted, rejected = {}, []
    for it in got.get("items", []):
        kw = (it.get("keyword") or "").strip()
        base = {k: it.get(k) for k in ("keyword", "sector", "from_title", "confidence")}
        if it.get("sector") not in sectors:
            rejected.append({**base, "why": f"กลุ่ม '{it.get('sector')}' ไม่มีในรายการ"})
            continue
        if len(kw) < 5:
            rejected.append({**base, "why": "คำสั้นกว่า 5 ตัวอักษร (R3.37)"})
            continue
        if kw in SECTOR_BY_THAI_KEYWORD:
            rejected.append({**base, "why": "มีคำนี้อยู่แล้ว"})
            continue
        hits = sum(1 for t in titles if kw in t)
        share = hits / max(1, total_articles)
        if share > 0.30:
            rejected.append({**base, "why": f"ติด {share:.0%} ของคลังบทความ "
                                            f"กว้างเกินเกณฑ์ 30% (R3.38)"})
            continue
        accepted[kw] = {**base, "corpus_share": round(share, 4), "corpus_hits": hits}

    payload = {"kind": "sector_keyword", "model": MODEL,
               "at": dt.datetime.now().isoformat(timespec="seconds"),
               "asked": len(blind), "accepted": accepted, "rejected": rejected}
    path = write("sector", payload)
    print(f"\nผ่านด่านตรวจ {len(accepted)} · ตกด่าน {len(rejected)}")
    print(f"เขียนไว้ที่ {path}")
    print("อ่านแล้วกดรับด้วย:  python -m scripts.approve sector " + path.name)


# ==========================================================================
# 4. sector ของหุ้นต่างประเทศ (B3) — ดึงจาก Yahoo Finance ตรง ๆ ไม่ใช้ LLM
#
# ต่างจากอีกสามตัวข้างบน: ไม่มีอะไรให้โมเดล "เดา" — Yahoo ตอบ sector มาตรง ๆ
# (GICS-based) ยังผ่าน proposals/ + approve.py เหมือนเดิมเพราะชื่อ sector ของ
# Yahoo เป็นภาษาอังกฤษคนละชุดกับ Coverage List หุ้นไทย ต้องมีคนเห็นก่อนว่าไม่ตี
# กับของเดิม ไม่ใช่เพราะไม่เชื่อ Yahoo
# ==========================================================================

def propose_offshore_sector(args) -> None:
    from app.yahoo import fetch_sector, to_yahoo_symbol

    con = db.connect()
    try:
        uni = universe_from_db(con)
        impact = {r["entity"]: (r["customers"], r["value_mb"]) for r in con.execute("""
            SELECT entity, COUNT(DISTINCT customer_key) customers,
                   ROUND(SUM(COALESCE(holding_value,0))/1e6, 2) value_mb
            FROM holdings WHERE entity IS NOT NULL AND entity LIKE '%:%'
            GROUP BY 1""")}
    finally:
        con.close()

    have = set(overrides.offshore_sector())
    thai = set(refdata()["thai_sector"])
    # เรียงตามมูลค่าที่ลูกค้าถือจริงก่อน เหมือน propose_dr — ตัวที่ไม่มีใครถือรอได้
    todo = sorted((e for e in uni.ids if ":" in e and e not in have and e not in thai),
                  key=lambda e: (-impact.get(e, (0, 0.0))[1], -impact.get(e, (0, 0.0))[0]))
    if not todo:
        print("หุ้นนอกทุกตัวที่ลูกค้าถือมี sector แล้ว — ไม่มีอะไรให้เสนอ")
        return
    if args.limit:
        todo = todo[: args.limit]

    if args.dry_run:
        print(f"จะขอ Yahoo Finance {len(todo)} ตัว (ไม่เรียกจริง):")
        for e in todo[:30]:
            cust, val = impact.get(e, (0, 0.0))
            sym = to_yahoo_symbol(e) or "(ตลาดนี้ Yahoo ไม่รองรับ — จะถูกข้าม)"
            print(f"  {e:<16} -> {sym:<12} ลูกค้า {cust} คน {val:.2f} ลบ.")
        if len(todo) > 30:
            print(f"  … อีก {len(todo) - 30} ตัว")
        return

    accepted, rejected = {}, []
    print(f"ดึง Yahoo Finance {len(todo)} ตัว …")
    for i, e in enumerate(todo, 1):
        cust, val = impact.get(e, (0, 0.0))
        sym = to_yahoo_symbol(e)
        if not sym:
            rejected.append({"entity": e, "why": "ตลาดของรหัสนี้ยังไม่มี mapping ไป Yahoo symbol"})
            continue
        info = fetch_sector(sym)
        if not info:
            rejected.append({"entity": e, "yahoo_symbol": sym,
                             "why": "Yahoo ไม่มีข้อมูล sector ของตัวนี้ (เช่น ETF/กองทุน)"})
            continue
        accepted[e] = {"sector": info["sector"], "industry": info.get("industry"),
                       "yahoo_symbol": sym, "confidence": "high",
                       "customers": cust, "value_mb": val}
        if i % 20 == 0:
            print(f"  … {i}/{len(todo)}")
        time.sleep(0.3)  # กันโดน rate-limit ฝั่ง Yahoo

    payload = {"kind": "offshore_sector", "model": "yahoo-finance:quoteSummary/assetProfile",
               "at": dt.datetime.now().isoformat(timespec="seconds"),
               "asked": len(todo), "accepted": accepted, "rejected": rejected}
    path = write("offshore", payload)
    print(f"\nได้ sector {len(accepted)} ตัว, ไม่ได้ {len(rejected)}")
    print(f"เขียนไว้ที่ {path}")
    print("อ่านแล้วกดรับด้วย:  python -m scripts.approve offshore " + path.name)


# ==========================================================================

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("kind", choices=["dr", "subcategory", "sector", "offshore"])
    p.add_argument("--dry-run", action="store_true", help="แสดงคำถามโดยไม่เรียก API")
    p.add_argument("--limit", type=int, default=0, help="จำกัดจำนวนรายการที่ถาม")
    args = p.parse_args()
    {"dr": propose_dr, "subcategory": propose_subcategory,
     "sector": propose_sector, "offshore": propose_offshore_sector}[args.kind](args)


if __name__ == "__main__":
    main()
