# -*- coding: utf-8 -*-
"""ประกอบและส่งอีเมล "เรื่องที่ควรโทรวันนี้" ให้ RM รายคน

ใครใช้
------
หัวหน้าทีมเป็นคนกดส่ง หลังจากอัปโหลดพอร์ต/ดึงข่าวของวันแล้ว RM แต่ละคนได้อีเมล
ของบุ๊กตัวเอง เรียงตามหุ้น (ไม่ใช่ตามรายชื่อลูกค้า) เพราะโทรทีละหุ้นได้ประเด็นเดียว
คุยได้หลายคน — เรียงตามคนต้องเปลี่ยนเรื่องพูดทุกสาย

ส่งผ่าน Outlook ไม่ใช่ SMTP
--------------------------
ใช้ Outlook (Classic engine) ที่ผู้ใช้ล็อกอินอยู่แล้วผ่าน COM จึงไม่ต้องมีรหัสผ่าน
อยู่ในระบบเลย ไม่ต้องขอ SMTP จากฝ่าย IT และอีเมลที่ส่งออกไปโผล่ใน Sent Items
ของหัวหน้าเองตามปกติ — แพตเทิร์นเดียวกับโปรเจกต์ KIKO-graph ที่ใช้งานจริงแล้ว

จุดที่ห้ามเปลี่ยน (เหตุผลมาจากของที่พังมาก่อน)
  * ต้อง GetActiveObject ไม่ใช่ New-Object — ตัวที่ COM สร้างเองมักข้ามขั้นตอน login
    แล้ว .Send() เงียบ ๆ โดยไม่มีอะไรออกไปจริง
  * ข้อความทั้งหมดส่งผ่านไฟล์ JSON + environment variable ไม่เคยถูกแทรกเป็นซอร์ส
    ของสคริปต์ PowerShell — ชื่อ/หัวข้อที่มีอักขระพิเศษจึงแทรกคำสั่งไม่ได้
  * Get-Content ต้องระบุ -Encoding UTF8 — Windows PowerShell 5.1 อ่านเป็น cp874
    โดยปริยาย ภาษาไทยจะเพี้ยนทั้งฉบับ
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time

from . import db


_PS_BIN = shutil.which("powershell") or shutil.which("pwsh")
_CFG_ENV = "MATCHPORT_MAIL_CFG"

# รอ Outlook ให้พร้อม แล้วส่งฉบับเดียวพร้อมไฟล์แนบทุกไฟล์
#
# ตอนเปิด Outlook ใหม่ ๆ ตัว COM object ยังไม่โผล่ใน ROT ทันทีแม้หน้าต่างจะขึ้นแล้ว
# และถ้ามี MFA ต้องรอคนกดด้วย — จึง poll ยาวถึง ~100 วินาที ก่อนยอมแพ้
# หลังได้ object มาแล้วยังต้องแตะ .Session อีกชั้น เพราะบางครั้ง GetActiveObject
# สำเร็จตั้งแต่ profile ยังไม่พร้อม แล้วไปพังตอน .Send() ซึ่งสายเกินจะย้อน
_SEND_PS = r"""
$ErrorActionPreference = 'Stop'
$cfg = Get-Content -Raw -Encoding UTF8 -LiteralPath $env:MATCHPORT_MAIL_CFG | ConvertFrom-Json
function Get-Outlook {
    try { return [Runtime.InteropServices.Marshal]::GetActiveObject('Outlook.Application') }
    catch { return $null }
}
function Test-Ready($o) {
    if ($null -eq $o) { return $false }
    try { $null = $o.Session.CurrentUser; return $true } catch { return $false }
}
$outlook = Get-Outlook
if (-not (Test-Ready $outlook)) {
    try { Start-Process 'outlook' } catch {}
    for ($i = 0; $i -lt 50; $i++) {      # ~100 วินาที เผื่อเปิด + login/MFA + ลง profile
        Start-Sleep -Seconds 2
        $outlook = Get-Outlook
        if (Test-Ready $outlook) { break }
    }
}
if (-not (Test-Ready $outlook)) { Write-Output 'NOOUTLOOK'; exit 1 }
try {
    $mail = $outlook.CreateItem(0)   # 0 = olMailItem
    $mail.To = $cfg.to
    $mail.Subject = $cfg.subject
    $mail.HTMLBody = $cfg.html
    foreach ($a in $cfg.attachments) {
        if (Test-Path -LiteralPath $a) { $mail.Attachments.Add($a) | Out-Null }
    }
    $mail.Send()
    Write-Output 'SENT'
} catch {
    Write-Output "ERR|$($_.Exception.Message)"
    exit 1
}
"""


# --------------------------------------------------------------------------
# ค่าตั้งและสถานะ
# --------------------------------------------------------------------------

def config(con: sqlite3.Connection) -> dict:
    """ผู้รับเป็นรายชื่ออีเมลอิสระ ไม่ผูกกับ RM

    เดิมผูกอีเมลกับ RM ทีละคน แต่ของจริงคนที่ควรได้รับไม่ได้มีแค่ RM — หัวหน้าสายงาน
    หรือทีมซัพพอร์ตก็อยู่ในลิสต์ได้ และ RM คนหนึ่งอาจมีหลายอีเมล การบังคับให้จับคู่
    หนึ่งต่อหนึ่งจึงเป็นข้อจำกัดที่ไม่มีอยู่จริง
    """
    return {"recipients": db.get_setting(con, "mail_recipients", []) or [],
            "sent_at": db.get_setting(con, "mail_sent_at", None)}


def health() -> dict:
    """เครื่องนี้ส่งได้ไหม และ Outlook เปิดอยู่หรือยัง

    ตรวจด้วย GetActiveObject อย่างเดียว ตั้งใจไม่ใช้ New-Object — ไม่งั้นทุกครั้งที่หน้าจอ
    ถามสถานะจะทิ้ง process Outlook ซ่อนไว้เพิ่มอีกตัว
    """
    if os.name != "nt" or not _PS_BIN:
        return {"available": False, "running": False,
                "blocked": "ส่งอัตโนมัติได้เฉพาะบน Windows ที่มี Outlook เท่านั้น"}
    try:
        p = subprocess.run(
            [_PS_BIN, "-NoProfile", "-NonInteractive", "-Command",
             "try { $o = [Runtime.InteropServices.Marshal]::GetActiveObject("
             "'Outlook.Application'); Write-Output $o.Version } catch { Write-Output 'NO' }"],
            capture_output=True, text=True, encoding="utf-8", timeout=20)
        ver = (p.stdout or "").strip()
    except Exception:                                               # noqa: BLE001
        return {"available": True, "running": False, "blocked": None}
    running = ver not in ("", "NO")
    return {"available": True, "running": running,
            "version": ver if running else None, "blocked": None}


# --------------------------------------------------------------------------
# ประกอบเนื้อหา
# --------------------------------------------------------------------------

def _mb(v: float) -> str:
    return f"{v / 1e6:,.1f} ลบ." if v >= 1e5 else f"{v:,.0f} บาท"


def _clip(s: str, n: int) -> str:
    """ตัดที่ช่องว่างใกล้ ๆ ไม่ตัดกลางคำ — ของเต็มอยู่ในลิงก์ข่าวและไฟล์ .csv"""
    s = (s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > n * 0.7 else cut).rstrip() + "…"


def dividend_map(con: sqlite3.Connection) -> dict[str, dict]:
    """ปันผลของเดือนล่าสุด คีย์ด้วยหุ้น — แปะในอีเมลเมื่อหุ้นตัวนั้นมี XD"""
    return {r["entity"]: dict(r) for r in con.execute("""
        SELECT entity, xd_date, pay_date, yield_interim, yield_forecast, remark
        FROM dividends
        WHERE report_month = (SELECT MAX(report_month) FROM dividends)""")}


# --------------------------------------------------------------------------
# ไฟล์แนบรายคน — ของละเอียดอยู่ในไฟล์ ส่วนอีเมลเป็นสรุป
# --------------------------------------------------------------------------
#
# หน้าจอตัดเหลือ 4 คนต่อหุ้นเพราะพื้นที่จำกัด แต่ไฟล์ไม่มีข้อจำกัดนั้น
# จึงคิวรีเองทั้งหมดแทนการเรียก endpoint เดิม — RM ต้องได้ทุกคนที่ควรโทรจริง ๆ
# ไม่ใช่แค่สี่คนแรก ไม่งั้นคนที่ 5 เป็นต้นไปหายไปเงียบ ๆ ทั้งที่ถืออยู่

_DIR_TH = {"up": "บวก", "down": "ลบ", "mixed": "ผสม", "flat": "ทรงตัว", "unknown": "ไม่ชัด"}


def detail_rows(con: sqlite3.Connection, rm_id: str, day: str | None,
                divs: dict[str, dict]) -> list[dict]:
    """หนึ่งแถวต่อ (หุ้น, ลูกค้า) ครบทุกคน เรียงตามเงินของหุ้นแล้วเงินของลูกค้า"""
    from . import briefing

    where, args = "", [rm_id]
    if day:
        where = "AND substr(a.trigger_at,1,10)=?"
        args.append(day)

    # MAX(holding_value) ต่อคู่ — ข่าวหลายชิ้นชี้หุ้นตัวเดียวกันได้ ถ้ารวมตรง ๆ เงินจะบวมเป็นเท่าตัว
    #
    # reason_th ยกมาจากแถวที่คะแนนสูงสุดของคู่นั้น (rn=1) ไม่ใช่แถวไหนก็ได้ — เป็นประโยคที่
    # บอกว่า "ลูกค้าคนนี้เกี่ยวกับข่าวนี้เพราะอะไร" ซึ่งต่างกันรายคน ("ถือ DCC มูลค่า 60,900" กับ
    # "เคยเทรดแต่ตอนนี้ไม่ถือ" คนละบทสนทนากันคนละแบบ) ระดับการจับคู่อย่างเดียวบอกไม่ได้
    pairs = [dict(r) for r in con.execute(f"""
        WITH ranked AS (
            SELECT m.matched_entity entity, m.customer_key, m.article_id,
                   COALESCE(m.holding_value,0) holding_value, m.score, m.level,
                   m.reason_th, m.instrument_label,
                   ROW_NUMBER() OVER (PARTITION BY m.matched_entity, m.customer_key
                                      ORDER BY m.score DESC) rn
            FROM matches m JOIN articles a USING(article_id)
            WHERE m.rm_id=? {where}
        )
        SELECT r.entity, r.customer_key,
               MAX(r.holding_value) holding_value,
               MAX(r.score) score, MIN(r.level) level,
               GROUP_CONCAT(DISTINCT r.article_id) article_ids,
               MAX(CASE WHEN r.rn=1 THEN r.reason_th END)        match_reason,
               MAX(CASE WHEN r.rn=1 THEN r.instrument_label END) instrument_label,
               cu.portfolio_value, cu.persona, cu.portfolio_tier
        FROM ranked r
        JOIN customers cu ON cu.customer_key=r.customer_key
        GROUP BY r.entity, r.customer_key""", args)]
    if not pairs:
        return []

    by_entity: dict[str, dict] = {}
    for p in pairs:
        e = by_entity.setdefault(p["entity"], {"value": 0.0, "customers": 0, "arts": set()})
        e["value"] += p["holding_value"]
        e["customers"] += 1
        e["arts"].update((p["article_ids"] or "").split(","))

    # วิเคราะห์บทความชิ้นละครั้งแล้วแจกใช้ซ้ำ — บทความเดียวถูกอ้างถึงได้หลายสิบแถว
    need = {a for e in by_entity.values() for a in e["arts"] if a}
    art_view: dict[str, dict] = {}
    if need:
        from . import news

        qs = ",".join("?" * len(need))
        for row in con.execute(f"SELECT * FROM articles WHERE article_id IN ({qs})", tuple(need)):
            art = dict(row)
            v = briefing.analyse(art)
            sigs = v.get("signals") or []
            # สรุปรายวันชิ้นเดียวมีคำแนะนำของหุ้นหลายสิบตัว (ของจริงเจอ 39 สัญญาณ)
            # ถ้าหยิบสัญญาณตัวแรกมาใช้กับทุกหุ้น ADVANC จะได้คำแนะนำของ PTTEP ไปแสดง
            # ซึ่งผิดคนละบริษัทและ RM เอาไปคุยกับลูกค้าไม่ได้ จึงต้องแยกเก็บรายตัว
            by_ent: dict[str, dict] = {}
            for s in sigs:
                e = (s.get("entity") or "").strip()
                if e and e not in by_ent:
                    by_ent[e] = s
            sig = sigs[0] if sigs else None
            # หุ้นเด่นประจำวันที่บทความชี้เอง (GAP-23) — ไม่ใช่ผลจากการตีความของเรา
            picks = {k for k, x in (db.jload(art.get("evidence"), {}) or {}).items()
                     if isinstance(x, dict) and x.get("rule") == "GAP-23"}
            art_view[art["article_id"]] = {
                "sig_by_entity": by_ent, "top_picks": picks,
                "title": art["title"], "at": art["trigger_at"],
                # url ที่เก็บไว้เป็น path ที่ตัดโดเมนออกแล้ว ต่อเองจะได้ 404
                "url": news.article_url(art.get("url") or ""),
                "overall": v["overall"], "why": sig["th"] if sig else "",
                "invx_view": v.get("invx_view") or "",
                "invx_points": v.get("invx_points") or [],
                # AI-01/02 — สิ่งที่ Claude อ่านเนื้อข่าวเต็มแล้วสรุปเอง พร้อมประโยคที่ยกมา
                # ถ้าอ่านแล้วสรุปทิศทางไม่ได้ ai_reason_th บอกว่าเพราะอะไร
                "ai_direction": art.get("ai_direction") or "",
                "ai_reason": art.get("ai_reason_th") or "",
                "ai_quote": art.get("ai_direction_quote") or "",
                "content_type": art.get("content_type") or "",
            }

    for e in by_entity.values():
        arts = sorted((art_view[a] for a in e["arts"] if a in art_view),
                      key=lambda x: x["at"], reverse=True)
        # ข่าวที่ยกมาเป็นตัวเปิดเรื่อง เลือกชิ้นที่บอกทิศทางได้ก่อน ไม่ใช่ชิ้นล่าสุดเสมอ
        e["lead"] = next((a for a in arts if a["overall"] not in ("unknown", "flat")),
                         arts[0] if arts else None)
        # เก็บข่าวทุกชิ้นไว้ด้วย — หุ้นเด่นกับสัญญาณรายตัวอาจอยู่คนละชิ้นกับ lead
        e["arts_view"] = arts

    order = sorted(by_entity, key=lambda k: -by_entity[k]["value"])
    rank = {k: i + 1 for i, k in enumerate(order)}
    pairs.sort(key=lambda p: (rank[p["entity"]], -p["holding_value"]))

    out = []
    for p in pairs:
        e = by_entity[p["entity"]]
        lead = e.get("lead") or {}
        d = divs.get(p["entity"])
        # หาสัญญาณของ "หุ้นตัวนี้" ในบทความ ไม่ใช่ตัวแรกของบทความ
        # รหัสในสัญญาณเป็นตัวย่อล้วน (PTTEP) ส่วนของเราอาจมี MIC ต่อท้าย (NVDA:xnas)
        root = p["entity"].split(":", 1)[0]
        arts_v = e.get("arts_view") or []
        mine_sig = None
        for a in [lead, *arts_v]:                 # lead ก่อน แล้วค่อยไล่ข่าวชิ้นอื่นของวันเดียวกัน
            b = (a or {}).get("sig_by_entity") or {}
            mine_sig = b.get(p["entity"]) or b.get(root)
            if mine_sig:
                break
        # ไม่มีสัญญาณของตัวเองก็ปล่อยว่าง ดีกว่ายืมของหุ้นอื่นมาใส่
        why = mine_sig["th"] if mine_sig else (
            lead.get("why", "") if not (lead.get("sig_by_entity") or {}) else "")
        out.append({
            "rank": rank[p["entity"]], "entity": p["entity"],
            "customer_key": p["customer_key"],
            "holding_value": round(p["holding_value"], 2),
            "level": p["level"], "score": round(p["score"] or 0, 1),
            "entity_value": round(e["value"], 2), "entity_customers": e["customers"],
            # ดูข่าวทุกชิ้นของวันนั้น — ชิ้นที่ประกาศหุ้นเด่นมักไม่ใช่ชิ้นที่ถูกเลือกเป็น lead
            "top_pick": any(p["entity"] in (a.get("top_picks") or set())
                            or root in (a.get("top_picks") or set()) for a in arts_v),
            # โผล่แค่ในสรุปรายวัน = พาดหัวเป็นของภาพรวมตลาด ไม่ได้พูดถึงหุ้นตัวนี้
            "coverage": "own" if any(a.get("content_type") != "daily_brief"
                                     for a in arts_v) else "brief",
            "direction": _DIR_TH.get(lead.get("overall") or "unknown", ""),
            "article_title": lead.get("title", ""), "article_why": why,
            "article_url": lead.get("url", ""),
            "invx_view": lead.get("invx_view", ""),
            "invx_points": lead.get("invx_points", []),
            # คำตัดสินของ AI แยกจาก direction รวม — direction ผสมสัญญาณจากกฎเข้าไปด้วย
            # แต่ RM ควรเห็นได้ว่าอันไหนคือสิ่งที่ AI อ่านเนื้อข่าวแล้วสรุปเอง
            "ai_direction": lead.get("ai_direction", ""),
            "ai_reason": lead.get("ai_reason", ""),
            "ai_quote": lead.get("ai_quote", ""),
            "article_at": (lead.get("at") or "")[:16].replace("T", " "),
            "match_reason": p.get("match_reason") or "",
            "instrument_label": p.get("instrument_label") or "",
            "xd_date": d["xd_date"] if d else "", "pay_date": d["pay_date"] if d else "",
            "div_yield": d["yield_interim"] if d else "",
            "div_baht": round(p["holding_value"] * d["yield_interim"] / 100, 2) if d else "",
            "div_status": ("คาดการณ์" if d["remark"] == "Estimated" else "ประกาศแล้ว") if d else "",
            "div_forecast": d["yield_forecast"] if d else "",
            "portfolio_value": round(p["portfolio_value"] or 0, 2),
            "persona": p["persona"], "portfolio_tier": p["portfolio_tier"],
        })
    return out


def freshness(con: sqlite3.Connection, day: str) -> dict:
    """ข้อมูลชุดนี้เป็นของวันไหน และเป็นของวันนี้จริงหรือเปล่า

    ทำไมต้องมี
    ---------
    `day` มาจากวันล่าสุดที่มีข่าวในฐาน ไม่ใช่วันนี้ ถ้าเช้านี้ยังไม่มีใครกดดึงข่าว
    ค่านี้จะเป็นเมื่อวาน แล้วอีเมลที่ส่งออกไปคือคิวโทรของเมื่อวานทั้งฉบับ
    โดยที่หน้าจอไม่ได้ผิดอะไรเลย — ต้องมีคนบอกก่อนกด ไม่ใช่รู้ตัวหลัง RM โทรไปแล้ว
    """
    today = dt.date.today().isoformat()
    ingested = db.get_setting(con, "news_ingested_at", None)
    n_today = con.execute(
        "SELECT COUNT(*) FROM articles WHERE role='content' AND substr(trigger_at,1,10)=?",
        (today,)).fetchone()[0]
    return {
        "day": day, "today": today, "is_today": day == today,
        "news_ingested_at": ingested,
        "ingested_today": bool(ingested) and str(ingested)[:10] == today,
        "articles_today": n_today,
    }


def stale_warning(fresh: dict) -> str | None:
    """ประโยคเตือนที่ต้องโชว์ทั้งบนหน้าจอและในอีเมล — None ถ้าเป็นของวันนี้จริง"""
    if fresh["is_today"]:
        return None
    return (f"ข้อมูลชุดนี้เป็นของวันที่ {fresh['day']} ไม่ใช่วันนี้ ({fresh['today']}) "
            f"— วันนี้ยังไม่มีข่าวเข้าระบบ กดปุ่มดึงข่าวก่อนถ้าต้องการคิวโทรของวันนี้")


# คำตัดสินของ AI — คำไทยพร้อมสี ต้องอ่านออกใน 1 วินาทีว่าให้ไปทางไหน
_AI_DIR = {
    "up": ("บวก", "#137333"), "down": ("ลบ", "#c5221f"),
    "mixed": ("สองทาง", "#9a6700"), "position_dependent": ("ขึ้นกับว่าถืออะไร", "#9a6700"),
    "unknown": ("ยังไม่ฟันธง", "#777"),
}


def _ai_box(f: dict, _h) -> str:
    """กล่อง "AI อ่านแล้วว่า" — ว่างถ้ายังไม่ได้ให้ AI อ่านข่าวชิ้นนี้

    แยกจากกล่องมุมมองของ InnovestX ตั้งใจ: อันนั้นนักวิเคราะห์ของบริษัทเขียนเอง
    อันนี้เครื่องอ่านเนื้อข่าวแล้วสรุป ต้องไม่ถูกอ่านสลับกันเพราะน้ำหนักไม่เท่ากัน
    ตอนที่ AI สรุปทิศทางไม่ได้ก็ยังแสดง เพราะ "อ่านแล้วไม่ฟันธง" ต่างจาก "ยังไม่ได้อ่าน"
    """
    d = f.get("ai_direction") or ""
    if not d:
        return ""
    label, color = _AI_DIR.get(d, (d, "#777"))
    parts = [f"<div class='ai'><b>AI อ่านข่าวเต็มแล้วสรุปว่า</b>"
             f"<span class='aidir' style='color:{color}'>{_h.escape(label)}</span>"]
    if f.get("ai_reason"):
        parts.append(f" — {_h.escape(_clip(f['ai_reason'], 300))}")
    if f.get("ai_quote"):
        # ประโยคที่ยกมาคือหลักฐาน ไม่ใช่การตีความ — RM เอาไปอ้างกับลูกค้าได้ตรง ๆ
        parts.append(f"<div style='margin-top:4px'>"
                     f"<q>{_h.escape(_clip(f['ai_quote'], 300))}</q></div>")
    return "".join(parts) + "</div>"


_AC_TH = {
    "EQUITY_TH": "หุ้นไทย", "EQUITY_OFFSHORE": "หุ้นต่างประเทศ", "FUND_DIY": "กองทุน (เลือกเอง)",
    "FUND_ROBO": "กองทุน (จัดให้)", "BOND": "ตราสารหนี้", "DERIVATIVES": "อนุพันธ์",
    "CRYPTO": "คริปโต", "STRUCTURED": "ตราสารโครงสร้าง", "CASH": "เงินสด",
}
_DIRECTION_TH = {"INCREASE": "ซื้อเพิ่ม", "DECREASE": "ขายออก", "NEUTRAL": "ไม่เปลี่ยนสถานะ"}


def render_report(rm_id: str, day: str, rows: list[dict], warning: str | None = None,
                  profiles: dict[str, dict] | None = None) -> bytes:
    """ไฟล์ HTML หน้าตาเหมือนหน้าจอในเว็บ — เปิดอ่านได้เลยจากอีเมล

    ทำไมต้องมีทั้ง HTML และ CSV
    ---------------------------
    CSV ไว้ทำงานต่อ (กรอง เรียง ทำ pivot ใน Excel) แต่เปิดมาเจอตัวเลขดิบ 300 แถว
    อ่านไม่ออกว่าควรโทรใครก่อน ไฟล์นี้จึงจัดให้อ่านแล้วรู้ลำดับทันที เหมือนที่เห็นในเว็บ
    ทั้งสองไฟล์มาจากข้อมูลชุดเดียวกัน ไม่ใช่คนละชุดที่ต้องมาเทียบกัน

    ฝัง CSS ไว้ในไฟล์ทั้งหมด ไม่มีลิงก์ออกนอก — เปิดจากไฟล์แนบใน Outlook ได้เลย
    โดยไม่ต้องต่อเน็ตและไม่มีอะไรถูกโหลดจากภายนอก

    หน้าลูกค้าอยู่ในไฟล์เดียวกัน
    ---------------------------
    กดชื่อลูกค้าแล้วเปิดหน้าของคนนั้นได้เหมือนในเว็บ ทำด้วย :target ของ CSS ล้วน
    ไม่ใช้ JavaScript เลย เพราะไฟล์แนบที่มีสคริปต์มักโดนนโยบายความปลอดภัยขององค์กร
    บล็อกหรือเตือน ส่วน :target รองรับทุกเบราว์เซอร์มาสิบกว่าปีแล้ว
    """
    import html as _h

    by_entity: dict[str, list[dict]] = {}
    by_customer: dict[str, list[dict]] = {}
    for r in rows:
        by_entity.setdefault(r["entity"], []).append(r)
        by_customer.setdefault(r["customer_key"], []).append(r)
    total = sum(v[0]["entity_value"] for v in by_entity.values())

    def anchor(key: str) -> str:
        """id ที่ปลอดภัยสำหรับ URL — รหัสลูกค้าเป็น A-Z0-9 อยู่แล้ว แต่กันไว้ก่อน"""
        return "c-" + re.sub(r"[^A-Za-z0-9_-]", "_", key)

    tone = {"บวก": "#137333", "ลบ": "#c5221f", "ผสม": "#9a6700"}
    top_value = max((v[0]["entity_value"] for v in by_entity.values()), default=1) or 1

    out = [
        '<!doctype html><html lang="th"><head><meta charset="utf-8">',
        f"<title>MatchPort {_h.escape(rm_id)} {day}</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#1a1a1a;"
        "background:#fff;margin:0;padding:28px 20px;line-height:1.5}",
        ".wrap{max-width:900px;margin:0 auto}",
        "h1{font-size:22px;margin:0 0 2px}",
        ".sub{color:#666;font-size:14px;margin:0 0 20px}",
        ".fig{font-size:30px;font-weight:600;letter-spacing:-.5px}",
        ".figlab{color:#666;font-size:13px}",
        ".stats{display:flex;flex-wrap:wrap;gap:34px;border-bottom:1px solid #e5e5e5;"
        "padding-bottom:18px;margin-bottom:8px}",
        ".item{border-bottom:1px solid #ececec;padding:16px 0}",
        ".head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}",
        ".rank{color:#999;font-size:13px;min-width:22px}",
        ".tic{font-weight:600;font-size:16px}",
        ".money{margin-left:auto;font-weight:600;font-size:15px}",
        ".bar{height:4px;background:#f0f0f0;border-radius:2px;margin:7px 0 9px;overflow:hidden}",
        ".bar>i{display:block;height:4px;background:#3b6fd4}",
        ".news{font-size:13px;color:#333;margin:2px 0}",
        ".news a{color:#1a4fa0;text-decoration:none}",
        ".news a:hover{text-decoration:underline}",
        ".stale{background:#fff4e5;border:1px solid #e0a33a;color:#7a4c00;padding:11px 14px;"
        "border-radius:4px;font-size:13px;margin-bottom:16px}",
        ".why{font-size:12px;color:#666}",
        ".div{font-size:12px;color:#666;margin-top:3px}",
        # ความเห็นของบ้านเราเองต้องเด่นกว่าเนื้อข่าว — ข่าวหาอ่านที่ไหนก็ได้ อันนี้หาไม่ได้
        ".view{margin-top:8px;background:#f4f7fd;border-left:3px solid #3b6fd4;"
        "padding:9px 12px;font-size:13px;color:#22324d;line-height:1.55}",
        ".view b{color:#1a4fa0;font-size:11px;letter-spacing:.3px;display:block;"
        "margin-bottom:3px;text-transform:uppercase}",
        ".view ul{margin:0;padding-left:18px}",
        ".view li{margin:3px 0}",
        ".vmore{color:#6b7c99;font-size:12px;margin-top:4px}",
        ".badge{font-size:11px;font-weight:600;padding:1px 7px;border-radius:9px;"
        "background:#f2f2f2}",
        "table{border-collapse:collapse;width:100%;margin-top:9px;font-size:13px}",
        "th{text-align:left;color:#666;font-weight:500;font-size:12px;padding:4px 8px;"
        "border-bottom:1px solid #e5e5e5}",
        "td{padding:4px 8px;border-bottom:1px solid #f5f5f5}",
        ".r{text-align:right}",
        ".note{margin-top:26px;background:#fafafa;border:1px solid #e0e0e0;padding:13px 15px;"
        "font-size:13px;border-radius:4px}",
        "a.cust{color:#1a4fa0;text-decoration:none;font-weight:600}",
        "a.cust:hover{text-decoration:underline}",
        # หน้าลูกค้าซ่อนไว้จนกว่าจะถูกกด — กดแล้วเบราว์เซอร์เลื่อนมาที่ส่วนนั้นให้เอง
        # ได้ความรู้สึกเหมือนเปลี่ยนหน้า และปุ่ม back ของเบราว์เซอร์ย้อนได้ตามปกติ
        # ตั้งใจไม่ใช้ :has() ซ่อนรายการหลัก เพราะเบราว์เซอร์รุ่นเก่าที่ Outlook เรียกใช้
        # อาจไม่รองรับ แล้วจะกลายเป็นหน้าว่างทั้งหน้า — แบบนี้แย่ที่สุดคือรายการยังอยู่ข้างล่าง
        ".person{display:none;border-top:2px solid #1a4fa0;padding-top:16px;margin-top:8px}",
        ".person:target{display:block}",
        ".back{display:inline-block;margin-bottom:14px;color:#1a4fa0;text-decoration:none;"
        "font-size:13px}",
        ".back:hover{text-decoration:underline}",
        ".pmeta{color:#666;font-size:13px;margin:0 0 14px}",
        ".pstat{display:flex;flex-wrap:wrap;gap:26px;border-top:1px solid #e5e5e5;"
        "border-bottom:1px solid #e5e5e5;padding:11px 0;margin-bottom:14px}",
        ".pstat b{display:block;font-size:17px;font-weight:600}",
        ".pstat span{color:#777;font-size:12px}",
        "h3{font-size:14px;margin:18px 0 6px}",
        ".mix{margin:0}",
        ".mix div{display:flex;align-items:center;gap:8px;font-size:12px;margin:3px 0}",
        ".mix i{display:block;height:8px;background:#3b6fd4;border-radius:2px;min-width:2px}",
        ".mix u{text-decoration:none;color:#777;min-width:52px;text-align:right}",
        ".mix em{font-style:normal;min-width:150px}",
        ".cols{display:flex;flex-wrap:wrap;gap:28px}",
        ".cols>div{flex:1;min-width:280px}",
        ".buy{color:#137333}",
        ".sell{color:#c5221f}",
        # คำตัดสินของ AI แยกกล่องคนละสีกับ "มุมมองของ InnovestX" — คนละแหล่งกัน
        # อันหนึ่งคนของบริษัทเขียน อีกอันเครื่องอ่านเอง ห้ามให้อ่านสลับกัน
        ".ai{margin-top:8px;background:#f6f4fb;border-left:3px solid #7a5cd0;"
        "padding:9px 12px;font-size:13px;color:#2e2545;line-height:1.55}",
        ".ai b{color:#5b3fa8;font-size:11px;letter-spacing:.3px;display:block;"
        "margin-bottom:3px;text-transform:uppercase}",
        ".ai q{color:#544a6b;font-style:italic}",
        ".aidir{font-weight:700}",
        # หุ้นเด่นประจำวันที่บทความชี้เอง — ป้ายเด่นกว่าป้ายอื่นเพราะเป็นคำแนะนำตรง ๆ
        ".pick{background:#fff1cc;color:#7a5300;border:1px solid #e0a33a;font-size:11px;"
        "font-weight:600;padding:1px 7px;border-radius:9px}",
        "</style></head><body><div class='wrap'><span id='top'></span>",
        f"<h1>เรื่องที่ควรโทร · {_h.escape(rm_id)}</h1>",
        f"<p class='sub'>{day} — เรียงตามเงินที่ข่าวไปแตะ ตัวบนสุดคุยแล้วได้ผลมากสุด</p>",
        # คำเตือนต้องติดไปกับไฟล์ด้วย ไม่ใช่อยู่แค่บนหน้าจอคนส่ง — ไฟล์ถูกส่งต่อได้
        (f"<div class='stale'><b>ข้อมูลไม่ใช่ของวันนี้</b><br>{_h.escape(warning)}</div>"
         if warning else ""),
        "<div class='stats'>",
        f"<div><div class='fig'>{_mb(total)}</div>"
        f"<div class='figlab'>เงินที่ข่าววันนี้แตะ</div></div>",
        f"<div><div class='fig'>{len(by_entity):,}</div>"
        f"<div class='figlab'>ตัวที่ควรโทร</div></div>",
        f"<div><div class='fig'>{len(rows):,}</div>"
        f"<div class='figlab'>รายชื่อที่ต้องคุย</div></div>",
        "</div>",
    ]

    for ent, people in sorted(by_entity.items(), key=lambda kv: -kv[1][0]["entity_value"]):
        f = people[0]
        pct = max(2, round(f["entity_value"] / top_value * 100))
        col = tone.get(f["direction"], "#666")
        out.append(
            f"<div class='item'><div class='head'>"
            f"<span class='rank'>{f['rank']}</span>"
            f"<span class='tic'>{_h.escape(ent)}</span>"
            + ("<span class='pick'>InnovestX Daily Top Pick</span>" if f["top_pick"] else "")
            + ("<span class='badge' style='color:#777'>จากสรุปรายวัน</span>"
               if f["coverage"] == "brief" else "")
            + f"<span class='badge' style='color:{col}'>ข่าว{_h.escape(f['direction'] or '-')}</span>"
            f"<span style='color:#777;font-size:13px'>ลูกค้า {len(people)} คน</span>"
            f"<span class='money'>{_mb(f['entity_value'])}</span></div>"
            f"<div class='bar'><i style='width:{pct}%'></i></div>")
        # หุ้นที่มาจากสรุปรายวันล้วน สลับให้ประโยคของตัวเองขึ้นก่อน พาดหัวลงไปเป็นที่มา
        # ไม่งั้นทั้งลิสต์อ่านเหมือนข่าวเดียวกันซ้ำสิบกว่าครั้ง
        brief = f["coverage"] == "brief"
        title = _h.escape(f["article_title"] or "")
        if f["article_url"]:
            title = f"<a href=\"{_h.escape(f['article_url'])}\">{title}</a>"
        if brief:
            if f["article_why"]:
                out.append(f"<div class='news'>{_h.escape(f['article_why'])}</div>")
            else:
                out.append("<div class='why'>สรุปรายวันเอ่ยถึงตัวนี้ "
                           "แต่ไม่ได้ให้คำแนะนำเจาะจง</div>")
            out.append(f"<div class='why'>จากสรุปรายวัน · {title} · "
                       f"{_h.escape(f['article_at'])}</div>")
        else:
            if f["article_title"]:
                out.append(f"<div class='news'>{title}</div>")
            if f["article_why"]:
                out.append(f"<div class='why'>{_h.escape(f['article_why'])} · "
                           f"{_h.escape(f['article_at'])}</div>")
        out.append(_ai_box(f, _h))
        if f["invx_points"]:
            # ขึ้นเป็นข้อ ๆ ตามที่นักวิเคราะห์แบ่งไว้เอง ไม่ยุบเป็นก้อนเดียว
            items = "".join(f"<li>{_h.escape(_clip(p, 600))}</li>"
                            for p in f["invx_points"][:6])
            more = (f"<div class='vmore'>ยังมีอีก {len(f['invx_points']) - 6} ข้อในข่าวฉบับเต็ม</div>"
                    if len(f["invx_points"]) > 6 else "")
            out.append(f"<div class='view'><b>มุมมองของ InnovestX</b>"
                       f"<ul>{items}</ul>{more}</div>")
        elif f["invx_view"]:
            out.append(f"<div class='view'><b>มุมมองของ InnovestX</b>"
                       f"{_h.escape(_clip(f['invx_view'], 900))}</div>")
        if f["xd_date"]:
            # Estimated ยังไม่ประกาศจริง ต้องอ่านออกว่าเป็นการคาด ไม่ใช่ตัวเลขที่ยืนยันแล้ว
            tag = " (คาดการณ์)" if f["div_status"] == "คาดการณ์" else ""
            out.append(f"<div class='div'>ปันผล XD {_h.escape(str(f['xd_date']))} · "
                       f"จ่าย {_h.escape(str(f['pay_date']))} · "
                       f"{f['div_yield']}% งวดนี้{tag}</div>")

        has_div = bool(f["xd_date"])
        out.append("<table><tr><th>ลูกค้า</th><th>ทำไมคนนี้เกี่ยวกับข่าวนี้</th>"
                   "<th class='r'>ถือ</th>"
                   + ("<th class='r'>ปันผลที่จะได้</th>" if has_div else "")
                   + "<th class='r'>พอร์ตรวม</th><th>กลุ่ม</th></tr>")
        for p in people:
            # เหตุผลรายคนคือสิ่งที่ RM ใช้เปิดประโยคจริง — "ถือ 60,900 บาท" กับ
            # "เคยเทรดแต่ตอนนี้ไม่ถือ" คนละบทสนทนากันคนละแบบ ระดับ L1/L2 บอกไม่ได้
            label = f" · {_h.escape(p['instrument_label'])}" if p.get("instrument_label") else ""
            out.append(
                f"<tr><td>"
                f"<a class='cust' href='#{anchor(p['customer_key'])}'>"
                f"{_h.escape(p['customer_key'])}</a>"
                f"<div style='color:#999;font-size:11px'>{_h.escape(p['level'] or '')}{label}</div>"
                f"</td>"
                f"<td style='color:#444'>{_h.escape(p['match_reason'] or '')}</td>"
                f"<td class='r'>{p['holding_value']:,.0f}</td>"
                + (f"<td class='r'>{p['div_baht']:,.0f}</td>" if has_div else "")
                + f"<td class='r' style='color:#777'>{p['portfolio_value']:,.0f}</td>"
                f"<td style='color:#777'>{_h.escape(p['persona'] or '')}</td></tr>")
        out.append("</table></div>")

    # ---- หน้าของลูกค้าแต่ละคน — กดชื่อจากตารางข้างบนมาที่นี่ ----
    # เรียงตามเงินที่ข่าวไปแตะของคนนั้น เพื่อให้เปิดดูคนใหญ่สุดได้ก่อนถ้าไล่จากล่าง
    order = sorted(by_customer.items(),
                   key=lambda kv: -sum(x["holding_value"] for x in kv[1]))
    for key, mine in order:
        first = mine[0]
        touched = sum(x["holding_value"] for x in mine)
        pv = first["portfolio_value"] or 0
        share = f" · {touched / pv * 100:.0f}% ของพอร์ต" if pv else ""
        out.append(
            f"<div class='person' id='{anchor(key)}'>"
            f"<a class='back' href='#top'>← กลับไปรายการทั้งหมด</a>"
            f"<h2 style='margin:0 0 2px;font-size:19px'>{_h.escape(key)}</h2>"
            f"<p class='pmeta'>{_h.escape(first['persona'] or '')} · "
            f"{_h.escape(first['portfolio_tier'] or '')} · พอร์ตรวม {pv:,.0f} บาท<br>"
            f"ข่าววันนี้แตะเงินของลูกค้ารายนี้ <b>{_mb(touched)}</b> "
            f"จาก {len(mine)} ตัว{share}</p>"
            "<table><tr><th>หุ้น</th><th>ทำไมคนนี้เกี่ยวกับข่าวนี้</th>"
            "<th class='r'>ถือ</th><th class='r'>ปันผลที่จะได้</th>"
            "<th>ข่าวที่ใช้เปิดบทสนทนา</th></tr>")
        for x in sorted(mine, key=lambda r: -r["holding_value"]):
            title = _h.escape(x["article_title"] or "")
            if x["article_url"]:
                title = f"<a href=\"{_h.escape(x['article_url'])}\">{title}</a>"
            div = f"{x['div_baht']:,.0f}" if x["div_baht"] != "" else "—"
            xd = (f"<div style='color:#777;font-size:11px'>XD {_h.escape(str(x['xd_date']))}</div>"
                  if x["xd_date"] else "")
            out.append(
                f"<tr><td><b>{_h.escape(x['entity'])}</b>"
                + (" <span class='pick'>Daily Top Pick</span>" if x["top_pick"] else "")
                + f"<div style='color:#999;font-size:11px'>{_h.escape(x['level'] or '')}</div></td>"
                f"<td style='color:#444'>{_h.escape(x['match_reason'] or '')}</td>"
                f"<td class='r'>{x['holding_value']:,.0f}</td>"
                f"<td class='r'>{div}{xd}</td>"
                f"<td style='font-size:12px'>{title}"
                f"<div style='color:#666'>{_h.escape(x['article_why'] or '')}</div></td></tr>")
        out.append("</table>")
        # ความเห็นของบ้านเราเองของหุ้นที่เขาถือหนักสุด — ประโยคที่ RM เอาไปเปิดสายได้เลย
        lead = max(mine, key=lambda r: r["holding_value"])
        out.append(_ai_box(lead, _h))
        if lead.get("invx_points"):
            items = "".join(f"<li>{_h.escape(_clip(p, 600))}</li>"
                            for p in lead["invx_points"][:6])
            out.append(f"<div class='view'><b>มุมมองของ InnovestX · {_h.escape(lead['entity'])}"
                       f"</b><ul>{items}</ul></div>")

        # ---- ภาพรวมพอร์ตของคนนี้ ชุดเดียวกับหน้าลูกค้าในเว็บ ----
        pf = (profiles or {}).get(key)
        if pf:
            st = pf["stats"]
            idle = st.get("days_since_last_trade")
            out.append(
                "<div class='pstat'>"
                f"<div><b>{pv:,.0f}</b><span>พอร์ตรวม (บาท)</span></div>"
                f"<div><b>{st.get('n_holdings') or 0}</b><span>ตัวที่ถืออยู่</span></div>"
                f"<div><b>{st.get('txn_count') or 0}</b><span>ธุรกรรม 6 เดือน</span></div>"
                f"<div><b>{idle if idle is not None and idle < 9999 else '—'}</b>"
                f"<span>วันตั้งแต่เทรดล่าสุด</span></div>"
                f"<div><b>{pf['dividend_total']:,.0f}</b>"
                f"<span>ปันผลทั้งพอร์ตรอบนี้ (บาท)</span></div>"
                "</div>")

            out.append("<div class='cols'>")

            # สัดส่วนสินทรัพย์ — บอกว่าเขาเป็นนักลงทุนแนวไหนก่อนจะเปิดบทสนทนา
            if pf["mix"]:
                out.append("<div><h3>สัดส่วนสินทรัพย์</h3><div class='mix'>")
                for k, v in sorted(pf["mix"].items(), key=lambda kv: -kv[1])[:8]:
                    out.append(
                        f"<div><em>{_h.escape(_AC_TH.get(k, k))}</em>"
                        f"<i style='width:{max(2, round(v * 160))}px'></i>"
                        f"<u>{v * 100:.1f}%</u></div>")
                out.append("</div></div>")

            if pf["sectors"]:
                out.append("<div><h3>กลุ่มอุตสาหกรรมที่ถือ</h3><div class='mix'>")
                top = max(pf["sectors"].values())
                for k, v in sorted(pf["sectors"].items(), key=lambda kv: -kv[1])[:8]:
                    out.append(
                        f"<div><em>{_h.escape(k)}</em>"
                        f"<i style='width:{max(2, round(v / top * 160))}px;background:#7a5cd0'></i>"
                        f"<u>{v * 100:.1f}%</u></div>")
                out.append("</div></div>")
            out.append("</div>")

            if pf["holdings"]:
                out.append("<h3>ทุกตัวที่ถืออยู่</h3><table>"
                           "<tr><th>สินทรัพย์</th><th>ประเภท</th><th class='r'>มูลค่า</th>"
                           "<th class='r'>กำไร/ขาดทุน</th></tr>")
                for hd in pf["holdings"][:PROFILE_HOLDINGS]:
                    pnl = hd["unrealized_pnl"]
                    cls = "buy" if (pnl or 0) > 0 else "sell" if (pnl or 0) < 0 else ""
                    # ไฟล์ต้นทางไม่ได้ส่งกำไร/ขาดทุนมาทุกตัว — ต้องอ่านออกว่า "ไม่มีข้อมูล"
                    # ไม่ใช่ "+0" ซึ่งอ่านเหมือนเท่าทุนพอดี
                    pnl_txt = f"{pnl:+,.0f}" if pnl is not None else "—"
                    out.append(
                        f"<tr><td><b>{_h.escape(hd['entity'] or hd['product_code'] or '')}</b>"
                        + (f"<div style='color:#999;font-size:11px'>"
                           f"{_h.escape(hd['instrument_label'])}</div>"
                           if hd.get("instrument_label") else "")
                        + f"</td><td style='color:#777'>"
                        f"{_h.escape(_AC_TH.get(hd['asset_class'], hd['asset_class'] or ''))}</td>"
                        f"<td class='r'>{(hd['holding_value'] or 0):,.0f}</td>"
                        f"<td class='r'><span class='{cls}'>{pnl_txt}</span></td></tr>")
                if len(pf["holdings"]) > PROFILE_HOLDINGS:
                    out.append(f"<tr><td colspan='4' style='color:#777'>… อีก "
                               f"{len(pf['holdings']) - PROFILE_HOLDINGS} ตัว</td></tr>")
                out.append("</table>")

            if pf["txn"]:
                out.append("<h3>ธุรกรรมล่าสุด</h3><table>"
                           "<tr><th>วันที่</th><th>รายการ</th><th>สินทรัพย์</th>"
                           "<th class='r'>มูลค่า</th></tr>")
                for tx in pf["txn"]:
                    d = tx["txn_direction"]
                    cls = "buy" if d == "INCREASE" else "sell" if d == "DECREASE" else ""
                    out.append(
                        f"<tr><td class='tnum'>{_h.escape(tx['txn_date'] or '')}</td>"
                        f"<td class='{cls}'>{_h.escape(tx['txn_type'] or '')}"
                        f"<span style='color:#999'> · "
                        f"{_h.escape(_DIRECTION_TH.get(d, d or ''))}</span></td>"
                        f"<td>{_h.escape(tx['entity'] or tx['product_code'] or '')}</td>"
                        f"<td class='r'>{(tx['txn_value'] or 0):,.0f}</td></tr>")
                out.append("</table>")

            if pf["watch"]:
                items = " · ".join(f"{_h.escape(k)} ({v})"
                                   for k, v in sorted(pf["watch"].items(),
                                                      key=lambda kv: kv[1], reverse=True)[:12])
                out.append(f"<h3>เคยเทรดใน 90 วัน แต่ตอนนี้ไม่ถือแล้ว</h3>"
                           f"<p style='font-size:12px;color:#555;margin:0'>{items}</p>")

        out.append("<a class='back' href='#top'>← กลับไปรายการทั้งหมด</a></div>")

    out.append(
        "<div class='note'><b>เรื่องรหัสลูกค้าในไฟล์</b><br>"
        "รหัสอย่าง CUST00123 เป็นรหัสอ้างอิงในระบบ ไม่ใช่ชื่อจริง — ระบบนี้ไม่เก็บชื่อ เบอร์ "
        "หรืออีเมลของลูกค้าไว้เลย<br>ถ้าต้องการตารางเทียบว่ารหัสไหนคือลูกค้าคนใด "
        "ให้ขอจากผู้ดูแลระบบที่เป็นคนส่งอีเมลฉบับนี้</div>"
        "<p style='color:#999;font-size:12px;margin-top:14px'>"
        "สร้างจากข้อมูลในระบบ MatchPort · กดที่รหัสลูกค้าในตารางเพื่อเปิดหน้าของคนนั้น "
        "แล้วกด “กลับไปรายการทั้งหมด” หรือปุ่มย้อนกลับของเบราว์เซอร์เพื่อกลับ"
        "</p></div></body></html>")
    return "\n".join(out).encode("utf-8")


PROFILE_HOLDINGS = 15      # ถือเกินนี้ตัดแล้วบอกว่าเหลืออีกกี่ตัว — ไฟล์ต้องยังเปิดไหว
PROFILE_TXN = 12


def customer_profiles(con: sqlite3.Connection, keys: list[str],
                      divs: dict[str, dict]) -> dict[str, dict]:
    """ข้อมูลพอร์ตของลูกค้าแต่ละคน ชุดเดียวกับที่หน้าเว็บแสดง

    ดึงทีเดียวทุกคนแล้วแจกทีหลัง — วนยิงทีละคน 56 คนคือ 168 คิวรี
    ไฟล์เดียวไม่ควรใช้เวลานานขนาดนั้นตอนกดส่ง
    """
    if not keys:
        return {}
    qs = ",".join("?" * len(keys))
    out: dict[str, dict] = {k: {"mix": {}, "sectors": {}, "watch": {}, "holdings": [],
                                "txn": [], "stats": {}} for k in keys}

    for r in con.execute(f"SELECT * FROM customers WHERE customer_key IN ({qs})", keys):
        d = dict(r)
        p = out[d["customer_key"]]
        p["mix"] = db.jload(d.get("asset_mix"), {}) or {}
        p["sectors"] = db.jload(d.get("sector_exposure"), {}) or {}
        p["watch"] = db.jload(d.get("watchlist"), {}) or {}
        p["stats"] = {k: d.get(k) for k in
                      ("portfolio_value", "n_holdings", "n_watchlist", "txn_count",
                       "days_since_last_trade", "trade_frequency", "unrealized_state",
                       "portfolio_tier", "persona", "dominant_asset_class")}

    for r in con.execute(f"""
            SELECT customer_key, entity, product_code, asset_class, instrument_label,
                   holding_value, unrealized_pnl
            FROM holdings WHERE customer_key IN ({qs})
            ORDER BY holding_value DESC""", keys):
        out[r["customer_key"]]["holdings"].append(dict(r))

    # ธุรกรรมล่าสุดบอกว่าเขากำลังทำอะไรอยู่ — ซื้อเพิ่มหรือทยอยขาย เปลี่ยนวิธีเปิดบทสนทนา
    for r in con.execute(f"""
            SELECT customer_key, txn_date, txn_type, txn_direction, entity, product_code,
                   asset_class, txn_value
            FROM transactions
            WHERE customer_key IN ({qs}) AND txn_direction<>'IGNORE'
            ORDER BY txn_date DESC""", keys):
        t = out[r["customer_key"]]["txn"]
        if len(t) < PROFILE_TXN:
            t.append(dict(r))

    for p in out.values():
        # ปันผลรวมทั้งพอร์ต ไม่ใช่เฉพาะตัวที่ข่าวแตะ — เป็นเหตุผลโทรที่ไม่ต้องรอข่าว
        p["dividend_total"] = sum(
            (h["holding_value"] or 0) * divs[h["entity"]]["yield_interim"] / 100
            for h in p["holdings"] if h["entity"] in divs)
    return out


# --------------------------------------------------------------------------
# ส่งจริง
# --------------------------------------------------------------------------

class OutlookUnavailable(RuntimeError):
    """เปิด Outlook ไม่ได้ / login ไม่เสร็จ — ต่างจากส่งไม่สำเร็จด้วยเหตุอื่น"""


SEND_ATTEMPTS = 3
_RETRY_WAIT = 8


def send_mail(to: str, subject: str, html: str, files: list[tuple[str, bytes]]) -> None:
    """ส่งฉบับเดียวพร้อมไฟล์แนบ ลองซ้ำเองถ้า Outlook ยังไม่พร้อม

    ลองซ้ำเฉพาะกรณี "Outlook ยังไม่พร้อม" เท่านั้น (NOOUTLOOK / timeout) ซึ่งยืนยันได้ว่า
    ยังไม่มีอะไรถูกส่งออกไป — ความล้มเหลวหลัง .Send() ห้ามลองซ้ำเด็ดขาด เพราะอาจส่งไปแล้ว
    แล้วการลองใหม่จะกลายเป็นส่งซ้ำสองฉบับ
    """
    if os.name != "nt" or not _PS_BIN:
        raise OutlookUnavailable("ส่งอัตโนมัติได้เฉพาะบน Windows ที่มี Outlook เท่านั้น")

    tmp = tempfile.mkdtemp(prefix="matchport_mail_")
    try:
        paths = []
        for name, blob in files:
            fp = os.path.join(tmp, os.path.basename(name))
            with open(fp, "wb") as fh:
                fh.write(blob)
            paths.append(fp)

        cfg_path = os.path.join(tmp, "_send_cfg.json")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump({"to": to, "subject": subject, "html": html, "attachments": paths},
                      fh, ensure_ascii=False)

        last = ""
        for attempt in range(SEND_ATTEMPTS):
            try:
                p = subprocess.run(
                    [_PS_BIN, "-NoProfile", "-NonInteractive", "-Command", _SEND_PS],
                    capture_output=True, text=True, encoding="utf-8", timeout=300,
                    env={**os.environ, _CFG_ENV: cfg_path})
            except subprocess.TimeoutExpired:
                last = "สั่ง Outlook ใช้เวลานานเกินไป"
                time.sleep(_RETRY_WAIT)
                continue

            out = (p.stdout or "").strip()
            if "SENT" in out:
                return
            if "NOOUTLOOK" in out:
                last = "เปิด Outlook (Classic) ไม่ได้ หรือ login ยังไม่เสร็จ"
                if attempt < SEND_ATTEMPTS - 1:
                    time.sleep(_RETRY_WAIT)
                continue
            # ผิดพลาดหลังจากเริ่มสร้าง/ส่งเมลแล้ว — หยุดทันที ไม่ลองซ้ำ
            err = next((ln.split("|", 1)[1] for ln in out.splitlines()
                        if ln.startswith("ERR|")), "") or (p.stderr or "").strip()
            raise RuntimeError(f"Outlook: {err[:400] or 'ส่งไม่สำเร็จ'}")

        raise OutlookUnavailable(
            f"{last} — ลองแล้ว {SEND_ATTEMPTS} ครั้ง เปิด Outlook ค้างไว้แล้วกดใหม่อีกที")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def compose_team(day: str, books: list[dict], warning: str | None = None) -> dict:
    """อีเมลฉบับเดียวถึงทั้งทีม — สรุปในตัวอีเมล ของละเอียดอยู่ในไฟล์แนบรายคน

    books: [{rm_id, report_name, rows, entities, value_total, top}]
    """
    total = sum(b["value_total"] for b in books)
    # วันที่อยู่ในหัวข้อเสมอ และถ้าไม่ใช่ของวันนี้ต้องเห็นตั้งแต่ยังไม่เปิดอ่าน
    flag = "[ข้อมูลไม่ใช่ของวันนี้] " if warning else ""
    subject = f"[MatchPort] {flag}เรื่องที่ควรโทร {day} — {len(books)} ทีม รวม {_mb(total)}"

    html = [
        '<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;'
        'color:#1a1a1a;max-width:760px">',
        f'<h2 style="margin:0 0 4px;font-size:19px">เรื่องที่ควรโทร · {day}</h2>',
        (f'<div style="background:#fff4e5;border:1px solid #e0a33a;color:#7a4c00;'
         f'padding:11px 14px;border-radius:4px;font-size:13px;margin:10px 0 14px">'
         f'<b>ข้อมูลไม่ใช่ของวันนี้</b><br>{warning}</div>' if warning else ""),
        f'<p style="margin:0 0 16px;color:#555;font-size:14px">'
        f'ข่าวของวันไปแตะเงินในพอร์ตลูกค้ารวม <b>{_mb(total)}</b> '
        f'แต่ละทีมเปิดไฟล์แนบที่ชื่อตรงกับรหัสของคุณ — ในไฟล์กดที่รหัสลูกค้าได้ '
        f'เพื่อดูหน้าของคนนั้นว่าถืออะไรและควรคุยเรื่องอะไร</p>',
        '<table style="border-collapse:collapse;font-size:14px;width:100%">',
        '<tr style="background:#f5f5f5">'
        '<th style="text-align:left;padding:7px 10px;border:1px solid #e0e0e0">ทีม</th>'
        '<th style="text-align:right;padding:7px 10px;border:1px solid #e0e0e0">ตัวที่ควรโทร</th>'
        '<th style="text-align:right;padding:7px 10px;border:1px solid #e0e0e0">รายชื่อที่ต้องคุย</th>'
        '<th style="text-align:right;padding:7px 10px;border:1px solid #e0e0e0">เงินที่ข่าวแตะ</th>'
        '<th style="text-align:left;padding:7px 10px;border:1px solid #e0e0e0">ไฟล์ของคุณ</th></tr>',
    ]
    for b in books:
        html.append(
            f'<tr><td style="padding:7px 10px;border:1px solid #e0e0e0"><b>{b["rm_id"]}</b></td>'
            f'<td style="text-align:right;padding:7px 10px;border:1px solid #e0e0e0">'
            f'{b["entities"]:,}</td>'
            f'<td style="text-align:right;padding:7px 10px;border:1px solid #e0e0e0">'
            f'{len(b["rows"]):,}</td>'
            f'<td style="text-align:right;padding:7px 10px;border:1px solid #e0e0e0">'
            f'{_mb(b["value_total"])}</td>'
            f'<td style="padding:7px 10px;border:1px solid #e0e0e0;color:#555">'
            f'{b["report_name"]}</td></tr>')
    html.append("</table>")

    for b in books:
        if not b["top"]:
            continue
        html.append(f'<h3 style="margin:22px 0 6px;font-size:15px">{b["rm_id"]} '
                    f'<span style="color:#777;font-weight:normal">— ห้าอันดับแรก '
                    f'(ทั้งหมด {b["entities"]} ตัวอยู่ในไฟล์)</span></h3>')
        for n, t in enumerate(b["top"], 1):
            extra = ""
            if t.get("xd_date"):
                tag = " (คาดการณ์)" if t["div_status"] == "คาดการณ์" else ""
                extra = (f'<div style="font-size:12px;color:#555">ปันผล XD {t["xd_date"]} · '
                         f'จ่าย {t["pay_date"]} · {t["div_yield"]}% งวดนี้{tag}</div>')
            # ความเห็นของนักวิเคราะห์บ้านเราเองสำคัญกว่าตัวข่าว จึงอยู่ในอีเมลด้วย ไม่ใช่แค่ในไฟล์
            view = ""
            if t.get("invx_points") or t.get("invx_view"):
                pts = t.get("invx_points") or []
                inner = ("<ul style='margin:0;padding-left:17px'>"
                         + "".join(f"<li style='margin:2px 0'>{_clip(p, 260)}</li>"
                                   for p in pts[:3]) + "</ul>"
                         + (f"<div style='color:#6b7c99;font-size:12px;margin-top:3px'>"
                            f"ยังมีอีก {len(pts) - 3} ข้อในไฟล์แนบ</div>" if len(pts) > 3 else "")
                         ) if pts else _clip(t["invx_view"], 420)
                view = (f'<div style="margin-top:6px;background:#f4f7fd;'
                        f'border-left:3px solid #3b6fd4;padding:8px 11px;font-size:13px;'
                        f'color:#22324d"><b style="color:#1a4fa0;font-size:11px;display:block;'
                        f'margin-bottom:2px">มุมมองของ InnovestX</b>{inner}</div>')
            title = (f'<a href="{t["article_url"]}" style="color:#1a4fa0;'
                     f'text-decoration:none">{t["article_title"]}</a>'
                     if t.get("article_url") else t["article_title"])
            html.append(
                f'<div style="border-top:1px solid #ececec;padding:8px 0">'
                f'<div style="font-size:14px"><b>{n}. {t["entity"]}</b> '
                f'<span style="color:#555">— {_mb(t["entity_value"])} · '
                f'ลูกค้า {t["entity_customers"]} คน · ข่าว{t["direction"]}</span></div>'
                f'<div style="font-size:13px;color:#333;margin-top:2px">{title}</div>'
                f'<div style="font-size:12px;color:#666">{t["article_why"]}</div>'
                f'{view}{extra}</div>')

    # รหัสลูกค้าในไฟล์ไม่ใช่ชื่อจริง — ระบบไม่เก็บชื่อลูกค้าเลย (ไฟล์นำเข้าที่มี PII ถูกปฏิเสธ)
    # คนรับต้องรู้ว่าต้องไปขอตารางเทียบจากใคร ไม่ใช่เดาเองหรือคิดว่าไฟล์เสีย
    html.append(
        '<div style="margin-top:22px;border:1px solid #e0e0e0;background:#fafafa;'
        'padding:12px 14px;font-size:13px;color:#333">'
        '<b>เรื่องรหัสลูกค้าในไฟล์</b><br>'
        'คอลัมน์ "รหัสลูกค้า" เป็นรหัสอ้างอิงในระบบ (เช่น CUST00123) ไม่ใช่ชื่อจริง '
        'ระบบนี้ไม่เก็บชื่อ เบอร์ หรืออีเมลของลูกค้าไว้เลย<br>'
        'ถ้าต้องการตารางเทียบว่ารหัสไหนคือลูกค้าคนใด ให้ขอจากผู้ดูแลระบบที่เป็นคนกดส่งอีเมลฉบับนี้'
        '</div>')
    html.append('<p style="font-size:12px;color:#999;margin-top:16px;'
                'border-top:1px solid #e5e5e5;padding-top:10px">'
                'อีเมลนี้สร้างจากข้อมูลในระบบ MatchPort และไม่ได้ส่งถึงลูกค้า</p></div>')
    return {"subject": subject, "html": "\n".join(html)}


def log(con: sqlite3.Connection, rm_id: str, to: str, ok: bool, detail: str) -> None:
    now = dt.datetime.now().isoformat(timespec="seconds")
    with con:
        con.execute("INSERT INTO ingest_log(kind, started_at, finished_at, ok, detail) "
                    "VALUES(?,?,?,?,?)",
                    (f"mail:{rm_id}", now, now, 1 if ok else 0, f"{to} — {detail}"))
