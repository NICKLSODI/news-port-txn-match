# -*- coding: utf-8 -*-
"""ให้เกรดคุณภาพของ entity ที่ระบบสกัดเอง — ไม่บล็อกการจับคู่

STEP8 กำหนดว่า entity ระดับ inferred ต้องมีคนตรวจก่อนใช้จับคู่จริง
ระบบนี้ยกประตูนั้นออก (ดู GAP-21): ทุกบทความเข้าสู่การจับคู่ทันที
ส่วนตัวตรวจอัตโนมัติเปลี่ยนบทบาทเป็น "ผู้ให้เกรด" — บอกว่าหลักฐานแน่นแค่ไหน
และแน่นเพราะอะไร เพื่อให้คนเปิดดูย้อนหลังได้ว่าอันไหนควรสงสัย

เกรด
    confirmed      ที่มาน่าเชื่อถือในตัวเอง (field stock ของ API หรือ ticker ใน url)
    auto_verified  สกัดเอง และผ่านการตรวจซ้ำทุกข้อ
    weak           สกัดเอง และมีข้อที่ไม่ผ่าน — ยังจับคู่ แต่ติดธงให้คนดู

หลักการของตัวตรวจ: **ตรวจซ้ำเอง ไม่เชื่อสิ่งที่ต้นน้ำบอก**
ถ้าแค่ทวนกฎที่ขั้นสกัดกรองไปแล้ว (เช่น "alias ยาว >= 3" ที่ build_alias_index บังคับอยู่แล้ว)
เช็คนั้นจะไม่มีวันไม่ผ่าน กลายเป็นตรายางที่ทำให้เข้าใจผิดว่ามีการตรวจ
เช็คในไฟล์นี้จึงเป็นการยืนยันจากข้อมูลจริงซ้ำอีกรอบเท่านั้น:

    R4.47  ต้องบันทึกว่า "คำไหน" ทำให้จับ entity ตัวนั้นได้
    R4.43  คำนั้นต้องปรากฏในเนื้อความจริง ๆ (ค้นซ้ำเอง ไม่เชื่อบันทึก)
    R4.44  คำละตินต้องตรงแบบคำเต็ม ไม่ใช่ชิ้นส่วนของคำที่ยาวกว่า
    R3.38  คำที่ติดเกิน 30% ของคลังบทความ ถือว่ากว้างเกินไปจนใช้ไม่ได้
    R3.24  ไม่มีลูกค้าถือ = เรื่องปกติ ไม่ใช่ข้อผิดพลาด (เป็นข้อมูลประกอบ ไม่ตัดเกรด)

ไม่เรียก LLM โดยตั้งใจ — เกรดต้องออกมาเหมือนเดิมทุกครั้งที่รันด้วย input เดิม
และต้องอธิบายเป็นเลขกฎได้ ไม่ใช่ความเห็น
"""
from __future__ import annotations

import re

OVERBROAD_SHARE = 0.30          # R3.38

TRUSTED_SOURCES = {"api", "url_slug"}

_THAI_CH = r"฀-๿"
_THAI = re.compile(f"[{_THAI_CH}]")
_LATIN_WORD = re.compile(r"[A-Za-z0-9]")


def _token_of(ev) -> str | None:
    """R4.47 — หลักฐานเก็บเป็น {text, token, rule} จึงอ่าน token ได้ตรง ไม่ต้องเดาจากประโยค"""
    if isinstance(ev, dict):
        return (ev.get("token") or "").strip() or None
    return None


def _found_standalone(token: str, text: str) -> tuple[bool, str]:
    """ค้น token ในเนื้อความจริง คืน (เจอแบบคำเต็มไหม, บริบทรอบ ๆ)

    ละติน — ต้องไม่มีตัวอักษร/ตัวเลขติดหัวท้าย (R4.44)
    ไทย   — ไม่มีการเว้นวรรค จึงตรวจแค่ว่าพบจริง แล้วคืนบริบทให้คนอ่านตัดสิน (R3.37)
    """
    if not token or not text:
        return False, ""
    if _THAI.search(token):
        i = text.find(token)
        if i < 0:
            return False, ""
        return True, text[max(0, i - 12): i + len(token) + 12].replace("\n", " ")
    m = re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text, re.I)
    if not m:
        loose = text.lower().find(token.lower())
        if loose < 0:
            return False, ""
        return False, text[max(0, loose - 12): loose + len(token) + 12].replace("\n", " ")
    s = m.start()
    return True, text[max(0, s - 12): s + len(token) + 12].replace("\n", " ")


def grade(*, source: str, entities: list[str], evidence: dict[str, dict], title: str,
          held: set[str], text: str = "", overbroad: dict[str, float] | None = None) -> dict:
    """ให้เกรดบทความหนึ่งชิ้น — คืน grade + เหตุผล + รายการตรวจทีละข้อ

    text      เนื้อความที่ใช้สกัดจริง (หัวข้อ + สรุป หรือเนื้อข้อย่อย) ใช้ค้นซ้ำ
    overbroad {entity: สัดส่วนบทความที่สกัดตัวนี้ได้} สำหรับ R3.38
    """
    checks: list[dict] = []
    overbroad = overbroad or {}
    haystack = text or title

    def add(name: str, ok: bool, th: str, en: str, rule: str = "") -> None:
        checks.append({"check": name, "ok": ok, "th": th, "en": en, "rule": rule})

    if not entities:
        add("no_entity", True,
            "บทความนี้ไม่มี entity รายตัว จับคู่ด้วย sector หรือ macro แทน",
            "no per-instrument entity; matched by sector or macro instead", "R3.22")
        return _out("confirmed", checks, "ไม่มี entity ให้ตรวจ", "nothing to verify")

    if source in TRUSTED_SOURCES:
        add("trusted_source", True,
            "entity มาจาก field stock ของ API" if source == "api"
            else "ticker ฝังอยู่ใน url ของบทความ",
            "entity came from the API stock field" if source == "api"
            else "the ticker is embedded in the article url",
            "A-18")
        return _out("confirmed", checks, "ที่มาน่าเชื่อถือในตัวเอง", "self-evident source")

    # ------- ที่มาที่ระบบสกัดเอง: ตรวจซ้ำจากข้อมูลจริง -------
    for e in entities:
        token = _token_of(evidence.get(e))

        # R4.47 — ไม่มีบันทึกว่าคำไหนทำให้จับได้ = ตอบ RM ไม่ได้ว่าทำไม
        if not token:
            add(f"recorded:{e}", False,
                f"ไม่ได้บันทึกว่าจับ {e} ได้เพราะคำไหน จึงตรวจซ้ำไม่ได้",
                f"no token recorded for {e}, so it cannot be re-checked", "R4.47")
            continue
        add(f"recorded:{e}", True,
            f"บันทึกไว้ว่าจับ {e} ได้เพราะคำว่า “{token}”",
            f"recorded that “{token}” is what matched {e}", "R4.47")

        # R4.43 / R4.44 — ค้นซ้ำในเนื้อความเอง ไม่เชื่อบันทึกของขั้นสกัด
        ok, ctx = _found_standalone(token, haystack)
        rule = "R3.37" if _THAI.search(token) else "R4.44"
        if ok:
            add(f"in_text:{e}", True,
                f"เจอ “{token}” ในเนื้อความจริง: …{ctx}…",
                f"found “{token}” in the actual text: …{ctx}…", rule)
        else:
            add(f"in_text:{e}", False,
                (f"“{token}” เป็นชิ้นส่วนของคำที่ยาวกว่า: …{ctx}…" if ctx
                 else f"ค้นซ้ำแล้วไม่เจอ “{token}” ในเนื้อความ"),
                (f"“{token}” is embedded inside a longer word: …{ctx}…" if ctx
                 else f"re-checking could not find “{token}” in the text"), rule)

        # R3.38 — คำที่ติดเกิน 30% ของคลัง ถือว่ากว้างเกินจนใช้ไม่ได้
        share = overbroad.get(e, 0.0)
        if share > OVERBROAD_SHARE:
            add(f"overbroad:{e}", False,
                f"{e} ถูกสกัดได้จาก {share:.0%} ของคลังบทความ กว้างเกินเกณฑ์ 30%",
                f"{e} is extracted from {share:.0%} of the corpus, past the 30% limit", "R3.38")
        else:
            add(f"overbroad:{e}", True,
                f"{e} พบใน {share:.0%} ของคลังบทความ อยู่ในเกณฑ์",
                f"{e} appears in {share:.0%} of the corpus, within limits", "R3.38")

        # R3.24 — ไม่มีใครถือถือเป็นเรื่องปกติ เป็นข้อมูลประกอบ ไม่ตัดเกรด
        add(f"held:{e}", e in held,
            f"มีลูกค้าถือ {e} อยู่จริง" if e in held else f"ยังไม่มีลูกค้าคนไหนถือ {e}",
            f"customers hold {e}" if e in held else f"no customer holds {e}", "R3.24")

    hard = [c for c in checks if not c["ok"] and not c["check"].startswith("held:")]
    if hard:
        return _out("weak", checks,
                    "; ".join(c["th"] for c in hard[:2]),
                    "; ".join(c["en"] for c in hard[:2]))
    return _out("auto_verified", checks,
                "ค้นซ้ำในเนื้อความแล้วเจอทุกคำ และไม่มีคำไหนกว้างเกินเกณฑ์",
                "every token was re-found in the text, and none is over-broad")


def _out(g: str, checks: list, th: str, en: str) -> dict:
    return {"grade": g, "reason_th": th, "reason_en": en, "checks": checks,
            "n_checks": len(checks), "n_failed": sum(1 for c in checks if not c["ok"])}


# ==========================================================================

def corpus_share(con) -> dict[str, float]:
    """R3.38 — สัดส่วนบทความที่สกัด entity แต่ละตัวได้

    นับเฉพาะที่ระบบสกัดเอง (title / summary) เพราะกฎนี้พูดถึง "คำค้น"
    ไม่ใช่ ticker ที่ API ส่งมาให้ตรง ๆ
    """
    from . import db

    rows_ = list(con.execute(
        "SELECT entity FROM articles WHERE entity_source IN ('title','summary')"))
    total = len(rows_)
    if not total:
        return {}
    seen: dict[str, int] = {}
    for r in rows_:
        for e in set(db.jload(r["entity"], []) or []):
            seen[e] = seen.get(e, 0) + 1
    return {e: n / total for e, n in seen.items()}


def regrade(con, only_missing: bool = True) -> dict:
    """ให้เกรดใหม่ — ไม่มีแถวไหนควรค้างเป็น unknown

    only_missing=False ใช้ตอนกฎการให้เกรดเปลี่ยน
    """
    from . import db

    held = held_entities(con)
    share = corpus_share(con)
    where = "WHERE auto_grade IS NULL" if only_missing else ""
    rows_ = list(con.execute(
        f"""SELECT article_id, title, summary, segment_text, entity, entity_source, evidence
            FROM articles {where}"""))
    out: dict[str, int] = {}
    with con:
        for r in rows_:
            body = r["segment_text"] or f"{r['title'] or ''} {r['summary'] or ''}"
            g = grade(source=r["entity_source"] or "none",
                      entities=db.jload(r["entity"], []) or [],
                      evidence=db.jload(r["evidence"], {}) or {},
                      title=r["title"] or "",
                      held=held, text=body, overbroad=share)
            out[g["grade"]] = out.get(g["grade"], 0) + 1
            con.execute(
                """UPDATE articles SET auto_grade=?, auto_reason_th=?, auto_reason_en=?,
                                       auto_checks=? WHERE article_id=?""",
                (g["grade"], g["reason_th"], g["reason_en"], db.jdump(g["checks"]),
                 r["article_id"]))
    return {"regraded": len(rows_), "by_grade": out}


def held_entities(con) -> set[str]:
    return {
        r["entity"]
        for r in con.execute(
            "SELECT DISTINCT entity FROM holdings WHERE entity IS NOT NULL "
            "UNION SELECT DISTINCT entity FROM transactions WHERE entity IS NOT NULL"
        )
    }
