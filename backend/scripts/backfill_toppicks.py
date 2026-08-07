# -*- coding: utf-8 -*-
"""เติม entity จากท่อน "หุ้นเด่น" ของเนื้อหาเต็ม แล้วจับคู่ใหม่ (GAP-23)

ใช้ครั้งเดียวกับคลังบทความที่ดึงเนื้อหาเต็มมาก่อนที่ตัวสกัดนี้จะมี
ของใหม่หลังจากนี้ถูกเติมอัตโนมัติตอน backfill_full_text
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, matching, news        # noqa: E402


def main() -> None:
    con = db.connect()
    try:
        before = con.execute(
            "SELECT COUNT(*) FROM articles WHERE role='content' AND entity IN ('[]','')"
        ).fetchone()[0]
        res = news.apply_top_picks(con)
        after = con.execute(
            "SELECT COUNT(*) FROM articles WHERE role='content' AND entity IN ('[]','')"
        ).fetchone()[0]
        print(f"เติม entity: {res['articles']} บทความ · {res['entities_added']} รายการ")
        print(f"บทความที่ยังไม่มี entity: {before} -> {after}")

        m = matching.run_for_articles(con, only_unmatched=True)
        print("จับคู่ใหม่:", {k: v for k, v in m.items() if k in
                              ("articles", "matches", "hit", "below_threshold")} or m)
    finally:
        con.close()


if __name__ == "__main__":
    main()
