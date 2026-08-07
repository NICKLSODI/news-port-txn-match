# -*- coding: utf-8 -*-
"""STEP6 — Matching Rulebook (R6.1 - R6.16)

จับคู่บทความ 1 ชิ้น -> รายชื่อลูกค้าที่ควรติดต่อ เรียงตามคะแนน
ทุกแถวเก็บหลักฐานว่าเข้าระดับไหนเพราะ entity ตัวไหน (หลักการข้อ 3)
"""
from __future__ import annotations

import datetime as dt
import math

from . import db
from .mapping import coverage_of, refdata, sector_of
from .tables import (
    LEVEL_WEIGHT,
    MAX_LEVEL_BY_MODE,
    MIN_SECTOR_WEIGHT,
    MULTI_HIT_BONUS,
    PERSONA_CONTENT_MAP,
    RECENCY_FACTOR,
    SCORE_THRESHOLD,
    URGENCY_FACTOR,
)

LEVEL_ORDER = ["L1_HOLD", "L2_WATCH", "L3_SECTOR", "L4_RELATED", "L5_ASSET", "L6_MACRO"]
LEVEL_INDEX = {name: i + 1 for i, name in enumerate(LEVEL_ORDER)}

# GAP-11 — R6.6 บอกให้ถ่วง L6 ตาม "ความไวของพอร์ต" แต่ไม่ได้ให้สูตร
# ตารางนี้เป็นค่าที่ระบบตั้งเอง (ASSUMED) ปรับได้
MACRO_SENSITIVITY = {
    "ค่าเงิน":        {"asset": {"EQUITY_OFFSHORE", "FUND_OFFSHORE", "BOND_OFFSHORE",
                                "OPTIONS_OFFSHORE"}},
    "สงครามการค้า":   {"asset": {"EQUITY_OFFSHORE", "FUND_OFFSHORE", "OPTIONS_OFFSHORE"}},
    "ดอกเบี้ย":       {"asset": {"BOND_TH", "BOND_OFFSHORE"},
                      "sector": {"Banking", "Finance & Securities", "Insurance"}},
    "ราคาน้ำมัน":     {"sector": {"Energy & Utilities", "Petrochemicals & Chemicals",
                                 "Transportation & Logistics"}},
    "GDP":           {"asset": {"EQUITY_TH", "EQUITY_OFFSHORE"}},
    "เงินเฟ้อ":       {"all": True},
}

# GAP-19 — R6.16 ตั้งใจให้ Fund Robo ได้รับ Rebalance/Monthly Report ทุกฉบับ (สองหมวดนี้คือ
# เนื้อหาหลักของ persona นี้ ไม่ใช่แค่ข่าวประกอบ) แต่น้ำหนักฐาน L5 มาตรฐาน (20) คูณด้วย
# ตัวคูณอื่นแล้วไม่เคยพอผ่านเกณฑ์ 50 แม้พอร์ตเป็น FUND_ROBO ล้วน — ยกน้ำหนักเฉพาะคู่นี้
# (asset_classes == {"FUND_ROBO"} ซึ่งมาจาก ASSET_CLASS_OVERRIDE_BY_SUBCATEGORY สองหมวดนั้น
# เท่านั้น) ไม่แตะน้ำหนัก L5 มาตรฐานของ asset class อื่น (เช่นบทความ macro กว้าง ๆ ที่ใช้ "*")
FUND_ROBO_REPORT_WEIGHT = 55.0


def _log_scale(value: float) -> float:
    """R6.8 — ถือมูลค่ามากได้คะแนนสูงกว่า ใช้ log กันรายใหญ่กลบทุกคน

    คืนค่า 0..1 โดย 20 ลบ. (เกณฑ์ VIP ของ CF-08) แตะ 1.0
    """
    if not value or value <= 0:
        return 0.0
    return min(1.0, math.log10(1 + value) / math.log10(1 + 20_000_000))


def _recency_factor(last_traded: str | None, ref: dt.date) -> tuple[float, int | None]:
    """R6.11 — เพิ่งเทรดตัวนั้น = กำลังสนใจ (เทียบกับวันที่บทความออก)"""
    if not last_traded:
        return 1.0, None
    try:
        days = (ref - dt.date.fromisoformat(last_traded[:10])).days
    except ValueError:
        return 1.0, None
    for limit, factor in RECENCY_FACTOR:
        if 0 <= days <= limit:
            return factor, days
    return 1.0, days


def _why(evidence: dict, key: str) -> str:
    """R4.47 — ดึงข้อความหลักฐานของ entity หนึ่งตัว (หลักฐานเก็บเป็น {text, token, rule})"""
    v = evidence.get(key)
    if isinstance(v, dict):
        return str(v.get("text", ""))
    return str(v or "")


def learned_related(con, min_count: int = 3) -> dict[str, set[str]]:
    """R3.31 — นับว่าเกี่ยวข้องกันต่อเมื่อปรากฏด้วยกันอย่างน้อย 3 ครั้ง"""
    out: dict[str, set[str]] = {}
    for r in con.execute("SELECT a, b FROM entity_pairs WHERE n >= ?", (min_count,)):
        out.setdefault(r["a"], set()).add(r["b"])
        out.setdefault(r["b"], set()).add(r["a"])
    return out


def seed_related(con) -> dict[str, set[str]]:
    """C2 seed จาก STEP4 — สมาชิกในชีตเป็น ticker เปล่า (BAC, LMT, 0700)

    ต้องคลี่ให้เป็นรหัสกลางก่อน (BAC:xnys, 00700:xhkg) ไม่งั้นเทียบกับพอร์ตไม่ติด
    """
    from .news import universe_from_db

    uni = universe_from_db(con)

    def canon(tok: str) -> str | None:
        tok = tok.strip().upper()
        if not tok:
            return None
        ent, _ = uni.resolve_root(tok)
        if ent:
            return ent
        if tok.isdigit():                                  # R4.6 — ฮ่องกงเติมศูนย์ 5 หลัก
            ent, _ = uni.resolve_root(tok.zfill(5))
            if ent:
                return ent
        return None

    out: dict[str, set[str]] = {}
    for grp in refdata()["related_groups"]:
        members = [m for m in (canon(x) for x in grp["members"]) if m]
        for a in members:
            out.setdefault(a, set()).update(x for x in members if x != a)
    return out


# ==========================================================================

def persona_accepts(persona: str, content_type: str) -> bool:
    """R6.16 — กรองด้วย persona ก่อนจับคู่เสมอ"""
    return content_type in PERSONA_CONTENT_MAP.get(persona, set())


def match_article(article: dict, customers: list[dict], *, threshold: float = SCORE_THRESHOLD,
                  extra_related: dict[str, set[str]] | None = None) -> tuple[list[dict], dict]:
    """คืน (รายการที่ผ่านเกณฑ์, สรุปสถิติ)"""
    mode = article["mode"]
    max_level = MAX_LEVEL_BY_MODE[mode]
    entities = set(db.jload(article["entity"], []) or [])
    sectors = set(db.jload(article["sector"], []) or [])
    macro = [m["topic"] for m in (db.jload(article["macro_topic"], []) or [])]
    asset_classes = set(db.jload(article["article_asset_class"], []) or [])
    content_type = article["content_type"]
    importance = article["importance"] or 1
    urgency = article["urgency"] or "low"
    # evidence เก็บเป็น JSON ในคอลัมน์ articles.evidence — ต้อง decode ก่อนใช้
    raw_ev = article.get("evidence")
    evidence_src = (raw_ev if isinstance(raw_ev, dict) else db.jload(raw_ev, {})) or {}

    try:
        ref = dt.date.fromisoformat(str(article["trigger_at"])[:10])
    except ValueError:
        ref = dt.date.today()

    importance_factor = importance / 3.0
    urgency_factor = URGENCY_FACTOR.get(urgency, 0.7)

    out, stats = [], {"considered": 0, "persona_filtered": 0, "hit": 0,
                      "below_threshold": 0, "by_level": {}}

    for c in customers:
        stats["considered"] += 1
        if not persona_accepts(c["persona"], content_type):
            stats["persona_filtered"] += 1
            continue

        holds: dict[str, float] = c["holdings"]
        watch: dict[str, str] = c["watchlist"]
        labels: dict[str, str] = c["labels"]
        last: dict[str, str] = c["last_traded"]
        hits: list[dict] = []

        # ---- L1 ถือตรงตัว (R6.1) ----
        for e in entities:
            if e in holds:
                val = holds[e] or 0.0
                hits.append({
                    "level": "L1_HOLD", "entity": e, "rule": "R6.1", "value": val,
                    "th": f"ถือ {e} มูลค่า {val:,.0f} บาท" if val else f"ถือ {e} (ไม่ทราบมูลค่า)",
                    "en": f"holds {e} worth THB {val:,.0f}" if val else f"holds {e} (value unknown)",
                    "label": labels.get(e, ""),
                    "why": _why(evidence_src, e),
                })

        # ---- L2 watchlist (R6.2) ----
        if max_level >= 2:
            for e in entities:
                if e in watch and e not in holds:
                    hits.append({
                        "level": "L2_WATCH", "entity": e, "rule": "R6.2", "value": 0.0,
                        "th": f"เคยเทรด {e} เมื่อ {watch[e]} แต่ตอนนี้ไม่ถือ",
                        "en": f"traded {e} on {watch[e]}, no longer holding",
                        "label": labels.get(e, ""), "why": _why(evidence_src, e),
                    })

        # ---- L3 sector เดียวกัน — หุ้นไทยเท่านั้น (R6.3) ----
        if max_level >= 3:
            for s in sectors:
                w = c["sector_exposure"].get(s, 0.0)
                if w >= MIN_SECTOR_WEIGHT:
                    hits.append({
                        "level": "L3_SECTOR", "entity": s, "rule": "R6.3",
                        "value": w * (c["portfolio_value"] or 0.0),
                        "th": f"ถือหุ้นกลุ่ม {s} คิดเป็น {w:.0%} ของพอร์ต",
                        "en": f"holds {w:.0%} of portfolio in {s}",
                        "label": "", "why": _why(evidence_src, s),
                    })

        # ---- L4 ความสัมพันธ์หุ้น (R6.4) ----
        # GAP-20 — R6.4 ตั้งใจให้ L4 เป็นตัวแทน L3 สำหรับหุ้นนอกที่ไม่มี sector แต่ข่าวหุ้นนอก
        # ทั้งหมดเป็น company_news = realtime ซึ่ง R6.12 จำกัดไว้แค่ L1-L2 ทำให้ L4 ไม่เคย
        # ทำงานเลยกับหุ้นนอก — เปิดให้ L4 ทำงานในโหมด realtime ได้ด้วย แต่เฉพาะหุ้นต้นทาง (e)
        # ที่ไม่มี sector (หุ้นนอก) เท่านั้น หุ้นไทยยังใช้ L3 ตามเดิม ไม่เปิด L4 เพิ่มให้
        # (คงเจตนาเดิมของ R6.12 ที่ข่าวด่วนหุ้นไทยควรถึงแค่คนถือตรง/watchlist)
        for e in entities:
            if max_level < 4 and not (mode == "realtime" and not sector_of(e)):
                continue
            for r in (extra_related or {}).get(e, ()):
                if r in holds:
                    hits.append({
                        "level": "L4_RELATED", "entity": r, "rule": "R6.4",
                        "value": holds[r] or 0.0,
                        "th": f"ถือ {r} ซึ่งถูกกล่าวถึงในบทความเดียวกับ {e} บ่อยครั้ง (เชื่อมโยงทางอ้อม)",
                        "en": f"holds {r}, frequently co-mentioned with {e} (indirect link)",
                        "label": labels.get(r, ""), "why": "",
                    })

        # ---- L5 asset class เดียวกัน (R6.5) — ข่าวภาพรวมรายกลุ่ม ----
        if max_level >= 4 and not entities and asset_classes:
            mix = c["asset_mix"]
            share = 1.0 if "*" in asset_classes else sum(mix.get(a, 0.0) for a in asset_classes)
            if share > 0:
                names = "*" if "*" in asset_classes else "/".join(sorted(asset_classes))
                hit = {
                    "level": "L5_ASSET", "entity": names, "rule": "R6.5",
                    "value": share * (c["portfolio_value"] or 0.0),
                    "th": f"พอร์ตมีสินทรัพย์ประเภทเดียวกับบทความ {share:.0%}",
                    "en": f"{share:.0%} of the portfolio is in the same asset class",
                    "label": "", "why": "",
                }
                if asset_classes == {"FUND_ROBO"}:            # GAP-19
                    hit["weight"] = FUND_ROBO_REPORT_WEIGHT
                hits.append(hit)

        # ---- L6 macro (R6.6) — ทุกคน แต่ถ่วงตามความไวของพอร์ต ----
        if max_level >= 4 and not entities and macro:
            for topic in macro:
                sens = _macro_sensitivity(topic, c)
                if sens > 0:
                    hits.append({
                        "level": "L6_MACRO", "entity": topic, "rule": "R6.6",
                        "value": sens * (c["portfolio_value"] or 0.0),
                        "th": f"พอร์ตไวต่อประเด็น{topic} {sens:.0%}",
                        "en": f"portfolio is {sens:.0%} sensitive to {topic}",
                        "label": "", "why": "",
                    })

        if not hits:
            continue

        # R6.x — ลูกค้าเข้าหลายระดับ ใช้ระดับสูงสุดเป็นฐาน + โบนัสถ้าแตะหลายจุด
        best = max(hits, key=lambda h: (h.get("weight", LEVEL_WEIGHT[h["level"]]), h["value"]))
        base = best.get("weight", LEVEL_WEIGHT[best["level"]])
        value_factor = 1 + _log_scale(best["value"])
        rec_factor, rec_days = _recency_factor(last.get(best["entity"]), ref)
        bonus = 1 + MULTI_HIT_BONUS * (len(hits) - 1)
        score = base * value_factor * importance_factor * urgency_factor * rec_factor * bonus

        stats["hit"] += 1
        if score < threshold:                                    # R6.14
            stats["below_threshold"] += 1
            continue
        stats["by_level"][best["level"]] = stats["by_level"].get(best["level"], 0) + 1

        cov = coverage_of(best["entity"]) or {}
        out.append({
            "article_id": article["article_id"], "customer_key": c["customer_key"],
            "rm_id": c["rm_id"], "persona": c["persona"], "level": best["level"],
            "matched_entity": best["entity"], "score": round(score, 2),
            "reason_th": best["th"], "reason_en": best["en"],
            "instrument_label": best["label"],
            "holding_value": best["value"],
            "evidence": db.jdump({
                "hits": [{k: h[k] for k in ("level", "entity", "rule", "th", "en", "label", "why")}
                         for h in hits],
                "factors": {
                    "base": base, "value_factor": round(value_factor, 3),
                    "importance": importance, "importance_factor": round(importance_factor, 3),
                    "urgency": urgency, "urgency_factor": urgency_factor,
                    "recency_factor": rec_factor, "recency_days": rec_days,
                    "multi_hit_bonus": round(bonus, 3), "n_hits": len(hits),
                },
                "customer": {
                    "persona": c["persona"], "tier": c["portfolio_tier"],
                    "portfolio_value": c["portfolio_value"],
                    "trade_frequency": c["trade_frequency"],
                    "unrealized_state": c["unrealized_state"],
                    "n_holdings": c["n_holdings"],
                },
                "coverage": cov,
            }),
        })

    # R6.15 — ไม่ cap แต่เรียงจากคะแนนสูงไปต่ำ
    out.sort(key=lambda m: -m["score"])
    return out, stats


def _macro_sensitivity(topic: str, c: dict) -> float:
    rule = MACRO_SENSITIVITY.get(topic)
    if not rule:
        return 0.0
    if rule.get("all"):
        return 1.0
    share = 0.0
    for a in rule.get("asset", ()):
        share += c["asset_mix"].get(a, 0.0)
    for s in rule.get("sector", ()):
        share += c["sector_exposure"].get(s, 0.0)
    return min(1.0, share)


# ==========================================================================

def run_for_articles(con, article_ids: list[str] | None = None, *,
                     threshold: float | None = None, only_unmatched: bool = False) -> dict:
    """จับคู่บทความ (default = ทุกชิ้นที่ยังไม่เคยจับ) แล้วเก็บผลลง matches"""
    from .ingest_customers import load_customers
    from .verify import regrade

    # GAP-21 — ไม่มีแถวไหนควรค้างไม่มีเกรด คนเปิดดูต้องเห็นครบทุกชิ้น
    regrade(con, only_missing=True)

    # R6.14 — เกณฑ์คะแนนเป็นค่าคงที่ของระบบ (tables.SCORE_THRESHOLD)
    # ยังส่ง threshold เข้ามาเองได้จาก CLI ตอนทดลอง แต่หน้าเว็บไม่มีปุ่มให้ปรับ
    if threshold is None:
        threshold = SCORE_THRESHOLD
    customers = load_customers(con)
    # C2 — seed จาก spec (คลี่เป็นรหัสกลางแล้ว) รวมกับที่ระบบเรียนเองจาก co-mention >= 3 ครั้ง
    extra = seed_related(con)
    for a, bs in learned_related(con).items():
        extra.setdefault(a, set()).update(bs)
    now = dt.datetime.now().isoformat(timespec="seconds")

    where = ["role = 'content'"]                                  # A-23 reference ไม่ส่งใคร
    where.append("NOT (record_type='article' AND subcategory IN ('morning-brief','evening-brief'))")
    params: list = []
    if article_ids:
        where.append(f"article_id IN ({','.join('?' * len(article_ids))})")
        params += article_ids
    if only_unmatched:
        where.append("matched_at IS NULL")
    sql = f"SELECT * FROM articles WHERE {' AND '.join(where)} ORDER BY trigger_at DESC"

    total, arts = 0, 0
    graded: dict[str, int] = {}
    for row in list(con.execute(sql, params)):
        art = dict(row)
        # GAP-21 — ไม่มีประตูให้คนอนุมัติแล้ว ทุกบทความเข้าสู่การจับคู่ทันที
        # เกรดจากตัวตรวจอัตโนมัติเก็บไว้ให้คนดูย้อนหลัง ไม่ได้ใช้กั้น
        g = art.get("auto_grade") or "unknown"
        graded[g] = graded.get(g, 0) + 1
        matches, stats = match_article(art, customers, threshold=threshold,
                                       extra_related=extra)
        with con:
            con.execute("DELETE FROM matches WHERE article_id=?", (art["article_id"],))
            if matches:
                con.executemany(
                    """INSERT INTO matches(article_id,customer_key,rm_id,persona,level,
                         matched_entity,score,reason_th,reason_en,evidence,instrument_label,
                         holding_value,computed_at)
                       VALUES(:article_id,:customer_key,:rm_id,:persona,:level,:matched_entity,
                              :score,:reason_th,:reason_en,:evidence,:instrument_label,
                              :holding_value,:now)""",
                    [{**m, "now": now} for m in matches])
            con.execute("UPDATE articles SET matched_at=?, n_matches=? WHERE article_id=?",
                        (now, len(matches), art["article_id"]))
        total += len(matches)
        arts += 1

    with con:
        db.set_setting(con, "matched_at", now)
    return {"articles_matched": arts, "matches": total, "threshold": threshold,
            "by_grade": graded, "at": now}
