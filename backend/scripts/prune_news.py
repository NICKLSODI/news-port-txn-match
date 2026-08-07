# -*- coding: utf-8 -*-
"""ลบข่าวที่เก่ากว่าช่วงที่เก็บ (ค่าเริ่มต้น 14 วัน)

    python -m scripts.prune_news --dry-run        ดูก่อนว่าจะลบอะไร
    python -m scripts.prune_news                  ลบจริง (สำรองฐานให้ก่อนเสมอ)
    python -m scripts.prune_news --days 30        เปลี่ยนช่วง

ทำไมต้องลบ: RM ใช้ข่าวย้อนหลังไม่เกินสองสัปดาห์ ของเก่ากว่านั้นไม่ถูกเปิดดู
แต่ยังกินพื้นที่และทำให้ทุกงานที่กวาดทั้งตาราง (จับคู่ใหม่ ดึงเนื้อหาเต็ม) ช้าขึ้นเรื่อย ๆ
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, news, tables        # noqa: E402


def backup(path: Path) -> Path:
    """สำรองด้วย sqlite backup API — ปลอดภัยกับ WAL กว่าการ copy ไฟล์เฉย ๆ"""
    stamp = sqlite3.connect(str(path)).execute("SELECT strftime('%Y%m%d-%H%M','now','localtime')").fetchone()[0]
    out = path.parent / "backups" / f"matchport-{stamp}.db"
    out.parent.mkdir(exist_ok=True)
    src = sqlite3.connect(str(path))
    dst = sqlite3.connect(str(out))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=tables.RETENTION_DAYS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()

    con = db.connect()
    try:
        plan = news.prune_old(con, days=a.days, dry_run=True)
        print(f"เก็บข่าวตั้งแต่ {plan['cutoff']} ({a.days} วัน)")
        print(f"  จะลบ: บทความ {plan['articles']} · คู่จับ {plan['matches']}")
        print(f"  เหลือ: บทความ {plan['keep_articles']}")
        if a.dry_run:
            print("โหมดดูก่อน ไม่ได้ลบอะไร")
            return
        if not plan["articles"]:
            print("ไม่มีอะไรต้องลบ")
            return
        if not a.no_backup:
            print("สำรองฐาน:", backup(db.DB_PATH))
        res = news.prune_old(con, days=a.days)
        print(f"ลบแล้ว: บทความ {res['articles']} · คู่จับ {res['matches']} "
              f"· ล้าง article_id ค้างใน entity_pairs {res['pairs_cleaned']}")
        print(f"ขนาดไฟล์ {res['size_before_mb']} -> {res['size_after_mb']} MB")
    finally:
        con.close()


if __name__ == "__main__":
    main()
