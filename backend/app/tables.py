# -*- coding: utf-8 -*-
"""Rule tables — STEP1-STEP8.

ตารางในไฟล์นี้คือ "กฎ" ไม่ใช่ "ข้อมูล" จึงเขียนไว้ในโค้ดพร้อมเลขกฎกำกับ
ส่วนรายการข้อมูล (97 หุ้นไทย, 197 DR, 69 หุ้นกู้, 939 กองทุน, entity dictionary,
ความสัมพันธ์หุ้น, คำค้น macro) ดึงจากไฟล์ spec ตอน build — ดู refdata.py

ทุกค่าที่ spec เว้นว่างไว้ ติดป้าย ASSUMED และรวมอยู่ใน SPEC_GAPS
เพื่อให้ /api/spec-gaps รายงานออกหน้าจอได้ ตามหลักการ "ไม่มั่นใจ ไม่เดาเงียบ"
"""

# ==========================================================================
# STEP1 — asset_class / txn_direction
# ==========================================================================

# R1.5 — product_txt_key (ค่าดิบต้นทาง) -> asset_class ที่ระบบใช้
ASSET_CLASS_BY_TXT_KEY = {
    "equity": "EQUITY_TH",
    "offshore_equity": "EQUITY_OFFSHORE",
    "offshore_options": "OPTIONS_OFFSHORE",
    "offshore_bond": "BOND_OFFSHORE",
    "offshore_fund": "FUND_OFFSHORE",
    "fe_diy": "FUND_DIY",
    "fe_robo": "FUND_ROBO",
    "digital_asset": "DIGITAL_ASSET",
    "bond": "BOND_TH",
    "bond_ipo": "BOND_TH",
    "tfex": "TFEX",
    "kiko": "STRUCTURED_NOTE",
}

# R1.5 — enum ที่ไม่รู้จักไปที่ OTHER และต้องรายงาน ห้ามทิ้งเงียบ
ASSET_CLASS_FALLBACK = "OTHER"

# txn_direction — ระบบคำนวณเองจาก txn_type (STEP1 ชีต Enums)
TXN_DIRECTION = {
    "Buy": "INCREASE",
    "SUB": "INCREASE",
    "SWI": "INCREASE",
    "TRI": "INCREASE",
    "XSI": "INCREASE",
    "Sell": "DECREASE",
    "RED": "DECREASE",
    "SWO": "DECREASE",
    "TRO": "DECREASE",
    "XSO": "DECREASE",
    "Buy(Long)": "DERIVATIVE_LONG",   # R1.10
    "Sell(Short)": "DERIVATIVE_SHORT",  # R1.10
    # GAP-10 — spec สั่งไม่นับ da_* ทุกแถว แต่ไฟล์จริงไม่มีแถว Buy/Sell ของคริปโตเลย
    # แถว da_trading_fee_* คือตัวธุรกรรมเอง (มี trading_value + confirm_unit ครบ)
    # ส่วน da_spread_* มี trading_value = 0 ทุกแถว (แถวซ้ำ) และ da_withdraw_fee ไม่มี units
    "da_trading_fee_buy": "INCREASE",
    "da_trading_fee_sell": "DECREASE",
    "da_spread_buy": "IGNORE",
    "da_spread_sell": "IGNORE",
    "da_withdraw_fee": "IGNORE",
}

WATCHLIST_WINDOW_DAYS = 90     # CF-05 / R6.2 — ตัดสินใจแล้วในชีต "รอตอบ" ข้อ 6
TXN_HISTORY_MONTHS = 6         # R1.15

# ==========================================================================
# STEP4 — venue / suffix / MIC
# ==========================================================================

VENUE_PREFIXES = {"NYS", "NXB", "HKG"}          # R4.1 / R3.21 — ตัดออกก่อนเสมอ

SUFFIX_TO_MIC = {                                # R4.5, R4.6
    "N": "xnys",
    "NB": "xnas",
    "HK": "xhkg",
    "P": "arcx",
    "A": "xase",
    "TO": "XTSX",
    "V": "TSXV",
    "T": "XTKS",
    "L": "xlon",
    "PA": "xpar",
    "DE": "xetr",
    "SW": "xswx",
    "AX": "XASX",
    "SI": "SGX",
    "KS": "XKRX",
    "TW": "XTAI",
    "VN": "XSTC",
    # GAP-14 — suffix ที่พบในข่าวจริงแต่ไม่อยู่ในผลสำรวจ 137 รหัสของ STEP3
    # (แปลงผิด MIC จะไม่เกิดการจับคู่ผิด เพราะเทียบรหัสแบบตรงตัว — แค่ไม่ match)
    "O": "xnas",     # Refinitiv NASDAQ  AAPL.O TSLA.O
    "S": "xswx",     # สวิส              CFR.S
    "SZ": "XSHE",    # เซินเจิ้น          300750.SZ
    "SS": "XSHG",    # เซี่ยงไฮ้           601012.SS
    "FP": "xpar",    # ปารีส (Bloomberg) MC.FP
    "MI": "XMIL",
    "AS": "XAMS",
    "HE": "xhel",
    "MC": "xmce",
    "KQ": "KOSDAQ",
    "VX": "xvtx",
    "NS": "xnse",    # NSE อินเดีย  HCLT.NS TCS.NS WIPR.NS
    "BO": "xbom",
}

SUFFIX_UNSUPPORTED = {"CHI"}                     # R4.7 — Chi-X ยุโรป รากรหัสคนละแบบ

# GAP-15 — ฝั่งลูกค้ามีรหัสแบบ Bloomberg ปนอยู่ด้วย ("ACV VN", "7974.JP", "004990 KS")
# เป็นตัวเดียวกับที่มีอยู่ในรูปแบบ TICKER:MIC ทำให้สินทรัพย์เดียวถูกนับเป็นสองตัว (R1.2)
# คั่นด้วยช่องว่างหรือจุดก็ได้ ตารางนี้บอกว่ารหัสประเทศชี้ไปตลาดไหนได้
BLOOMBERG_COUNTRY = {
    "VN": ("xstc", "upcom"),
    "JP": ("xtks",),
    "KS": ("xkrx", "kosdaq"),
    "ID": ("xidx",),
    "AU": ("xasx",),
    "CA": ("xtsx", "tsxv"),
    "MY": ("xkls",),
    "SG": ("sgx",),
    "PM": ("xphs",),
    "CN": ("xshe", "xshg", "cnsgse"),
    "HK": ("xhkg",),
    "TT": ("xtai",),
    "SW": ("xswx", "xvtx"),
    "FP": ("xpar",),
    "LN": ("xlon", "lse"),
    "GR": ("xetr",),
    "SM": ("xmce",),
    "US": ("xnas", "xnys", "arcx", "bats", "xase"),
}

# ตลาดสหรัฐ — ใช้ตัดสินกรณี underlying ของ options CBOE ชนกันข้ามตลาด (R4.30)
US_MICS = ("xnas", "xnys", "arcx", "bats", "xase")
PAD5_MIC = {"xhkg"}                              # R4.6 — ฮ่องกงเติมศูนย์ครบ 5 หลัก
# ช่วงที่เก็บข่าว — RM ใช้ย้อนหลังไม่เกินสองสัปดาห์ ของเก่ากว่านั้นไม่ถูกเปิดดู
# แต่ยังทำให้ทุกงานที่กวาดทั้งตารางช้าลงเรื่อย ๆ (จับคู่ใหม่ ดึงเนื้อหาเต็ม)
# ตัวเลขนี้คุมทั้งการลบอัตโนมัติหลังดึงข่าว และปุ่มช่วงวันบนหน้าจอ
RETENTION_DAYS = 14

THAI_SUFFIX = "BK"                               # R4.2
OFFSHORE_FUND_SUFFIX = "MFU"                     # ช่องว่าง: ไม่มีกฎใน STEP4 (ดู SPEC_GAPS)
OPTIONS_MIC = "xcbf"                             # R4.29

TFEX_MONTH_CODES = {                             # R4.19
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}

# R4.25 — เลขผู้ออก DR ที่พบจริง (ไม่ใช่แค่ 80)
DR_ISSUER_SUFFIXES = {"80", "23", "19", "01", "06", "03", "24", "13", "11", "30"}

# R4.15 / R4.27 — ตารางชื่อพ้อง DR (ชื่อเต็มบริษัท -> รหัสหุ้นแม่)
# ทุกแถวเป็นระดับ inferred และถูกตรวจกับรายการสินทรัพย์ในพอร์ตก่อนใช้จริง
# (refdata.build จะทิ้งแถวที่ไม่พบรหัสปลายทางในพอร์ต แล้วรายงานเป็น unmapped)
DR_NAME_ALIAS = {
    # ฮ่องกง
    "TENCENT": "00700:xhkg", "XIAOMI": "01810:xhkg", "MEITUAN": "03690:xhkg",
    "PINGAN": "02318:xhkg", "BYDCOM": "01211:xhkg", "CATL": "03750:xhkg",
    "GEELY": "00175:xhkg", "TRIPCOM": "09961:xhkg", "SMIC": "00981:xhkg",
    "HUAHONG": "01347:xhkg", "ANTA": "02020:xhkg", "CMBANK": "03968:xhkg",
    "AIA": "01299:xhkg", "ICBC": "01398:xhkg", "CHMOBILE": "00941:xhkg",
    "KUAISH": "01024:xhkg", "POPMART": "09992:xhkg", "WUXIAT": "02268:xhkg",
    "CNRE": "01918:xhkg",
    # สหรัฐ / ยุโรป — R4.15 ตัวอย่างจาก spec + ชื่อเต็มที่ DR ใช้
    "MICRON": "MU:xnas", "INTEL": "INTC:xnas", "FABRINET": "FN:xnys",
    "SPACEX": "SPCX:xnas", "TSEMI": "TSEM:xnas", "SEAGATE": "STX:xnas",
    "VISA": "V:xnys", "LVMH": "MC:xpar", "LOREAL": "OR:xpar",
    "SANOFI": "SAN:xpar", "NOVOB": "NVO:xnys", "ESTEE": "EL:xnys",
    "SYNP": "SNPS:xnas", "JPMUS": "JPM:xnys", "BRKB": "BRK.B:xnys",
    # ญี่ปุ่น
    "KEYENCE": "6861:XTKS", "FANUC": "6954:XTKS", "NINTENDO": "7974:XTKS",
    "ITOCHU": "8001:XTKS", "SANRIO": "8136:XTKS", "ADVANT": "6857:XTKS",
    "UNIQLO": "9983:XTKS", "KIOXIA": "285A:XTKS",
    # สิงคโปร์
    "DBS": "D05:SGX",
}

# ==========================================================================
# STEP3 — content_type / importance / urgency / role
# ==========================================================================

CONTENT_TYPE_BY_SUBCATEGORY = {
    # company_news
    "earnings": "company_news",
    "company-update": "company_news",
    "high-conviction": "company_news",
    "stock-note": "company_news",
    "ipo": "company_news",
    "offshore-stock-update": "company_news",
    "thai-stock-update": "company_news",
    # daily_brief
    "morning-brief": "daily_brief",
    "evening-brief": "daily_brief",
    "swdpaper": "daily_brief",
    # derivatives_daily
    "swdtfex": "derivatives_daily",
    # sector_analysis
    "industry-analysis": "sector_analysis",
    "industry-cluster": "sector_analysis",
    # macro
    "macro": "macro",
    "fx-rates-monthly": "macro",
    "rising-star": "macro",
    # top_picks
    "thai-stock-short-term-top-picks": "top_picks",
    "offshore-stock-short-term-top-picks": "top_picks",
    "mutual-fund-short-medium-term-top-picks": "top_picks",
    "satellite-call": "top_picks",
    "funds-top-picks-long-term": "top_picks",
    "thai-stocks-top-picks-trading": "top_picks",
    "thai-stocks-playlists": "top_picks",
    "etfs-top-picks-long-term": "top_picks",
    "etfs-playlists": "top_picks",
    # fund_update
    "weekly-fund-update": "fund_update",
    "fund-review": "fund_update",
    "funds-playlists": "fund_update",
    # portfolio_update
    "rebalance-report": "portfolio_update",
    "intel-monthly-report": "portfolio_update",
    # digital_asset
    "digital-assets-trading": "digital_asset",
    "digital-assets-weekly": "digital_asset",
    "ico": "digital_asset",
    # special_report
    "special-report-thai-stocks": "special_report",
    "special-report-offshore-stocks": "special_report",
    "special-report-global-multi-asset-strategy": "special_report",
    "megatrends": "special_report",
    "guru-invest": "special_report",
    "wealthweekend": "special_report",
    "weekly-technical": "special_report",
    # outlook
    "quarterly-outlook": "outlook",
    "yearbook": "outlook",
    # company_story
    "company-history": "company_story",
    # tax
    "tax-corner": "tax",
    "rmf": "tax",
    "thaiesg": "tax",
    "investment-income-tax": "tax",
    "tax-101": "tax",
    # reference_data — role=reference ไม่ส่งใคร
    "recommendation-summary": "reference_data",
    "warrant-report": "reference_data",
    "monthly-report": "reference_data",
    # ASSUMED — us-options อยู่ในขอบเขต STEP2 แต่ STEP3 ไม่ได้ map ไว้
    "us-options": "options_update",
    # GAP-13 — slug ที่ API ส่งมาจริง ไม่ตรงกับที่ STEP2 จดไว้
    "usoptions": "options_update",       # STEP2 จดเป็น us-options
    "digital-asset": "digital_asset",    # STEP2 จดเป็น digital-assets-trading
}

# A-21 importance 1-5. ค่าที่ spec ระบุ: 5=earnings/corporate action,
# 4=company_news อื่น + derivatives_daily + top_picks, 1=outlook/company_story/tax
# ระดับ 3 กับ 2 spec เว้นว่าง -> ASSUMED
IMPORTANCE_BY_CONTENT_TYPE = {
    "company_news": 4,
    "derivatives_daily": 4,
    "top_picks": 4,
    "sector_analysis": 3,      # ASSUMED
    "fund_update": 3,          # ASSUMED
    "portfolio_update": 3,     # ASSUMED
    "digital_asset": 3,        # ASSUMED
    "daily_brief": 3,          # ASSUMED
    "options_update": 3,       # ASSUMED
    "macro": 2,                # ASSUMED
    "special_report": 2,       # ASSUMED
    "outlook": 1,
    "company_story": 1,
    "tax": 1,
    "reference_data": 1,
}

# importance 5 ผูกกับ subcategory ไม่ใช่ content_type (spec: "earnings และ corporate action")
IMPORTANCE_BY_SUBCATEGORY = {"earnings": 5}

# A-22 urgency. spec ระบุแค่ now -> ที่เหลือ ASSUMED
URGENCY_BY_CONTENT_TYPE = {
    "company_news": "now",
    "derivatives_daily": "now",
    "daily_brief": "this_week",       # ASSUMED
    "top_picks": "this_week",         # ASSUMED
    "digital_asset": "this_week",     # ASSUMED
    "sector_analysis": "this_week",   # ASSUMED
    "fund_update": "this_week",       # ASSUMED
    "portfolio_update": "this_week",  # ASSUMED
    "options_update": "this_week",    # ASSUMED
    "macro": "low",                   # ASSUMED
    "special_report": "low",          # ASSUMED
    "outlook": "low",                 # ASSUMED
    "company_story": "low",           # ASSUMED
    "tax": "low",                     # ASSUMED
    "reference_data": "low",
}

# urgency ที่ผูกกับ subcategory ตรง ๆ — ว่างไว้ เติมจาก overrides.json ตอนอนุมัติหมวดใหม่
# (A-22 ผูก urgency กับ content_type แต่หมวดใหม่ที่คนเพิ่งจัดชั้นควรระบุได้ทีละหมวด)
URGENCY_BY_SUBCATEGORY: dict[str, str] = {}

REFERENCE_SUBCATEGORIES = {"recommendation-summary", "warrant-report", "monthly-report"}

# R2.2 — ห้ามใช้ product_type ของ Morning Brief (ติดมาเป็น Mutual Fund แต่เนื้อหาเป็นหุ้น)
PRODUCT_TYPE_BLOCKED_SUBCATEGORIES = {"morning-brief"}

# หมวดที่เลิกผลิต / ตัดออก (STEP2)
DISCONTINUED_SUBCATEGORIES = {
    "bitesforbreakfast", "bitesfordinner", "glb-morning", "kohsue", "offshore-stock",
}
OUT_OF_SCOPE_SUBCATEGORIES = {
    "product-basic-knowledge", "easyfinance", "inspiration",
    # DR ถูกตัดออกจากขอบเขตแล้ว (STEP3 ชีตแปลง asset class — Alternative Assets)
    "dr",
    # Invest Snack เลื่อนไป Phase 2 (การตัดสินใจข้อ 6)
    "start-your-first-investment",
}

# STEP3 ชีต "ที่มาต่อหมวด" — หมวดที่สกัดจาก summary แล้วถือเป็น confirmed ได้
# (ชื่อเหรียญปรากฏตรงตัวแบบ BTCUSD ในสรุป ไม่ใช่การอนุมาน)
# หมวดอื่นที่สกัดจาก summary เช่น Brief และ ICO Report ยังเป็น inferred ต้องมีคนตรวจ
SUMMARY_CONFIRMED_SUBCATEGORIES = {
    "digital-assets-trading", "digital-assets-weekly", "digital-asset",
}

# GAP-18 — TFEX Daily ใส่รหัสสัญญาไว้ใน summary_plain แล้ว
# ("Daily Top Picks : LONG S50U26 ; LONG GOU26 ; SHORT USDU26")
# STEP3 จัดหมวดนี้ไว้ในกลุ่ม "ต้องดึง HTML" แต่จริง ๆ ใช้ API พอ — 10 ชิ้น/สัปดาห์
TFEX_SUBCATEGORIES = {"swdtfex"}

# GAP-17 — บทวิเคราะห์รายอุตสาหกรรมไม่เอ่ย ticker แต่ใส่ชื่อกลุ่มไว้ในหัวข้อ
# spec สั่ง "จับคู่ด้วย sector" แต่ไม่มีกฎว่าจะได้ sector มาจากไหนเมื่อไม่มี ticker
# ใช้เฉพาะกับหัวข้อของ sector_analysis เท่านั้น และทุกคำยาว >= 5 ตัวอักษร ตามหลัก R3.37
SECTOR_BY_THAI_KEYWORD = {
    "ธนาคาร": "Banking",
    "เงินทุนและหลักทรัพย์": "Finance & Securities",
    "ประกัน": "Insurance",
    "พลังงาน": "Energy & Utilities",
    "โรงกลั่น": "Energy & Utilities",
    "โรงไฟฟ้า": "Energy & Utilities",
    "ปิโตรเคมี": "Petrochemicals & Chemicals",
    "ค้าปลีก": "Commerce",
    "พาณิชย์": "Commerce",
    "อาหารและเครื่องดื่ม": "Food & Beverage",
    "เครื่องดื่ม": "Food & Beverage",
    "เกษตร": "Agribusiness",
    "โรงพยาบาล": "Health Care Services",
    "การแพทย์": "Health Care Services",
    "อสังหาริมทรัพย์": "Property Development",
    "นิคมอุตสาหกรรม": "Property Development",
    "ท่องเที่ยว": "Tourism & Leisure",
    "โรงแรม": "Tourism & Leisure",
    "ขนส่ง": "Transportation & Logistics",
    "สายการบิน": "Transportation & Logistics",
    "ชิ้นส่วนอิเล็กทรอนิกส์": "Electronic Components",
    "อิเล็กทรอนิกส์": "Electronic Components",
    "วัสดุก่อสร้าง": "Construction Materials",
    "รับเหมาก่อสร้าง": "Construction Materials",
    "บรรจุภัณฑ์": "Packaging",
    "ยานยนต์": "Automotive",
    "สื่อสาร": "Information & Communication Technology",
    "โทรคมนาคม": "Information & Communication Technology",
    "กองทุนโครงสร้างพื้นฐาน": "Infrastructure Fund",
}
SECTOR_KEYWORD_SUBCATEGORIES = {"industry-analysis", "industry-cluster"}

# R3.1-R3.5 — หมวดที่ต้องซอยเป็นข้อย่อย
SEGMENTED_SUBCATEGORIES = {"morning-brief", "evening-brief"}
SEGMENT_MIN, SEGMENT_MAX = 4, 9        # R3.2 — นอกช่วงนี้ให้รายงานว่าผิดปกติ

# A-14 — article_asset_class -> asset_class ฝั่งลูกค้า (STEP3 ชีต "แปลง asset class")
ARTICLE_ASSET_CLASS_MAP = {
    "Thai Stock": ["EQUITY_TH"],
    "Offshore Stock": ["EQUITY_OFFSHORE"],
    "TFEX": ["TFEX"],
    "Digital Asset": ["DIGITAL_ASSET"],
    "Mutual Fund": ["FUND_DIY", "FUND_ROBO"],
    "ETF": ["FUND_OFFSHORE"],
    "Offshore Mutual Fund": ["FUND_OFFSHORE"],
    "Economics": ["*"],
    "All": ["*"],
    "Derivatives": ["TFEX", "OPTIONS_OFFSHORE"],
    "Alternative Assets": [],          # ห้ามเดา
}
# ตัวช่วยแยกกรณีกำกวมด้วย subcategory
ASSET_CLASS_OVERRIDE_BY_SUBCATEGORY = {
    "rebalance-report": ["FUND_ROBO"],
    "intel-monthly-report": ["FUND_ROBO"],
    "us-options": ["OPTIONS_OFFSHORE"],
    "swdtfex": ["TFEX"],
}

# ==========================================================================
# STEP5 — persona
# ==========================================================================

PERSONA_BY_DOMINANT = {          # R5.2
    "DIGITAL_ASSET": "CRYPTO",
    "TFEX": "DERIVATIVES",
    "OPTIONS_OFFSHORE": "DERIVATIVES",
    "EQUITY_OFFSHORE": "US_OFFSHORE",
    "FUND_OFFSHORE": "US_OFFSHORE",
    "EQUITY_TH": "THAI_STOCK",
    "BOND_TH": "BOND",
    "BOND_OFFSHORE": "BOND",
    "STRUCTURED_NOTE": "THAI_STOCK",
}

PERSONA_LABELS = {
    "US_OFFSHORE": ("US/Offshore หุ้นนอก", "US / Offshore Equity"),
    "FUND_DIY": ("Fund DIY เลือกเอง", "Fund DIY"),
    "THAI_STOCK": ("Thai Stock หุ้นไทย", "Thai Stock"),
    "DORMANT": ("Dormant เงียบหาย", "Dormant"),
    "CRYPTO": ("Crypto คริปโต", "Crypto"),
    "FUND_ROBO": ("Fund Robo", "Fund Robo"),
    "DERIVATIVES": ("Derivatives อนุพันธ์", "Derivatives"),
    "BOND": ("Bond ตราสารหนี้", "Bond"),
    "NO_PORTFOLIO": ("ไม่มีพอร์ต/ไม่ระบุ", "No portfolio"),
}

TRADE_FREQ_BANDS = [(0, "inactive"), (1, "passive"), (11, "active"), (51, "very_active")]  # CF-06
PORTFOLIO_TIERS = [(20_000_000, "vip"), (5_000_000, "large"), (1_000_000, "mid"), (0, "small")]  # CF-08
DORMANT_DAYS = 90                                                                          # R5.1

# ==========================================================================
# STEP6 — matching
# ==========================================================================

LEVEL_WEIGHT = {          # R6.1 - R6.6
    "L1_HOLD": 100,
    "L2_WATCH": 60,
    "L3_SECTOR": 40,
    "L4_RELATED": 30,
    "L5_ASSET": 20,
    "L6_MACRO": 10,
}

MIN_SECTOR_WEIGHT = 0.05          # R6.3 — ตัดสินใจแล้ว (ชีต "รอตอบ" ข้อ 5 เสนอ 5-10%)
SCORE_THRESHOLD = 50.0            # R6.14 — ค่าคงที่ของระบบ แก้ได้ที่นี่ที่เดียว
URGENCY_FACTOR = {"now": 1.5, "this_week": 1.0, "low": 0.7}   # R6.10
RECENCY_FACTOR = [(7, 1.3), (30, 1.1)]                        # R6.11
MULTI_HIT_BONUS = 0.10                                        # โบนัสต่อ hit ที่เกินตัวแรก
MAX_LEVEL_BY_MODE = {"realtime": 2, "digest": 4}              # R6.12 / R6.13
REALTIME_CONTENT_TYPES = {"company_news"}                     # R6.12

# R6.16 — persona ไหนรับ content_type อะไร (STEP5/STEP6 ชีต "Persona กับข่าว")
PERSONA_CONTENT_MAP = {
    "US_OFFSHORE": {"company_news", "company_story", "daily_brief", "special_report",
                    "macro", "outlook", "top_picks", "options_update"},
    "THAI_STOCK": {"company_news", "sector_analysis", "top_picks", "daily_brief",
                   "special_report", "macro", "outlook", "derivatives_daily"},
    "FUND_DIY": {"fund_update", "top_picks", "special_report", "outlook", "tax", "macro"},
    "FUND_ROBO": {"portfolio_update"},          # ห้ามส่งข่าวรายกอง
    "CRYPTO": {"digital_asset", "macro", "special_report", "outlook"},
    "DERIVATIVES": {"derivatives_daily", "options_update", "company_news", "macro",
                    "special_report"},
    "BOND": {"company_news", "macro"},          # ใช้ข่าวหุ้นบริษัทผู้ออกแทน
    "DORMANT": set(),                           # ไม่ฝืนส่ง
    "NO_PORTFOLIO": set(),
}

# ==========================================================================
# STEP8 — ความรุนแรงของสิ่งที่ระบบอ่านไม่ออก
# ==========================================================================
#
# ตาราง unmapped เดิมเรียงตาม "จำนวนครั้งที่เจอ" ซึ่งบอกไม่ได้ว่าควรแก้อะไรก่อน
# รหัสที่เจอ 84 ครั้งแต่มีคนถือ 2 คน สำคัญน้อยกว่ารหัสที่เจอ 3 ครั้งแต่มีคนถือ 200 คน
# ตารางนี้จัดชั้นตามผลกระทบ ไม่ใช่ตามความถี่ (ดู /api/reports/unmapped)

UNMAPPED_NEW_DAYS = 7            # เจอครั้งแรกภายในกี่วันถือว่า "ของใหม่"

# bucket -> (ระดับ, ผลกระทบเป็นภาษาคน, ผลกระทบภาษาอังกฤษ)
UNMAPPED_SEVERITY = {
    # ---- สูง: กระทบทั้งหมวด หรือทำให้ข้อมูลผิดความจริง ----
    "subcategory": ("high",
                    "หมวดใหม่ที่ระบบไม่รู้จัก — บทความทั้งหมวดถูกข้ามไป ไม่มีชิ้นไหนเข้าระบบเลย",
                    "unknown content category — every article in it is skipped entirely"),
    "customer_key": ("high",
                     "แถวที่ระบุเจ้าของไม่ได้ ถ้าเก็บไว้จะรวมเป็นลูกค้าปลอมหนึ่งคน",
                     "rows with no owner; keeping them would invent a customer"),
    "txn_type": ("high",
                 "ไม่รู้ว่าซื้อหรือขาย กระทบ watchlist ความถี่เทรด และ persona",
                 "direction unknown; affects watchlist, trade frequency and persona"),
    # ---- กลาง: ลูกค้าบางกลุ่มไม่ได้รับข่าวที่ควรได้ ----
    "asset_class": ("medium",
                    "จัดเข้า OTHER ทำให้สัดส่วนพอร์ตและ persona เพี้ยน",
                    "falls into OTHER, skewing asset mix and persona"),
    "holding_code": ("medium",
                     "ลูกค้าที่ถือรหัสนี้ไม่เคยได้รับข่าวที่เกี่ยวข้องเลย",
                     "customers holding this never receive related news"),
    "news_entity": ("medium",
                    "บทความเอ่ยถึงสินทรัพย์นี้ แต่แปลงเป็นรหัสกลางไม่ได้",
                    "the article names this instrument but it cannot be normalised"),
    "tfex": ("medium",
             "สถานะอนุพันธ์ไม่ครบ ประกอบสถานะที่เปิดอยู่ไม่ได้",
             "incomplete derivative history; open position cannot be derived"),
    # ---- ต่ำ: กระทบคุณภาพ ไม่กระทบรายชื่อที่ส่งถึง RM ----
    "segment": ("low",
                "ซอย Brief ได้จำนวนข้อผิดปกติ ตรวจรูปแบบต้นทาง",
                "Brief split into an unusual number of items; check the source format"),
    "full_text": ("low",
                  "ดึงเนื้อหาเต็มไม่ได้ ยังจับคู่จากสรุปได้ตามปกติ",
                  "full text unavailable; matching still runs on the summary"),
}
UNMAPPED_SEVERITY_FALLBACK = ("medium", "ยังไม่ได้จัดชั้นความรุนแรง", "not yet classified")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# ==========================================================================
# ช่องว่างของ spec ที่ระบบเติมเอง — รายงานออกหน้าจอ ห้ามเงียบ
# ==========================================================================

SPEC_GAPS = [
    {
        "id": "GAP-01", "ref": "STEP3 A-21",
        "th": "importance ระดับ 3 และ 2 ไม่มีค่าใน spec (ช่องว่างเปล่า)",
        "en": "STEP3 leaves importance levels 3 and 2 blank",
        "assumed": "sector_analysis/fund_update/portfolio_update/digital_asset/daily_brief = 3, "
                   "macro/special_report = 2",
    },
    {
        "id": "GAP-02", "ref": "STEP3 A-22",
        "th": "urgency this_week และ low ไม่มีค่าใน spec (ระบุแค่ now)",
        "en": "STEP3 only defines urgency=now; this_week and low are blank",
        "assumed": "daily_brief/top_picks/digital_asset/sector_analysis/fund_update/"
                   "portfolio_update = this_week, ที่เหลือ = low",
    },
    {
        "id": "GAP-03", "ref": "STEP2 / STEP3",
        "th": "subcategory us-options อยู่ในขอบเขต แต่ไม่มีใน content_type map",
        "en": "us-options is in scope per STEP2 but missing from the STEP3 content_type map",
        "assumed": "สร้าง content_type ใหม่ options_update, importance 3, urgency this_week",
    },
    {
        "id": "GAP-04", "ref": "STEP4 A2",
        "th": "รหัสกองทุนต่างประเทศลงท้าย .MFU (22 รหัสในพอร์ต) ไม่มีกฎแปลง",
        "en": "Offshore fund codes ending .MFU (22 in the book) have no mapping rule",
        "assumed": "ตัด .MFU ออกแล้วถือเป็นรหัสกองทุน ระดับ inferred",
    },
    {
        "id": "GAP-05", "ref": "STEP4 / STEP2",
        "th": "KIKO ระบุ underlying ในรหัสอยู่แล้ว เช่น 'BDMS KIKO 27866' แต่ spec บอกว่าไม่มีเนื้อหารองรับ",
        "en": "KIKO codes already embed the underlying Thai stock; spec assumed no coverage",
        "assumed": "ถอดคำแรกเป็น underlying แล้วใช้ข่าวหุ้นตัวนั้น ติดป้ายว่าเป็น KIKO",
    },
    {
        "id": "GAP-06", "ref": "STEP2 API Spec",
        "th": "Cafe Invest API ตอบ 403 ถ้าไม่ส่ง header User-Agent — spec ไม่ได้ระบุ",
        "en": "The Cafe Invest API returns 403 without a User-Agent header; not documented",
        "assumed": "ส่ง User-Agent + Referer ทุกครั้ง",
    },
    {
        "id": "GAP-07", "ref": "PROJECT STATUS การตัดสินใจ #20 vs STEP3 R3.2",
        "th": "การตัดสินใจข้อ 20 บอก Brief ซอย 6 ข้อคงที่ แต่ R3.2 ห้ามสมมติว่า 6 (จริง 5-7)",
        "en": "Decision #20 says Brief splits into exactly 6 items; R3.2 forbids assuming 6",
        "assumed": "ยึด R3.2 — ซอยตามที่พบจริง รายงานเมื่อออกนอกช่วง 4-9",
    },
    {
        "id": "GAP-08", "ref": "PROJECT STATUS ระบบเลขกฎ",
        "th": "ชีตเขียน 'รวม 104 กฎ' สำหรับ STEP1-4 แต่ 20+9+40+47 = 116 และ STEP5 มี R5.4 ด้วย (ไม่ใช่ 3 ข้อ)",
        "en": "Rule-count sheet says 104 for STEP1-4 but 20+9+40+47 = 116; STEP5 has 4 rules not 3",
        "assumed": "รวมทั้งโปรเจกต์ 136 กฎ ถูกแล้ว เฉพาะยอดย่อยผิด",
    },
    {
        "id": "GAP-17", "ref": "STEP3 ที่มาต่อหมวด / R6.3",
        "th": "บทวิเคราะห์รายอุตสาหกรรม (3.16 ชิ้น/สัปดาห์) spec สั่งให้ 'จับคู่ด้วย sector' แต่ไม่มีกฎว่า "
              "จะได้ sector มาจากไหน — A-19 ให้ sector มาจาก ticker ผ่าน Coverage List เท่านั้น "
              "และบทความกลุ่มนี้ไม่เอ่ย ticker ผลคือ L3 ไม่เคยทำงาน",
        "en": "Industry analysis is meant to match by sector, but A-19 only derives sector from a ticker "
              "and these articles name none — so L3 never fires",
        "assumed": "อ่านชื่อกลุ่มจากหัวข้อบทความ (ธนาคาร / พลังงาน (โรงกลั่น) / ท่องเที่ยว (โรงแรม)) "
                   "ด้วยคำยาว 29 คำ ใช้เฉพาะหัวข้อของหมวดนี้ และบันทึกคำที่ทำให้ติดไว้ทุกครั้ง (R3.39)",
    },
    {
        "id": "GAP-18", "ref": "STEP3 ชีตแหล่งเนื้อหา",
        "th": "STEP3 จัด TFEX Daily (10 ชิ้น/สัปดาห์ มากที่สุดอันดับสาม) ไว้ในกลุ่ม 'ต้องดึง HTML' "
              "แต่ของจริง summary_plain มีรหัสสัญญาครบแล้ว "
              "('Daily Top Picks : LONG S50U26 ; LONG GOU26 ; SHORT USDU26') ใช้ API พอ",
        "en": "STEP3 puts TFEX Daily in the must-fetch-HTML group, but summary_plain already carries the "
              "full contract codes — the API alone is enough",
        "assumed": "สกัดรหัสสัญญาจากสรุปแล้วถอด underlying ตาม R4.18-R4.22 ระดับ confirmed "
                   "— ทำให้กลุ่ม Derivatives ครอบคลุมจาก 33% เป็น 100%",
    },
    {
        "id": "GAP-22", "ref": "STEP7 หลักการหน้าจอ ข้อ 6 / STEP3",
        "th": "STEP7 ข้อ 6 สั่งห้ามแสดงว่าข่าวดีหรือร้าย และ STEP3 ตัด sentiment ทิ้ง "
              "เพราะทดสอบ 300 บทความได้แค่ 42% และข่าวประธานลาออกถูกติดว่าบวก "
              "เจ้าของงานสั่งให้ใส่กลับ พร้อมประเด็นที่ควรคุยกับลูกค้า",
        "en": "STEP7 principle 6 forbids labelling news good or bad, and STEP3 cut sentiment after it "
              "scored 42% on 300 articles. The owner asked for it back, plus talking points.",
        "assumed": "ไม่ทำแบบที่ spec ลองแล้วพัง — ไม่เดาอารมณ์จากถ้อยคำ แต่ยกสิ่งที่มีแหล่งอ้างอิง 3 ชั้น "
                   "ชั้น 1 คำแนะนำที่ INVX ประกาศเอง (Top Picks เขียน แนะนำซื้อ/ขาย ไว้ในพาดหัว "
                   "และ rating + ราคาเป้าหมายจาก Coverage List) · ชั้น 2 ผลเทียบคาด "
                   "· ชั้น 3 โทนของพาดหัว ติดป้ายชัดว่าเป็นการอ่านถ้อยคำ และบังคับแสดงวลีที่ทำให้ติดเสมอ "
                   "· ข้อที่ spec ถูกที่สุดถูกรักษาไว้: บทความที่พูดสองทางจะไม่ถูกยุบเป็นค่าเดียว "
                   "(mixed) และประเด็นมหภาคที่กระทบคนละทาง ขึ้น position_dependent ไม่สรุปบวกหรือลบ "
                   "· ทุกวลีผ่านเกณฑ์ R3.38 (สูงสุด 13.4% จากเกณฑ์ 30%) · ประเด็นที่ควรคุย"
                   "ประกอบจากข้อเท็จจริงที่ระบบมีอยู่แล้ว ไม่เรียก LLM เพื่อให้ input เดิมได้ผลเดิม "
                   "และมีบรรทัดปิดท้ายเสมอว่านี่ไม่ใช่คำแนะนำการลงทุน RM ตัดสินใจเอง",
    },
    {
        "id": "GAP-21", "ref": "STEP8 ระดับความมั่นใจ / STEP3 A-18",
        "th": "spec กำหนดว่า entity ระดับ Inferred ต้องมีคนตรวจก่อนใช้จับคู่จริง ระบบนี้ยกประตูนั้นออก "
              "ตามที่เจ้าของงานสั่ง — ทุกบทความเข้าสู่การจับคู่ทันที ไม่มีอะไรรอคนกด "
              "แลกมาด้วยความเสี่ยงว่าถ้าสกัดชื่อผิด รายชื่อที่ผิดจะถึงมือ RM โดยไม่มีใครกรองก่อน",
        "en": "STEP8 requires human sign-off on inferred entities before matching goes live; that gate "
              "was removed by the owner's decision — every article now matches immediately",
        "assumed": "แทนด้วยตัวตรวจอัตโนมัติที่ 'ตรวจซ้ำเอง' ไม่ใช่ทวนกฎที่ขั้นสกัดกรองไปแล้ว: "
                   "R4.47 ต้องบันทึกว่าคำไหนทำให้จับได้ · R4.43/R4.44 ค้นคำนั้นซ้ำในเนื้อความจริง "
                   "และคำละตินต้องตรงแบบคำเต็ม · R3.38 คำที่ติดเกิน 30% ของคลังถือว่ากว้างเกิน "
                   "· R3.24 ไม่มีคนถือเป็นเรื่องปกติ ไม่ตัดเกรด "
                   "แล้วให้เกรด confirmed / auto_verified / weak พร้อมเหตุผลรายข้อ "
                   "เกรดไม่กั้นการจับคู่ แต่เปิดดูได้ที่หน้ารายงาน (หลักการข้อ 3) "
                   "ตัวตรวจเป็นกฎล้วน ไม่เรียก LLM เพื่อให้ input เดิมได้ผลเดิมทุกครั้ง "
                   "ผลจริง: ตัวตรวจนี้จับบั๊กของตัวสกัดได้ทันที 2 ตัว — alias 'SpaceX' ไปตรงกับ "
                   "'SpaceXAI' และ 'Meta' ไปตรงกับ 'MetaX' ส่งรายชื่อผิดถึง RM รวม 384 คน แก้แล้ว",
    },
    {
        "id": "GAP-20", "ref": "STEP6 R6.4 vs R6.12", "status": "แก้แล้ว 2026-08-04",
        "th": "R6.4 บอกว่า L4 ความสัมพันธ์หุ้นมีไว้แทน L3 สำหรับหุ้นนอกที่ไม่มี sector "
              "แต่ข่าวหุ้นนอกทั้งหมดเป็น content_type company_news ซึ่ง R6.12 บังคับให้เป็นโหมด "
              "realtime และจับได้แค่ L1-L2 — ผลคือ L4 ไม่มีทางทำงานเลย "
              "(ตรวจกับข้อมูลจริง: บทความ 48 ชิ้นที่เอ่ยหุ้นซึ่งมีความสัมพันธ์กัน เป็น realtime ทั้งหมด)",
        "en": "R6.4 positions L4 as the substitute for L3 on offshore stocks, but every offshore article "
              "is company_news, which R6.12 forces into realtime mode capped at L2 — so L4 can never fire",
        "assumed": "แก้แล้ว: L4 เปิดทำงานในโหมด realtime ได้แล้ว เฉพาะหุ้นต้นทางที่ไม่มี sector "
                   "(หุ้นนอก) เท่านั้น (matching.py) หุ้นไทยยังใช้ L3 ตามเดิม ไม่เปิด L4 เพิ่มให้ "
                   "คงเจตนาเดิมของ R6.12 ที่ข่าวด่วนหุ้นไทยควรถึงแค่คนถือตรง/watchlist",
    },
    {
        "id": "GAP-19", "ref": "STEP6 R6.5 vs R6.14", "status": "แก้แล้ว 2026-08-04",
        "th": "น้ำหนักฐาน L5 asset class = 20 แต่เกณฑ์ขั้นต่ำที่เสนอไว้ = 50 ทำให้ Rebalance Report / "
              "Monthly Report ไปไม่ถึงกลุ่ม Fund Robo เลย ขัดกับเจตนาของ R6.16 ที่ว่า Fund Robo "
              "ควรได้สองหมวดนี้ ปัญหาเดียวกันทำให้ Special Report (importance 2, urgency low) "
              "ไม่เคยผ่านเกณฑ์",
        "en": "L5 base weight 20 cannot clear the suggested threshold of 50, so Rebalance / Monthly "
              "Report never reach Fund Robo even though R6.16 says they should",
        "assumed": "แก้แล้ว: ยกน้ำหนักเฉพาะคู่ (Rebalance/Monthly Report, asset_classes เป็น "
                   "{FUND_ROBO} ล้วน) เป็น 55 (matching.py, FUND_ROBO_REPORT_WEIGHT) ไม่แตะน้ำหนัก "
                   "L5 มาตรฐานของ asset class อื่นหรือเกณฑ์คะแนนรวม — ยังเปิดอยู่: Special Report "
                   "(importance 2, urgency low) ยังไม่ผ่านเกณฑ์เหมือนเดิม เพราะไม่ใช่คู่ที่ R6.16 "
                   "ตั้งใจแก้",
    },
    {
        "id": "GAP-16", "ref": "STEP6 R6.7 / R6.8",
        "th": "spec บอกว่า 'บวกโบนัสถ้าแตะหลายจุด' แต่ไม่ได้ให้ขนาดโบนัส และไม่ได้บอกรูปโค้งของ "
              "f(มูลค่าถือ) — ที่ตั้งไว้ตอนนี้ โบนัส 10% ต่อ hit มีน้ำหนักมากกว่าส่วนต่างมูลค่าถือ "
              "เช่น คนถือ AMD 63 ลบ. (แตะจุดเดียว) อยู่ใต้คนถือ Tencent 0.9 ลบ. ที่แตะ 7 จุด "
              "ผลของ R6.8 ที่ spec ทดสอบไว้ (20 ลบ. มาก่อน 50,000) ยังถูกต้องเมื่อปัจจัยอื่นเท่ากัน",
        "en": "R6.7 says to add a bonus for multiple hits but never sizes it, and R6.8 never fixes the "
              "value curve. At 10% per hit the bonus outweighs holding-value differences.",
        "assumed": "log scale ของมูลค่าถืออิ่มตัวที่ 20 ลบ. (เกณฑ์ VIP ของ CF-08) และโบนัส 10% ต่อ hit "
                   "— ทั้งสองค่าปรับได้ที่ MULTI_HIT_BONUS และ _log_scale ควรให้ business ยืนยัน",
    },
    {
        "id": "GAP-15", "ref": "STEP1 R1.2 / STEP4",
        "th": "ฝั่งลูกค้ามีรหัสแบบ Bloomberg ปนอยู่ 28 รหัส (ACV VN, 7974.JP, 004990 KS, AALI.ID, "
              "DIV.CA, HOME PM) ซึ่งเป็นตัวเดียวกับที่มีอยู่ในรูปแบบ TICKER:MIC — R1.2 พบแค่ตัวอย่าง "
              "MC กับ MC:xpar แต่ของจริงกว้างกว่านั้นมาก ถ้าไม่รวมให้เป็นรูปแบบเดียว สินทรัพย์เดียว "
              "จะถูกนับเป็นสองตัวและจับคู่ไม่เจอ",
        "en": "The customer book mixes in 28 Bloomberg-style codes that duplicate instruments already "
              "present as TICKER:MIC — R1.2 only spotted the MC / MC:xpar case",
        "assumed": "ถอดรหัสประเทศแล้วคลี่กลับเป็นรหัสกลางจากพอร์ตเอง (VN→xstc/upcom, JP→xtks, "
                   "KS→xkrx, CA→xtsx/tsxv ฯลฯ) ถ้ารหัสประเทศชี้ได้ตลาดเดียวและไม่พบคู่ ตั้งเป็นตลาดนั้น "
                   "ระดับ inferred ถ้ากำกวมเข้า unmapped",
    },
    {
        "id": "GAP-11", "ref": "STEP6 R6.6",
        "th": "R6.6 บอกให้ถ่วงคะแนน L6 macro ตาม 'ความไวของพอร์ต' แต่ไม่ได้ให้สูตร",
        "en": "R6.6 requires weighting L6 by portfolio sensitivity but gives no formula",
        "assumed": "ตาราง MACRO_SENSITIVITY ใน matching.py — ดอกเบี้ยผูกกับตราสารหนี้+ธนาคาร, "
                   "น้ำมันผูกกับพลังงาน+ปิโตร+ขนส่ง, ค่าเงิน/สงครามการค้าผูกกับสินทรัพย์ต่างประเทศ, "
                   "เงินเฟ้อ = ทุกคน",
    },
    {
        "id": "GAP-12", "ref": "STEP2 API Spec / reference_pipeline.py",
        "th": "field category / sub_category / pillar / product_type ที่ API ส่งมาเป็น object "
              "{id, name, slug} ไม่ใช่ข้อความ — โค้ดตัวอย่างอ่านเป็นข้อความตรงๆ จะได้ค่าผิดทั้งหมด",
        "en": "category / sub_category / pillar / product_type come back as objects, not strings; "
              "the reference pipeline reads them as plain strings",
        "assumed": "อ่านจาก .slug (หมวด) และ .name (ชื่อแสดง)",
    },
    {
        "id": "GAP-13", "ref": "STEP2 บัญชีเนื้อหา / STEP3 R3.1",
        "th": "slug บางหมวดที่ API ส่งมาไม่ตรงกับที่ STEP2 จดไว้ (usoptions ไม่ใช่ us-options, "
              "digital-asset, dr, start-your-first-investment) และใน Brief จริง เลขข้อถัดไปติดกับ "
              "ตัวอักษรไทยของข้อก่อนหน้าโดยไม่เว้นวรรค",
        "en": "Live subcategory slugs differ from the STEP2 inventory, and Brief item numbers are "
              "glued to the previous item's text with no whitespace",
        "assumed": "เพิ่ม slug จริงเข้า map, ยก dr กับ start-your-first-investment ออกนอกขอบเขต, "
                   "และผ่อนกฎการซอยให้ไม่ต้องมีช่องว่างนำ (ยังกันเลขกลางประโยคตาม R3.4)",
    },
    {
        "id": "GAP-14", "ref": "STEP3 ชีตรูปแบบ ticker",
        "th": "ข่าวจริงมี suffix ที่ผลสำรวจ 137 รหัสไม่พบ: .O (NASDAQ), .SS (เซี่ยงไฮ้), "
              ".SZ (เซินเจิ้น), .S (สวิส) — R3.23 สั่งให้หยุดและแจ้งเตือน",
        "en": "Live articles use suffixes absent from the 137-symbol survey: .O, .SS, .SZ, .S",
        "assumed": "เพิ่มเข้าตาราง suffix แล้ว — แปลงผิด MIC ไม่ทำให้จับคู่ผิด เพราะเทียบตรงตัว",
    },
    {
        "id": "GAP-10", "ref": "STEP1 ชีต Enums / txn_direction",
        "th": "spec สั่ง 'ไม่นับ' แถว da_* ทุกแบบ แต่ไฟล์จริงไม่มีแถว Buy/Sell ของคริปโตเลย "
              "(digital_asset 25,149 แถว เป็น da_* ทั้งหมด) — ทำตามตรงตัวจะทิ้งประวัติเทรดคริปโต "
              "12,438 รายการ 548 ลบ. และลูกค้าคริปโต 302 คนกลายเป็น Dormant",
        "en": "STEP1 marks every da_* row as ignore, but the file has no crypto Buy/Sell rows at all; "
              "following it literally erases all crypto trading history",
        "assumed": "da_trading_fee_buy = INCREASE, da_trading_fee_sell = DECREASE "
                   "(สองชนิดนี้มี trading_value และ confirm_unit ครบ) ส่วน da_spread_* "
                   "(value = 0 ทุกแถว) และ da_withdraw_fee ยังไม่นับตามเดิม",
    },
    {
        "id": "GAP-09", "ref": "ข้อมูลจริง vs STEP5",
        "th": "ไฟล์ที่ส่งมามีลูกค้า 1,062 คน (portfolio) / 964 คน (txn) ไม่ใช่ 1,107 ตามเอกสาร",
        "en": "The delivered files contain 1,062 customers, not the 1,107 quoted in the docs",
        "assumed": "คำนวณ persona ใหม่จากไฟล์จริงทุกครั้งที่ ingest (R5.4)",
    },
]


# ==========================================================================
# ของที่คนอนุมัติแล้ว — เติมทับตารางข้างบนตอน import
# ==========================================================================
#
# ต้องอยู่ท้ายไฟล์ เพราะทุกตารางที่จะเติมต้องถูกประกาศไปแล้ว
# overrides.py ไม่ import ไฟล์นี้กลับ จึงไม่มี circular import
#
# หลักการ: override เพิ่มของใหม่ได้ แต่ไม่ลบกฎเดิม ทุกแถวมีบันทึกว่าใครรับเมื่อไหร่
# (ดู scripts/approve.py — ตรวจได้ด้วย `python -m scripts.approve list`)

from . import overrides as _ov  # noqa: E402

DR_NAME_ALIAS.update(_ov.dr_alias())

for _slug, _cfg in _ov.subcategory().items():
    CONTENT_TYPE_BY_SUBCATEGORY[_slug] = _cfg["content_type"]
    if _cfg.get("importance"):
        IMPORTANCE_BY_SUBCATEGORY[_slug] = int(_cfg["importance"])
    if _cfg.get("urgency"):
        URGENCY_BY_SUBCATEGORY[_slug] = _cfg["urgency"]

SECTOR_BY_THAI_KEYWORD.update(_ov.sector_keyword())

# R3.12/B3 ขยาย — sector ของหุ้นต่างประเทศ ไม่มีไฟล์ spec ต้นทาง (Coverage List คุมแค่หุ้นไทย)
# จึงเป็นของที่คนอนุมัติทั้งหมด ไม่ใช่กฎ (ดู scripts/seed_offshore_sector.py สำหรับชุดตั้งต้น)
OFFSHORE_SECTOR: dict[str, str] = {}
OFFSHORE_SECTOR.update(_ov.offshore_sector())

OVERRIDE_COUNTS = _ov.summary()

