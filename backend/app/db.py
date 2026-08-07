# -*- coding: utf-8 -*-
"""SQLite schema + helpers

เก็บทุกอย่างไว้ในไฟล์เดียว (matchport.db) — ไม่ต้องติดตั้ง DB server
ผลการจับคู่ถูกคำนวณตอน ingest แล้วเก็บลงตาราง matches เพื่อให้หน้าจอ RM เปิดเร็ว
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "matchport.db"

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- STEP1 --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS holdings (
  id INTEGER PRIMARY KEY,
  customer_key TEXT NOT NULL,
  account_key  TEXT,
  rm_id        TEXT,
  product_code TEXT,
  asset_class  TEXT NOT NULL,
  asset_subclass TEXT,
  holding_value REAL,
  unrealized_pnl REAL,
  as_of_date   TEXT NOT NULL,
  entity       TEXT,
  entity_kind  TEXT,
  entity_confidence TEXT,
  map_rule     TEXT,
  instrument_label TEXT
);
CREATE INDEX IF NOT EXISTS ix_hold_cust   ON holdings(customer_key);
CREATE INDEX IF NOT EXISTS ix_hold_entity ON holdings(entity);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY,
  customer_key TEXT NOT NULL,
  account_key  TEXT,
  rm_id        TEXT,
  product_code TEXT,
  asset_class  TEXT NOT NULL,
  asset_subclass TEXT,
  txn_date     TEXT NOT NULL,
  txn_type     TEXT,
  txn_direction TEXT,
  txn_units    REAL,
  txn_value    REAL,
  entity       TEXT,
  entity_kind  TEXT,
  instrument_label TEXT
);
CREATE INDEX IF NOT EXISTS ix_txn_cust   ON transactions(customer_key);
CREATE INDEX IF NOT EXISTS ix_txn_entity ON transactions(entity);
CREATE INDEX IF NOT EXISTS ix_txn_date   ON transactions(txn_date);

-- STEP5 --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
  customer_key TEXT PRIMARY KEY,
  rm_id TEXT,
  persona TEXT,
  dominant_asset_class TEXT,
  portfolio_value REAL,
  portfolio_tier TEXT,
  trade_frequency TEXT,
  days_since_last_trade INTEGER,
  txn_count INTEGER,
  unrealized_state TEXT,
  n_holdings INTEGER,
  n_watchlist INTEGER,
  asset_mix TEXT,
  sector_exposure TEXT,
  holdings TEXT,          -- {entity: value}
  labels TEXT,            -- {entity: instrument_label}
  watchlist TEXT,         -- {entity: last_traded}
  last_traded TEXT        -- {entity: iso date}
);
CREATE INDEX IF NOT EXISTS ix_cust_rm      ON customers(rm_id);
CREATE INDEX IF NOT EXISTS ix_cust_persona ON customers(persona);

-- STEP2 / STEP3 ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS articles (
  article_id   TEXT PRIMARY KEY,
  record_type  TEXT NOT NULL,          -- article | segment
  parent_article_id TEXT,
  segment_no   INTEGER,
  segment_text TEXT,
  title        TEXT NOT NULL,
  url          TEXT,
  summary      TEXT,
  trigger_at   TEXT NOT NULL,          -- A-06 published_date
  display_at   TEXT,                   -- A-07 displayed_date
  pillar       TEXT,
  category     TEXT,
  subcategory  TEXT NOT NULL,
  subcategory_name TEXT,
  source       TEXT,
  product_type TEXT,
  entity_raw   TEXT,
  entity       TEXT,
  article_asset_class TEXT,
  content_type TEXT,
  entity_source TEXT,
  entity_confidence TEXT,
  sector       TEXT,
  macro_topic  TEXT,
  importance   INTEGER,
  urgency      TEXT,
  role         TEXT,
  mode         TEXT,                   -- realtime | digest
  image_url    TEXT,
  read_minutes INTEGER,
  -- GAP-21 — ไม่มีประตูให้คนอนุมัติแล้ว ทุกบทความเข้าสู่การจับคู่ทันที
  -- สามช่องนี้เก็บเกรดคุณภาพของ entity ที่ระบบสกัดเอง ไว้ให้คนเปิดดูย้อนหลัง
  auto_grade   TEXT,            -- confirmed | auto_verified | weak
  auto_reason_th TEXT,
  auto_reason_en TEXT,
  auto_checks  TEXT,            -- [{check, ok, th, en, rule}]
  evidence     TEXT,            -- {entity: ที่มาที่ทำให้จับได้}
  matched_at   TEXT,
  n_matches    INTEGER DEFAULT 0,
  ingested_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_art_trigger ON articles(trigger_at DESC);
CREATE INDEX IF NOT EXISTS ix_art_sub     ON articles(subcategory);
CREATE INDEX IF NOT EXISTS ix_art_type    ON articles(record_type);
CREATE INDEX IF NOT EXISTS ix_art_mode    ON articles(mode);

-- STEP6 --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matches (
  id INTEGER PRIMARY KEY,
  article_id   TEXT NOT NULL,
  customer_key TEXT NOT NULL,
  rm_id        TEXT,
  persona      TEXT,
  level        TEXT NOT NULL,
  matched_entity TEXT,
  score        REAL NOT NULL,
  reason_th    TEXT,
  reason_en    TEXT,
  evidence     TEXT,                   -- [{level, entity, reason_th, reason_en, rule}]
  instrument_label TEXT,
  holding_value REAL,
  computed_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_match_art   ON matches(article_id, score DESC);
CREATE INDEX IF NOT EXISTS ix_match_rm    ON matches(rm_id, score DESC);
CREATE INDEX IF NOT EXISTS ix_match_cust  ON matches(customer_key);
CREATE UNIQUE INDEX IF NOT EXISTS ux_match ON matches(article_id, customer_key);

-- STEP8 --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS unmapped (
  id INTEGER PRIMARY KEY,
  bucket TEXT NOT NULL,                -- news_entity | holding_code | subcategory | api | fund | dr
  raw TEXT NOT NULL,
  rule TEXT,
  reason TEXT,
  n INTEGER DEFAULT 1,
  first_seen TEXT,
  last_seen TEXT,
  sample_ref TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_unmapped ON unmapped(bucket, raw, rule);

-- C2 ความสัมพันธ์หุ้น ที่ระบบเรียนเองจาก co-mention (R3.29 - R3.36) ------------
CREATE TABLE IF NOT EXISTS entity_pairs (
  a TEXT NOT NULL, b TEXT NOT NULL,
  n INTEGER DEFAULT 0,
  article_ids TEXT,
  PRIMARY KEY (a, b)
);

CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT NOT NULL);

-- แท่งเทียนที่ดึงมาจาก Yahoo (ดู prices.py) — เก็บดิบไว้ทั้งชุดต่อช่วงเวลา
-- เปิดหน้าเดิมซ้ำไม่ต้องยิงใหม่ และถ้าดึงไม่สำเร็จยังมีของเดิมให้แสดง
CREATE TABLE IF NOT EXISTS price_cache (
  k          TEXT PRIMARY KEY,        -- "<symbol>|<range>|<version>"
  symbol     TEXT NOT NULL,
  range_     TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  payload    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_log (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  started_at TEXT, finished_at TEXT,
  ok INTEGER, detail TEXT
);

-- ตาราง "ตามรอยหุ้นปันผล" จาก INVX Data Book รายเดือน (ดู dividends.py)
--
-- สองอัตราในแถวเดียวกันใช้คนละงาน แยกให้ชัดตั้งแต่ชั้นเก็บ:
--   yield_interim  งวดนี้งวดเดียว -> เงินบาทที่ลูกค้าจะได้รอบนี้ + ปฏิทิน XD
--   yield_forecast ทั้งปี 69F      -> สไตล์พอร์ต + เครื่องกรอง "อยากได้ 7%"
-- เอา interim ไปคิด yield ทั้งพอร์ตจะต่ำกว่าจริงหลายเท่า เพราะเป็นแค่งวดเดียว
--
-- source_line เก็บบรรทัดดิบที่แกะมา — ตัวเลขการเงินต้องย้อนไปดูต้นทางได้เสมอ
CREATE TABLE IF NOT EXISTS dividends (
  entity         TEXT NOT NULL,      -- รหัสกลาง ตรงกับ holdings.entity
  report_month   TEXT NOT NULL,      -- '2026-08' เดือนของ Data Book
  price          REAL,               -- ราคาปิด ณ วันที่รายงาน
  rating         TEXT,               -- Outperform / Neutral / Underperform
  dps            REAL,               -- เงินปันผล/หุ้น (บาท) งวดนี้
  yield_interim  REAL,               -- % ผลตอบแทน งวดนี้
  xd_date        TEXT,               -- วัน XD ตามที่รายงานเขียน (Aug-26 / 05-Aug-26)
  pay_date       TEXT,
  period         TEXT,               -- ผลดำเนินงาน เช่น 1H26, Apr 26 - Sep 26
  yield_forecast REAL,               -- อัตราเงินปันผลตอบแทนปี 69F (%)
  remark         TEXT,               -- Official (ประกาศแล้ว) / Estimated (คาดการณ์)
  as_of          TEXT,               -- วันที่ข้อมูลในรายงาน
  source_url     TEXT,
  source_line    TEXT,
  ingested_at    TEXT NOT NULL,
  PRIMARY KEY (entity, report_month)
);
CREATE INDEX IF NOT EXISTS ix_dividends_month ON dividends(report_month);
"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


MIGRATIONS = [
    ("articles", "subcategory_name", "TEXT"),
    ("articles", "auto_grade", "TEXT"),
    ("articles", "auto_reason_th", "TEXT"),
    ("articles", "auto_reason_en", "TEXT"),
    ("articles", "auto_checks", "TEXT"),
    ("articles", "evidence", "TEXT"),
    # R2.7 — เนื้อหาเต็มของบทความ (search API ส่งมาแค่ย่อหน้าแรก ~500-700 ตัวอักษร)
    ("articles", "full_text", "TEXT"),
    ("articles", "full_text_at", "TEXT"),
    # AI-01 — ทิศทางที่ Claude Code อ่านได้จากเนื้อหาเต็ม พร้อมประโยคที่ยกมา
    # เก็บแยกจากทิศทางที่กฎคำอ่านได้ เพื่อให้หน้าจอบอกได้ว่าอันไหนมาจากไหน
    ("articles", "ai_direction", "TEXT"),
    ("articles", "ai_direction_quote", "TEXT"),
    ("articles", "ai_at", "TEXT"),
    # AI-02 — "ทำไมถึงไม่ตีความ" ต้องตอบได้เหมือนกับตอนที่ตีความ
    # ai_reason      รหัสเหตุผลที่ไม่สรุปทิศทาง (history_only / data_only / ...)
    # ai_reason_th   ประโยคที่หน้าจอเอาไปแสดงตรง ๆ
    # ai_mentions    บันทึกทุกตัวย่อที่โมเดลเห็น พร้อมผลตรวจว่ารับหรือทิ้งเพราะอะไร
    ("articles", "ai_reason", "TEXT"),
    ("articles", "ai_reason_th", "TEXT"),
    ("articles", "ai_mentions", "TEXT"),
]


def init() -> None:
    con = connect()
    with con:
        con.executescript(SCHEMA)
        for table, col, kind in MIGRATIONS:
            have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
            if col not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
    con.close()


# --------------------------------------------------------------------------

def get_setting(con: sqlite3.Connection, key: str, default=None):
    row = con.execute("SELECT v FROM settings WHERE k=?", (key,)).fetchone()
    return json.loads(row["v"]) if row else default


def set_setting(con: sqlite3.Connection, key: str, value) -> None:
    con.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (key, json.dumps(value, ensure_ascii=False)))


def report_unmapped(con: sqlite3.Connection, bucket: str, raw: str, rule: str,
                    reason: str, ref: str = "", now: str = "") -> None:
    """R3.22 / R4.35 / STEP8 — ห้ามเงียบ ทุกอย่างที่จัดการไม่ได้ต้องเข้าบัญชีนี้"""
    con.execute(
        """INSERT INTO unmapped(bucket, raw, rule, reason, n, first_seen, last_seen, sample_ref)
           VALUES(?,?,?,?,1,?,?,?)
           ON CONFLICT(bucket, raw, rule) DO UPDATE SET
             n = n + 1, last_seen = excluded.last_seen,
             sample_ref = COALESCE(NULLIF(unmapped.sample_ref,''), excluded.sample_ref)""",
        (bucket, raw, rule or "", reason or "", now, now, ref))


def jdump(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def jload(v, default=None):
    if not v:
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default
