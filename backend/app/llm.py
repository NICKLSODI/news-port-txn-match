# -*- coding: utf-8 -*-
"""เรียก Claude Code CLI ที่ติดตั้งบนเครื่อง (headless `claude -p`)

ทำไมใช้ CLI ไม่ใช่ API key: เครื่องนี้ล็อกอิน Claude Code ไว้แล้ว งานนี้จึงไม่ต้องมี
ANTHROPIC_API_KEY และไม่มีบิลแยกต่อ token — ใช้สิทธิ์เดียวกับที่คนใช้อยู่

หลักที่ห้ามผ่อน: ผลจากโมเดล "เสนอ" ได้ แต่ต้องผ่านการตรวจก่อนถูกบันทึก
ทุกอย่างที่ลงฐานต้องมีประโยคจากบทความจริงกำกับ (ดู verify_quote) เพราะหน้าจอ
สัญญากับ RM ว่าทุกแถวอ้างหลักฐานได้ ไม่ใช่ "โมเดลว่ามา"
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading

MODEL = "claude-sonnet-5"
TIMEOUT_SECONDS = 240
BIN = shutil.which("claude")

# claude -p เรียกแบบไม่ตั้งค่าอะไรจะแบก system prompt ของตัวช่วยเขียนโค้ดกับคำอธิบาย
# เครื่องมือทั้งชุดไปด้วยทุกครั้ง วัดได้ 32,485 token ต่อครั้ง ทั้งที่งานนี้ไม่ได้ใช้เลย
# แทนด้วย system prompt สั้น ๆ และปิดเครื่องมือทั้งหมด เหลือ 8,336 token (ถูกลง 4 เท่า)
SYSTEM_PROMPT = ("You read Thai financial articles and answer strictly in JSON. "
                 "No tools, no preamble, no explanation.")
NO_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch",
            "TodoWrite", "Task", "NotebookEdit", "BashOutput", "KillShell",
            "SlashCommand", "ExitPlanMode"]

# ยอดใช้งานสะสมของ process นี้ — งานอ่านข่ายิงขนานหลายเธรด จึงต้องล็อกตอนบวก
_LOCK = threading.Lock()
_USAGE = {"calls": 0, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0,
          "cost_usd": 0.0}


def available() -> dict:
    return {"available": BIN is not None, "bin": BIN, "model": MODEL}


def usage() -> dict:
    """ยอด token/ค่าใช้จ่ายสะสมตั้งแต่เริ่ม process — ใช้ตอบว่างานรอบนี้กินไปเท่าไร"""
    with _LOCK:
        return dict(_USAGE)


def reset_usage() -> None:
    with _LOCK:
        for k in _USAGE:
            _USAGE[k] = 0 if k != "cost_usd" else 0.0


def _count(u: dict, cost: float) -> None:
    with _LOCK:
        _USAGE["calls"] += 1
        _USAGE["input"] += int(u.get("input_tokens") or 0)
        _USAGE["cache_write"] += int(u.get("cache_creation_input_tokens") or 0)
        _USAGE["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
        _USAGE["output"] += int(u.get("output_tokens") or 0)
        _USAGE["cost_usd"] += float(cost or 0.0)


def ask(prompt: str, timeout: int = TIMEOUT_SECONDS) -> tuple[str, str | None]:
    """คืน (คำตอบ, ปัญหา) — ไม่ raise เพื่อให้ตัวเรียกตัดสินใจต่อได้เอง

    prompt ส่งผ่าน stdin ไม่ใช่ argv — เนื้อข่าวมีอักขระพิเศษเยอะ ถ้าใส่ใน command line
    บน Windows (ซึ่งต้องผ่าน cmd.exe เพราะ claude เป็น .cmd/.ps1 shim) จะโดนตีความ

    ขอผลเป็น json เพื่อเก็บยอด token ของทุกครั้งที่เรียก — ไม่มีตัวเลขนี้ก็ตอบไม่ได้ว่า
    งานอ่านข่าวแต่ละวันกินไปเท่าไร และไม่รู้ว่าที่ปรับให้ประหยัดได้ผลจริงไหม
    """
    if not BIN:
        return "", "ไม่พบคำสั่ง claude บนเครื่อง — ติดตั้ง Claude Code แล้วรัน claude login"
    # ตัด ANTHROPIC_BASE_URL ออกเพื่อให้ใช้สิทธิ์จาก claude login เสมอ
    # ไม่ใช่พร็อกซีที่ process แม่อาจใส่ไว้
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_BASE_URL"}
    args = [BIN, "-p", "--output-format", "json", "--model", MODEL,
            "--system-prompt", SYSTEM_PROMPT, "--disallowed-tools", *NO_TOOLS]
    try:
        proc = subprocess.run(
            args, input=prompt, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, env=env,
            # claude บน Windows เป็น shim (.cmd/.ps1) ซึ่ง CreateProcess เรียกตรงไม่ได้
            shell=(os.name == "nt"),
        )
    except subprocess.TimeoutExpired:
        return "", f"claude ใช้เวลาเกิน {timeout} วินาที"
    except OSError as e:                       # noqa: BLE001
        return "", f"เรียก claude ไม่สำเร็จ: {e}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return "", f"claude ตอบกลับเป็นข้อผิดพลาด: {detail[:300]}"
    try:
        env_out = json.loads((proc.stdout or "").strip())
    except ValueError:
        return "", f"อ่านผลจาก claude ไม่ได้: {(proc.stdout or '')[:200]}"
    _count(env_out.get("usage") or {}, env_out.get("total_cost_usd") or 0.0)
    if env_out.get("is_error"):
        return "", f"claude ตอบกลับเป็นข้อผิดพลาด: {str(env_out.get('result'))[:300]}"
    return str(env_out.get("result") or "").strip(), None


_JSON_BLOCK = re.compile(r"[\{\[][\s\S]*[\}\]]")


def ask_json(prompt: str, timeout: int = TIMEOUT_SECONDS) -> tuple[dict | list | None, str | None]:
    """เหมือน ask แต่แกะ JSON ให้ — โมเดลมักห่อด้วย ```json หรือมีคำอธิบายนำ"""
    text, problem = ask(prompt, timeout)
    if problem:
        return None, problem
    if not text:
        return None, "claude ไม่ได้ส่งคำตอบกลับมา"
    for candidate in (text, (_JSON_BLOCK.search(text) or type("_", (), {"group": lambda *_: ""})()).group(0)):
        if not candidate:
            continue
        try:
            return json.loads(candidate), None
        except ValueError:
            continue
    return None, f"อ่าน JSON จากคำตอบไม่ได้: {text[:200]}"


# --------------------------------------------------------------------------

_WS = re.compile(r"\s+")
# เครื่องหมายที่ต่างกันระหว่างต้นฉบับกับที่โมเดลพิมพ์กลับมา (อัญประกาศโค้ง ขีดยาว ฯลฯ)
_PUNCT = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-", " ": " "})
QUOTE_PREFIX = 24


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "").translate(_PUNCT)).strip()


def verify_quote(quote: str, source: str, min_chars: int = 12) -> bool:
    """ประโยคที่โมเดลอ้างต้องมีอยู่จริงในบทความ ไม่ใช่เรียบเรียงใหม่หรือแต่งขึ้น

    เทียบแบบยุบช่องว่างและปรับเครื่องหมายให้ตรงกัน เพราะเนื้อหาที่สกัดจากหน้าเว็บ
    ตัดบรรทัดไม่เหมือนต้นฉบับและอัญประกาศเป็นแบบโค้ง

    ยอมให้ตรงแค่ช่วงต้น 24 ตัวอักษรได้ — โมเดลมักยกประโยคมาแล้วต่อท้ายด้วยข้อความ
    ของประโยคถัดไปหรือตัดคำสุดท้ายทิ้ง ถ้าบังคับตรงทั้งก้อนจะทิ้งของที่ถูกต้องไปด้วย
    (เจอจริง: ทิศทางที่อ้างประโยคภาษาอังกฤษในบทความไทยถูกตีว่าไม่ผ่านทั้งที่มีอยู่)
    ช่วงต้น 24 ตัวอักษรยังยาวพอจะพิสูจน์ว่าอ่านจากบทความจริง ไม่ใช่แต่งขึ้น
    """
    q, src = _norm(quote), _norm(source)
    if len(q) < min_chars or not src:
        return False
    return q in src or q[:QUOTE_PREFIX] in src
