# -*- coding: utf-8 -*-
"""เติมเนื้อหาเต็มให้บทความที่เก็บไว้แล้ว

    python -m scripts.backfill_fulltext            เฉพาะที่ยังไม่มี
    python -m scripts.backfill_fulltext --redo     ดึงใหม่ทั้งหมด
    python -m scripts.backfill_fulltext --limit 20 ลองสัก 20 ชิ้นก่อน

จำกัดอัตราเรียก 0.4 วินาทีต่อหน้าตาม R2.6 — 900 บทความใช้เวลาราว 7 นาที
บทความที่ดึงไม่ได้จะถูกรายงานเข้า bucket full_text (R2.5) ไม่เงียบ
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, news  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--retry-failed", action="store_true",
                    help="ลองใหม่เฉพาะที่เคยดึงไม่ได้")
    a = ap.parse_args()

    db.init()
    con = db.connect()
    try:
        if a.retry_failed:
            with con:
                n = con.execute(
                    "UPDATE articles SET full_text_at=NULL WHERE record_type='article' "
                    "AND role='content' AND (full_text IS NULL OR full_text='')").rowcount
            print(f"ล้างสถานะที่เคยดึงไม่ได้ {n} แถว เพื่อลองใหม่")
        todo = con.execute(
            "SELECT COUNT(*) FROM articles WHERE record_type='article' AND role='content'"
            + ("" if a.redo else " AND full_text_at IS NULL")
        ).fetchone()[0]
        n = min(todo, a.limit) if a.limit else todo
        print(f"จะดึง {n} บทความ (ประมาณ {n * 0.5 / 60:.1f} นาที)", flush=True)

        t0 = time.time()
        out = news.backfill_full_text(con, limit=a.limit, redo=a.redo)
        rows = list(con.execute(
            "SELECT COUNT(*) n, AVG(LENGTH(full_text)) avg_len, MAX(LENGTH(full_text)) max_len "
            "FROM articles WHERE full_text IS NOT NULL AND full_text<>''"))[0]
        print(f"\nเสร็จใน {time.time() - t0:.0f} วินาที")
        print(f"  ดึงสำเร็จรอบนี้ {out['stored']} · ล้มเหลว {out['failed']} จาก {out['tried']}")
        for reason, n in sorted(out["reasons"].items(), key=lambda kv: -kv[1]):
            print(f"    - {reason}: {n}")
        print(f"  ในฐานข้อมูลมีเนื้อหาเต็มแล้ว {rows['n']} แถว "
              f"(เฉลี่ย {int(rows['avg_len'] or 0):,} ตัวอักษร · ยาวสุด {int(rows['max_len'] or 0):,})")
    finally:
        con.close()


if __name__ == "__main__":
    main()
