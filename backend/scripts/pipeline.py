# -*- coding: utf-8 -*-
"""CLI สำหรับสั่งงาน pipeline โดยไม่ต้องเปิดเว็บ

    python -m scripts.pipeline ingest              นำเข้าไฟล์ลูกค้า + feature + persona
    python -m scripts.pipeline news --pages 4      ดึงข่าวจาก Cafe Invest API
    python -m scripts.pipeline match [--threshold 50]
    python -m scripts.pipeline ai                  ให้ Claude Code อ่านข่าวที่ยังไม่ได้อ่าน
    python -m scripts.pipeline daily               งานเช้า: ดึงข่าว -> AI อ่านของวันนี้ -> จับคู่
    python -m scripts.pipeline all --pages 4       ทำทั้งหมดตามลำดับ (ใส่ --ai ให้ AI อ่านด้วย)
    python -m scripts.pipeline status              สรุปสถานะ
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, enrich, llm, matching, news, tables  # noqa: E402
from app import ingest_customers as ingest  # noqa: E402


def show(title: str, payload: dict) -> None:
    print(f"\n{title}")
    print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))


def run_ai(con, day: str | None, limit: int, workers: int, redo: bool = False,
           demote: bool = False) -> dict:
    """ให้ AI อ่านจนหมดวันนั้น — ทีละล็อต ขาดตอนแล้วรันซ้ำได้ (ai_at กันอ่านซ้ำ)

    รันเป็นล็อตแทนที่จะยิงทีเดียวหมด เพื่อให้ล้มกลางทางแล้วของที่อ่านไปแล้วยังอยู่
    """
    total = {"done": 0, "entities_added": 0, "dropped": 0, "problems": 0,
             "flagged": 0, "demoted": 0, "directions": {}, "reasons": {}, "rounds": 0}
    # รอบอ่านซ้ำต้องจำเวลาเริ่ม ไม่งั้นล็อตถัดไปจะหยิบชิ้นเดิมที่เพิ่งอ่านไปมาอีก
    since = dt.datetime.now().isoformat(timespec="seconds") if redo else ""
    while True:
        res = enrich.enrich_batch(con, limit=limit, date=day, workers=workers, redo=redo,
                                  demote=demote, since=since)
        if res.get("problem"):
            return {**total, "problem": res["problem"]}
        total["rounds"] += 1
        for k in ("done", "entities_added", "dropped", "problems", "flagged", "demoted"):
            total[k] += res[k]
        for group in ("directions", "reasons"):
            for k, v in res[group].items():
                total[group][k] = total[group].get(k, 0) + v
        print(f"  [ล็อต {total['rounds']}] อ่าน {res['done']}/{res['tried']}"
              f" · entity +{res['entities_added']} · ไม่รับ {res['dropped']}", flush=True)
        # redo อ่านทับของเดิม จำนวนที่ "ยังไม่เคยอ่าน" จึงไม่ใช่เงื่อนไขจบ ใช้ล็อตที่ว่างแทน
        if res["tried"] == 0 or enrich.remaining(con, day, since) == 0:
            return {**total, "usage": llm.usage()}


def main() -> int:
    ap = argparse.ArgumentParser(prog="pipeline")
    ap.add_argument("cmd", choices=["ingest", "news", "match", "ai", "daily",
                                    "all", "status", "backfill"])
    ap.add_argument("--pages", type=int, default=4)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--subcategory", default=None,
                    help="ดึงเฉพาะหมวดย่อย เช่น rebalance-report")
    ap.add_argument("--ai", action="store_true",
                    help="ให้ Claude Code อ่านข่าวเชิงลึกด้วย (ใช้กับ all)")
    ap.add_argument("--ai-limit", type=int, default=12, help="ขนาดล็อตของงาน AI")
    ap.add_argument("--workers", type=int, default=4, help="ยิง claude ขนานกี่เส้น")
    ap.add_argument("--redo", action="store_true", help="ให้ AI อ่านซ้ำทับของเดิม")
    ap.add_argument("--demote-mentions", action="store_true",
                    help="ถอน entity ที่กฎจับไว้ แต่ AI อ่านแล้วเห็นว่าบทความแค่เอ่ยถึง")
    ap.add_argument("--date", default="today",
                    help="วันข่าวที่ให้ AI อ่าน: today | YYYY-MM-DD | all (ทั้งคลัง)")
    a = ap.parse_args()

    db.init()
    con = db.connect()
    t0 = time.time()
    try:
        if a.cmd in ("ingest", "all"):
            try:
                show("ingest customers", ingest.ingest(con))
            except ingest.CustomerFilesMissing as e:
                # ไม่มีไฟล์ลูกค้าไม่ใช่ความผิดพลาด — เครื่องที่เพิ่ง clone มายังไม่มีแน่นอน
                # `all` ต้องทำขั้นที่เหลือ (ดึงข่าว) ต่อได้ ส่วน `ingest` เดี่ยว ๆ จบด้วย exit 1
                # เพราะผู้ใช้สั่งงานนี้ตรง ๆ ต้องรู้ว่าไม่ได้ทำ
                print(f"\n! ข้ามการนำเข้าไฟล์ลูกค้า\n{e}\n")
                if a.cmd == "ingest":
                    return 1
        if a.cmd in ("news", "all", "daily") and a.subcategory:
            show(f"ingest news [{a.subcategory}]",
                 news.ingest_subcategory(con, a.subcategory, pages=a.pages, limit=a.limit))
        elif a.cmd in ("news", "all", "daily"):
            show("ingest news", news.ingest_recent(con, pages=a.pages, limit=a.limit))
        if a.cmd == "backfill":
            # หมวดสำคัญที่ออกน้อย จึงไม่ติดมากับการดึงบทความล่าสุด
            # (Fund Robo รับได้แค่ 2 หมวดนี้ ตาม R6.16)
            for sub in ("rebalance-report", "intel-monthly-report", "weekly-fund-update",
                        "fund-review", "usoptions", "swdtfex", "macro", "industry-analysis"):
                show(f"backfill [{sub}]",
                     news.ingest_subcategory(con, sub, pages=1, limit=60))
            show("match", matching.run_for_articles(con, threshold=a.threshold))
        # AI อ่านก่อนจับคู่เสมอ — entity ที่ AI เพิ่มต้องมีผลกับการจับคู่รอบเดียวกัน
        if a.cmd in ("ai", "daily") or (a.cmd == "all" and a.ai):
            day = a.date
            if day == "today":     # วันข่าวล่าสุดในฐาน ไม่ใช่วันตามนาฬิกา
                day = con.execute("SELECT MAX(substr(trigger_at,1,10)) FROM articles").fetchone()[0]
            if day == "all":
                day = None
            print(f"\nai อ่านข่าว{'วันที่ ' + day if day else 'ทั้งคลัง'}"
                  f" · ขนาน {a.workers} เส้น", flush=True)
            show("ai", run_ai(con, day, a.ai_limit, a.workers, redo=a.redo,
                              demote=a.demote_mentions))
        if a.cmd in ("match", "all", "ai", "daily"):
            show("match", matching.run_for_articles(con, threshold=a.threshold))
        if a.cmd == "status":
            n = lambda q: con.execute(q).fetchone()[0]  # noqa: E731
            show("status", {
                "customers": n("SELECT COUNT(*) FROM customers"),
                "articles": n("SELECT COUNT(*) FROM articles WHERE record_type='article'"),
                "segments": n("SELECT COUNT(*) FROM articles WHERE record_type='segment'"),
                "matches": n("SELECT COUNT(*) FROM matches"),
                "unmapped": n("SELECT COALESCE(SUM(n),0) FROM unmapped"),
                "weak_evidence": n("SELECT COUNT(*) FROM articles WHERE auto_grade='weak'"),
                "by_grade": {
                    r[0] or "unknown": r[1]
                    for r in con.execute(
                        "SELECT auto_grade, COUNT(*) FROM articles WHERE role='content' GROUP BY 1")
                },
                "data_as_of": db.get_setting(con, "data_as_of"),
                "persona_counts": db.get_setting(con, "persona_counts", {}),
                "score_threshold": tables.SCORE_THRESHOLD,
            })
    finally:
        con.close()
    print(f"\nดำเนินการเสร็จใน {time.time() - t0:.1f} วินาที")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
