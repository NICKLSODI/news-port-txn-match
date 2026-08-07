# -*- coding: utf-8 -*-
"""ตรวจด่านกรองของ AI-01/AI-02 โดยไม่เรียกโมเดลจริง

    python -m scripts.check_ai_guards

enrich.judge เป็นฟังก์ชันบริสุทธิ์ (ไม่แตะฐาน ไม่เรียก claude) จึงป้อนคำตอบสมมติ
ของโมเดลเข้าไปตรงได้ เคสในนี้มาจากของที่เจอจริงในคลัง ไม่ใช่เคสที่แต่งขึ้นลอย ๆ:
บทความเล่าประวัติบริษัท · ตัวย่อชนข้ามประเทศ · โมเดลนึกตัวย่อจากชื่อบริษัทเอง

ต้องใช้ฐานจริง เพราะรายการที่ลูกค้าถือเป็นส่วนหนึ่งของการตัดสิน
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, enrich       # noqa: E402

TH = {"article_id": "t", "article_asset_class": '["EQUITY_TH"]'}
OFF = {"article_id": "t", "article_asset_class": '["EQUITY_OFFSHORE"]'}


def stock(**kw) -> dict:
    base = {"symbol": "", "name": "", "market": "", "role": "analyze", "quote": ""}
    return {**base, **kw}


def answer(stocks: list, overall: str = "unknown", dquote: str = "",
           reason: str = "no_view") -> dict:
    return {"stocks": stocks, "direction": {"overall": overall, "quote": dquote},
            "no_call_reason": reason, "macro": []}


# (ชื่อเคส, บทความ, คำตอบสมมติของโมเดล, เนื้อหา, entity ที่ต้องได้, ทิศทางที่ต้องได้)
CASES = [
    ("เล่าประวัติบริษัท — ห้ามนับเป็นการแนะนำ", OFF,
     answer([stock(symbol="ASTS", market="US", role="mention_only",
                   quote="ASTS เริ่มต้นจากบริษัทดาวเทียมขนาดเล็ก")], reason="history_only"),
     "ASTS เริ่มต้นจากบริษัทดาวเทียมขนาดเล็ก และขยายธุรกิจต่อเนื่อง", [], "unknown"),

    ("ตัวย่อชนข้ามประเทศ — TEL ญี่ปุ่นไม่ใช่ TEL:xnys", OFF,
     answer([stock(symbol="TEL", name="Tokyo Electron", market="JP",
                   quote="TEL รายงานกำไรไตรมาสแรกดีกว่าคาด")], reason="data_only"),
     "TEL รายงานกำไรไตรมาสแรกดีกว่าคาด หนุนจากคำสั่งซื้อเครื่องจักร", [], "unknown"),

    ("TEL ตลาดสหรัฐ = TE Connectivity ที่ลูกค้าถือจริง", OFF,
     answer([stock(symbol="TEL", name="TE Connectivity", market="US", role="recommend",
                   quote="TEL ได้ประโยชน์จากคำสั่งซื้อรถ EV")],
            "up", "TEL ได้ประโยชน์จากคำสั่งซื้อรถ EV", ""),
     "TEL ได้ประโยชน์จากคำสั่งซื้อรถ EV ที่ฟื้นตัว", ["TEL:xnys"], "up"),

    ("TSMC ADR — พจนานุกรมต้องชนะคำเดาตลาดของโมเดล", OFF,
     answer([stock(symbol="TSMC", name="TSMC", market="TW", role="recommend",
                   quote="TSMC ยังคงความได้เปรียบด้านเทคโนโลยีการผลิตชิป")],
            "up", "TSMC ยังคงความได้เปรียบด้านเทคโนโลยีการผลิตชิป", ""),
     "TSMC ยังคงความได้เปรียบด้านเทคโนโลยีการผลิตชิปขั้นสูง", ["TSM:xnys"], "up"),

    ("ชื่อบริษัทในพจนานุกรม — บทความไม่ได้พิมพ์ตัวย่อ", OFF,
     answer([stock(name="Nvidia", market="US", role="recommend",
                   quote="Nvidia ยังครองส่วนแบ่งชิป AI")],
            "up", "Nvidia ยังครองส่วนแบ่งชิป AI", ""),
     "Nvidia ยังครองส่วนแบ่งชิป AI มากกว่า 80%", ["NVDA:xnas"], "up"),

    ("โมเดลนึกตัวย่อจากชื่อบริษัทเอง — ตัวย่อไม่มีในบทความ", TH,
     answer([stock(symbol="KBANK", market="TH", role="recommend",
                   quote="ธนาคารกสิกรไทยกำไรโต")]),
     "ธนาคารกสิกรไทยกำไรโตต่อเนื่องจากรายได้ดอกเบี้ย", [], "unknown"),

    ("ประโยคมีจริง แต่ไม่ได้เอ่ยถึงหุ้นตัวนั้น", TH,
     answer([stock(symbol="DELTA", market="TH", role="recommend",
                   quote="กลุ่มธนาคารได้ประโยชน์จากดอกเบี้ยขาขึ้น")]),
     "DELTA ราคาปรับขึ้น ขณะที่กลุ่มธนาคารได้ประโยชน์จากดอกเบี้ยขาขึ้น", [], "unknown"),

    ("บทความหุ้นนอกล้วน แต่แปลงได้เป็นรหัสหุ้นไทย", OFF,
     answer([stock(symbol="DELTA", market="TH", role="recommend",
                   quote="DELTA ยังเป็นตัวเลือกแรกของกลุ่ม")]),
     "DELTA ยังเป็นตัวเลือกแรกของกลุ่มอิเล็กทรอนิกส์", [], "unknown"),

    ("โมเดลบอกว่าหุ้นนอก แต่รหัสเป็นหุ้นไทย", OFF,
     answer([stock(symbol="SCB", market="US", role="recommend",
                   quote="SCB is our top pick in the sector")]),
     "SCB is our top pick in the sector this quarter", [], "unknown"),

    ("ทิศทางที่ยกประโยคไม่ตรงกับบทความ — ต้องตกเป็นไม่รู้", TH,
     answer([], "down", "ตลาดจะปรับฐานแรงในสัปดาห์หน้า", ""),
     "ดัชนีปิดบวก 5 จุด นักลงทุนต่างชาติซื้อสุทธิ", [], "unknown"),

    ("ตัวย่อสั้น 2 ตัวอักษรที่ลูกค้าถือจริง (TU)", TH,
     answer([stock(symbol="TU", market="TH", role="recommend",
                   quote="TU เป็นหุ้นเด่นของกลุ่มอาหาร")],
            "up", "TU เป็นหุ้นเด่นของกลุ่มอาหาร", ""),
     "TU เป็นหุ้นเด่นของกลุ่มอาหาร ราคาเป้าหมาย 16 บาท", ["TU"], "up"),
]


def main() -> int:
    con = db.connect()
    refs = enrich.Refs(con)
    bad = 0
    try:
        for name, art, data, body, want_ents, want_dir in CASES:
            v = enrich.judge(art, data, body, refs.by_alias, refs.uni,
                             refs.crypto, refs.aliases_of)
            got = sorted(k["entity"] for k in v["kept"])
            ok = got == sorted(want_ents) and v["direction"] == want_dir
            # ทุกเคสที่ตกต้องมีเหตุผลติดมาด้วยเสมอ ไม่งั้นหน้าจอจะว่างเปล่าโดยไม่มีคำอธิบาย
            if v["direction"] == "unknown" and not v["reason_th"]:
                ok = False
            bad += not ok
            print(f"{'ผ่าน' if ok else 'ตก  '} {name}")
            if not ok:
                print(f"      ได้ {got} ทิศทาง {v['direction']} · ต้องการ {want_ents} {want_dir}")
                for m in v["mentions"]:
                    print(f"      {'รับ' if m['kept'] else 'ทิ้ง'} {m['symbol']}: {m['why']}")
    finally:
        con.close()
    print(f"\n{len(CASES) - bad}/{len(CASES)} ผ่าน")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
