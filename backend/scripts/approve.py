# -*- coding: utf-8 -*-
"""ตัวอนุมัติ — คนอ่านข้อเสนอแล้วกดรับทีละแถว

    python -m scripts.approve list                      # ดูของที่รับไปแล้ว
    python -m scripts.approve dr dr-20260803-142500.json
    python -m scripts.approve dr <ไฟล์> --min-confidence high --yes
    python -m scripts.approve revoke dr BRKB            # ถอนของที่รับไปแล้ว

นี่คือประตูเดียวที่เขียน overrides.json ได้ ตัวเสนอเขียนได้แค่ proposals/
ทุกแถวที่รับจะบันทึกว่าใครรับ เมื่อไหร่ และมาจากโมเดลตัวไหน

รับแล้วต้องทำอะไรต่อ
--------------------
    python -m scripts.build_refdata     # สร้างตารางอ้างอิงใหม่ (ด่าน Universe ทำงานตรงนี้)
    python -m scripts.pipeline match    # จับคู่ใหม่ทุกบทความ
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import overrides                                   # noqa: E402

PROPOSALS = ROOT / "proposals"

# ข้อเสนอแต่ละชนิดลงช่องไหนของ overrides.json และค่าไหนคือ "ค่าจริง" ที่ระบบใช้
SECTIONS = {
    "dr": ("dr_alias", "parent"),
    "subcategory": ("subcategory", "content_type"),
    "sector": ("sector_keyword", "sector"),
    "offshore": ("offshore_sector", "sector"),
}
RANK = {"high": 0, "medium": 1, "low": 2}


def _who() -> str:
    return os.environ.get("MATCHPORT_APPROVER") or os.environ.get("USERNAME") \
        or os.environ.get("USER") or "unknown"


def _load(kind: str, name: str) -> dict:
    path = Path(name)
    if not path.exists():
        path = PROPOSALS / name
    if not path.exists():
        avail = sorted(p.name for p in PROPOSALS.glob(f"{kind}-*.json")) \
            if PROPOSALS.exists() else []
        sys.exit(f"ไม่พบไฟล์ {name}" +
                 (f"\nที่มีอยู่: {', '.join(avail)}" if avail else ""))
    return json.loads(path.read_text(encoding="utf-8"))


def _describe(kind: str, key: str, v: dict) -> str:
    if kind == "dr":
        return (f"{key:<12} -> {v['parent']:<16} {v.get('company', '')}\n"
                f"             ลูกค้า {v.get('customers', 0)} คน "
                f"{v.get('value_mb', 0):.2f} ลบ. · ความมั่นใจ {v.get('confidence')}\n"
                f"             เหตุผล: {v.get('reasoning', '')}")
    if kind == "subcategory":
        return (f"{key:<28} -> {v['content_type']}  "
                f"importance={v['importance']} urgency={v['urgency']} "
                f"({v.get('confidence')})\n             เหตุผล: {v.get('reasoning', '')}")
    if kind == "offshore":
        return (f"{key:<16} -> {v['sector']:<24} ({v.get('industry') or '-'})\n"
                f"             ลูกค้า {v.get('customers', 0)} คน {v.get('value_mb', 0):.2f} ลบ. "
                f"จาก Yahoo {v.get('yahoo_symbol', '')}")
    return (f"{key:<24} -> {v['sector']}  ({v.get('confidence')}, "
            f"ติด {v.get('corpus_share', 0):.1%} ของคลัง)\n"
            f"             จากหัวข้อ: {v.get('from_title', '')[:70]}")


# ==========================================================================

def cmd_approve(args) -> None:
    kind = args.kind
    section, _ = SECTIONS[kind]
    data = _load(kind, args.file)
    accepted = data.get("accepted") or {}
    rejected = data.get("rejected") or []

    if data.get("note"):
        print(f"หมายเหตุจากตัวเสนอ: {data['note']}\n")
    if rejected and not args.hide_rejected:
        print(f"ตกด่านตรวจไปแล้ว {len(rejected)} รายการ (ไม่ให้กดรับ):")
        for r in rejected[:12]:
            label = r.get("code") or r.get("subcategory") or r.get("keyword") or "?"
            print(f"  ✕ {label:<16} {r.get('why', '')}")
        if len(rejected) > 12:
            print(f"  … อีก {len(rejected) - 12} รายการ")
        print()

    items = sorted(accepted.items(), key=lambda kv: RANK.get(kv[1].get("confidence"), 9))
    if args.min_confidence:
        keep = RANK[args.min_confidence]
        skipped = [k for k, v in items if RANK.get(v.get("confidence"), 9) > keep]
        items = [(k, v) for k, v in items if RANK.get(v.get("confidence"), 9) <= keep]
        if skipped:
            print(f"ข้าม {len(skipped)} รายการที่ความมั่นใจต่ำกว่า {args.min_confidence}: "
                  f"{', '.join(skipped[:8])}\n")
    if not items:
        print("ไม่มีรายการให้พิจารณา")
        return

    store = overrides.load()
    store.setdefault(section, {})
    taken, passed = [], []
    stamp = dt.datetime.now().isoformat(timespec="seconds")

    for key, v in items:
        print("\n" + _describe(kind, key, v))
        if key in store[section]:
            print(f"             ! มีอยู่แล้ว (รับเมื่อ {store[section][key].get('at')}) — ข้าม")
            continue
        if args.yes:
            ok = True
        else:
            try:
                ok = input("             รับไหม? [y/N] ").strip().lower() in ("y", "yes")
            except EOFError:
                sys.exit("\nรันแบบไม่มี stdin — ใช้ --yes ถ้าตั้งใจรับทั้งหมด")
        if not ok:
            passed.append(key)
            continue
        store[section][key] = {**{k: val for k, val in v.items()
                                  if k not in ("confidence", "reasoning")},
                               "by": _who(), "at": stamp,
                               "source": f"llm:{data.get('model', '?')}",
                               "llm_confidence": v.get("confidence"),
                               "llm_reasoning": v.get("reasoning") or v.get("from_title")}
        taken.append(key)

    if not taken:
        print("\nไม่ได้รับอะไรเลย — overrides.json ไม่ถูกแตะ")
        return

    overrides.save(store)
    print(f"\nรับแล้ว {len(taken)} รายการ ({', '.join(taken)})")
    if passed:
        print(f"ไม่รับ {len(passed)} รายการ ({', '.join(passed)})")
    print(f"เขียนลง {overrides.PATH}")
    print("\nขั้นต่อไป — ของที่รับยังไม่มีผลจนกว่าจะสร้างตารางใหม่:")
    print("  python -m scripts.build_refdata")
    print("  python -m scripts.pipeline match")


def cmd_list(args) -> None:
    store = overrides.load()
    total = 0
    for section, entries in store.items():
        if not entries:
            continue
        print(f"\n[{section}] {len(entries)} รายการ")
        for key, v in sorted(entries.items()):
            val = v.get("parent") or v.get("content_type") or v.get("sector") or "?"
            print(f"  {key:<20} -> {str(val):<18} "
                  f"{v.get('by', '?')} {v.get('at', '')[:10]} "
                  f"({v.get('source', 'manual')}, {v.get('llm_confidence', '-')})")
            total += 1
    if not total:
        print("ยังไม่มีของที่คนอนุมัติเลย — overrides.json ว่าง")
        print(f"(ไฟล์: {overrides.PATH})")


def cmd_revoke(args) -> None:
    section, _ = SECTIONS[args.kind]
    store = overrides.load()
    if args.key not in store.get(section, {}):
        sys.exit(f"ไม่พบ '{args.key}' ใน {section}")
    old = store[section].pop(args.key)
    overrides.save(store)
    print(f"ถอน {args.key} ({old.get('parent') or old.get('content_type') or old.get('sector')}) แล้ว")
    print("อย่าลืมสร้างตารางใหม่:  python -m scripts.build_refdata")


# ==========================================================================

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="ดูของที่รับไปแล้ว").set_defaults(fn=cmd_list)

    for kind in SECTIONS:
        a = sub.add_parser(kind, help=f"พิจารณาข้อเสนอชนิด {kind}")
        a.add_argument("file", help="ชื่อไฟล์ใน proposals/ หรือ path เต็ม")
        a.add_argument("--yes", action="store_true", help="รับทุกรายการโดยไม่ถาม")
        a.add_argument("--min-confidence", choices=["high", "medium", "low"],
                       help="พิจารณาเฉพาะที่ความมั่นใจถึงระดับนี้")
        a.add_argument("--hide-rejected", action="store_true")
        a.set_defaults(fn=cmd_approve, kind=kind)

    r = sub.add_parser("revoke", help="ถอนของที่รับไปแล้ว")
    r.add_argument("kind", choices=list(SECTIONS))
    r.add_argument("key")
    r.set_defaults(fn=cmd_revoke)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
