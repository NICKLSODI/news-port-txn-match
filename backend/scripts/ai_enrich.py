# -*- coding: utf-8 -*-
"""ให้ Claude Code อ่านข่าวเชิงลึก แล้วเติมสิ่งที่กฎคำอ่านไม่ออก (AI-01 / AI-02)

    python -m scripts.ai_enrich --date today --limit 5 --dry-run   ลองดูผลก่อน ไม่บันทึก
    python -m scripts.ai_enrich --date today --all --workers 4     อ่านข่าววันนี้ให้หมด
    python -m scripts.ai_enrich --date today --all --redo          อ่านซ้ำทับของเดิม
    python -m scripts.ai_enrich --clean-briefs                     ถอน entity รวมของแม่ Brief
    python -m scripts.ai_enrich --no-match                         ไม่ต้องจับคู่ใหม่ท้ายงาน

ใช้สิทธิ์ claude login บนเครื่อง ไม่ต้องมี ANTHROPIC_API_KEY
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, enrich, llm, matching        # noqa: E402
from app.news import SEGMENTED_SUBCATEGORIES     # noqa: E402


def clean_briefs(con) -> int:
    """ถอน entity ที่ AI ใส่ให้ "แม่" ของ Brief ออก (R3.3 ห้ามมี entity รวม)"""
    marks = ",".join("?" * len(SEGMENTED_SUBCATEGORIES))
    rows = list(con.execute(
        f"SELECT article_id, entity, evidence FROM articles "
        f"WHERE record_type='article' AND subcategory IN ({marks}) AND evidence LIKE '%AI-01%'",
        tuple(SEGMENTED_SUBCATEGORIES)))
    n = 0
    for r in rows:
        ev = json.loads(r["evidence"] or "{}")
        drop = {k for k, v in ev.items() if v.get("rule") == "AI-01"}
        if not drop:
            continue
        ents = [e for e in json.loads(r["entity"] or "[]") if e not in drop]
        keep = {k: v for k, v in ev.items() if k not in drop}
        with con:
            con.execute("UPDATE articles SET entity=?, evidence=?, matched_at=NULL "
                        "WHERE article_id=?",
                        (json.dumps(ents, ensure_ascii=False),
                         json.dumps(keep, ensure_ascii=False), r["article_id"]))
            con.execute("DELETE FROM matches WHERE article_id=?", (r["article_id"],))
        n += len(drop)
    return n


def show_item(it: dict, verbose: bool) -> None:
    """พิมพ์ผลรายชิ้น — ที่รับและที่ไม่รับ อยู่บรรทัดเดียวกันเสมอ

    ที่ไม่รับต้องเห็นด้วยตาเปล่า ไม่งั้นคนอ่านสรุปจะเข้าใจว่า AI "ไม่เจออะไร"
    ทั้งที่จริงคือเจอแล้วตัดสินใจไม่นับ ซึ่งเป็นคนละเรื่องกัน
    """
    print(f"    {it['direction']:19} {str(it['added'])[:32]:34} {it['title'][:38]}", flush=True)
    if it.get("reason_th"):
        print(f"      ไม่ตีความ: {it['reason_th'][:150]}", flush=True)
    if it.get("demoted"):
        print(f"      ถอนของที่กฎจับเกิน: {it['demoted']}", flush=True)
    elif it.get("flagged"):
        print(f"      กฎจับไว้แต่แค่เอ่ยถึง: {it['flagged']}", flush=True)
    if verbose:
        for m in it.get("mentions", []):
            mark = "รับ " if m["kept"] else "ทิ้ง"
            print(f"      {mark} {m['symbol']:8} {m['role']:13} {m['why'][:70]}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--clean-briefs", action="store_true")
    ap.add_argument("--no-match", action="store_true")
    ap.add_argument("--date", default=None,
                    help="อ่านเฉพาะข่าววันนี้/วันที่ระบุ (YYYY-MM-DD หรือ today)")
    ap.add_argument("--all", action="store_true",
                    help="ไล่อ่านจนหมดคลัง ทีละล็อต ขาดตอนแล้วรันซ้ำได้ (ai_at กันอ่านซ้ำ)")
    ap.add_argument("--workers", type=int, default=4,
                    help="ยิง claude ขนานกันกี่เส้น (งานนี้รอ I/O ไม่ใช่กิน CPU)")
    ap.add_argument("--batch-size", type=int, default=1,
                    help="รวมกี่บทความเข้า claude call เดียว (ลด overhead คงที่ต่อครั้ง) "
                         "ค่าเริ่มต้น 1 = เดิม ทีละชิ้น แนะนำ 4-5 ถ้าจะประหยัด token")
    ap.add_argument("--dry-run", action="store_true",
                    help="อ่านและตรวจ แต่ไม่บันทึกลงฐาน — ใช้ดูคุณภาพก่อนรันจริง")
    ap.add_argument("--verbose", action="store_true",
                    help="โชว์ทุกตัวย่อที่โมเดลเห็น พร้อมผลตรวจว่ารับหรือทิ้งเพราะอะไร")
    ap.add_argument("--demote-mentions", action="store_true",
                    help="ถอน entity ที่กฎจับไว้ แต่ AI อ่านแล้วเห็นว่าบทความแค่เอ่ยถึง")
    a = ap.parse_args()

    info = llm.available()
    print(f"claude: {info['bin'] or 'ไม่พบ'} · โมเดล {info['model']} · ขนาน {a.workers} เส้น")
    if not info["available"]:
        sys.exit("ต้องติดตั้ง Claude Code แล้วรัน claude login ก่อน")

    db.init()
    con = db.connect()
    try:
        day = a.date
        if day == "today":         # วันข่าวล่าสุดในฐาน ไม่ใช่วันตามนาฬิกา
            day = con.execute("SELECT MAX(substr(trigger_at,1,10)) FROM articles").fetchone()[0]
        if day:
            print("อ่านเฉพาะข่าววันที่", day)
        if a.dry_run:
            print("โหมดลองอ่าน — ไม่บันทึกลงฐาน")
        if a.clean_briefs:
            print("ถอน entity รวมของแม่ Brief:", clean_briefs(con), "รายการ")

        total = {"done": 0, "added": 0, "dropped": 0, "problems": 0,
                 "flagged": 0, "demoted": 0, "dirs": {}, "reasons": {}}
        rounds = 0
        # รอบอ่านซ้ำต้องจำเวลาเริ่ม ไม่งั้นล็อตถัดไปจะหยิบชิ้นเดิมที่เพิ่งอ่านไปมาอีก
        since = dt.datetime.now().isoformat(timespec="seconds") if a.redo else ""
        while True:
            rounds += 1
            res = enrich.enrich_batch(con, limit=a.limit, redo=a.redo, date=day,
                                      workers=a.workers, dry_run=a.dry_run,
                                      demote=a.demote_mentions, since=since,
                                      batch_size=a.batch_size)
            if res.get("problem"):
                sys.exit(res["problem"])
            total["done"] += res["done"]
            total["added"] += res["entities_added"]
            total["dropped"] += res["dropped"]
            total["problems"] += res["problems"]
            total["flagged"] += res["flagged"]
            total["demoted"] += res["demoted"]
            for k, v in res["directions"].items():
                total["dirs"][k] = total["dirs"].get(k, 0) + v
            for k, v in res["reasons"].items():
                total["reasons"][k] = total["reasons"].get(k, 0) + v
            left = enrich.remaining(con, day, since)
            print(f"[ล็อต {rounds}] อ่าน {res['done']}/{res['tried']} · entity +{res['entities_added']}"
                  f" · ไม่รับ {res['dropped']} · ทิศทาง {res['directions']} · เหลือ {left}",
                  flush=True)
            for it in res["items"]:
                show_item(it, a.verbose)
            # dry-run ไม่เขียน ai_at จำนวนที่เหลือจึงไม่ลด วนต่อจะได้ชิ้นเดิมซ้ำ
            if not a.all or a.dry_run or res["tried"] == 0 or left == 0:
                break

        print(f"\nรวม: อ่าน {total['done']} ชิ้น · entity เพิ่ม {total['added']}"
              f" · ตัวย่อที่ไม่รับ {total['dropped']} · ปัญหา {total['problems']}")
        if total["flagged"] or total["demoted"]:
            verb = "ถอนออก" if a.demote_mentions else "ติดป้ายเตือน (ยังไม่ถอน)"
            print(f"กฎจับไว้แต่ AI เห็นว่าบทความแค่เอ่ยถึง: "
                  f"{total['demoted'] or total['flagged']} รายการ — {verb}")
        print("ทิศทางที่อ่านได้ทั้งหมด:", total["dirs"])
        if total["reasons"]:
            print("เหตุผลที่ไม่สรุปทิศทาง:", total["reasons"])
        u = llm.usage()
        if u["calls"]:
            tin = u["input"] + u["cache_write"] + u["cache_read"]
            print(f"ใช้โมเดล {u['calls']} ครั้ง · เข้า {tin:,} token"
                  f" (ใหม่ {u['input'] + u['cache_write']:,} · จากแคช {u['cache_read']:,})"
                  f" · ออก {u['output']:,} token · ${u['cost_usd']:.2f}"
                  f" (เฉลี่ย ${u['cost_usd'] / u['calls']:.3f}/ชิ้น)")

        if not a.no_match and not a.dry_run:
            m = matching.run_for_articles(con, only_unmatched=True)
            print("จับคู่ใหม่:", {k: m[k] for k in ("articles_matched", "matches") if k in m} or m)
    finally:
        con.close()


if __name__ == "__main__":
    main()
