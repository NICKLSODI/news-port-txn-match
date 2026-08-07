# -*- coding: utf-8 -*-
"""ล้าง entity ที่เคยเติมจากหุ้นเด่น (GAP-23) แล้วสกัดใหม่ + จับคู่ใหม่

ใช้เมื่อแก้ตัวสกัด — ของที่เคยเติมผิดต้องหลุดออก ไม่ใช่ค้างอยู่ในฐาน
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, matching, news        # noqa: E402


def main() -> None:
    con = db.connect()
    try:
        removed = 0
        for r in list(con.execute(
                "SELECT article_id, entity, evidence, sector FROM articles "
                "WHERE evidence LIKE '%GAP-23%'")):
            ev = json.loads(r["evidence"] or "{}")
            drop = {k for k, v in ev.items() if v.get("rule") == "GAP-23"}
            if not drop:
                continue
            ents = [e for e in (json.loads(r["entity"] or "[]")) if e not in drop]
            keep = {k: v for k, v in ev.items() if k not in drop}
            with con:
                con.execute("UPDATE articles SET entity=?, evidence=?, matched_at=NULL "
                            "WHERE article_id=?",
                            (json.dumps(ents, ensure_ascii=False),
                             json.dumps(keep, ensure_ascii=False), r["article_id"]))
            removed += len(drop)
        print(f"ถอนของเก่า {removed} รายการ")

        res = news.apply_top_picks(con)
        print(f"สกัดใหม่: {res['articles']} บทความ · {res['entities_added']} รายการ")

        # ลบคู่เก่าของบทความที่เปลี่ยน แล้วคำนวณใหม่ ไม่ให้คู่จากของผิดค้าง
        ids = [r[0] for r in con.execute(
            "SELECT article_id FROM articles WHERE matched_at IS NULL AND role='content'")]
        if ids:
            with con:
                for i in range(0, len(ids), 400):
                    chunk = ids[i:i + 400]
                    con.execute(
                        f"DELETE FROM matches WHERE article_id IN ({','.join('?' * len(chunk))})",
                        chunk)
        m = matching.run_for_articles(con, only_unmatched=True)
        print("จับคู่ใหม่:", m)
    finally:
        con.close()


if __name__ == "__main__":
    main()
