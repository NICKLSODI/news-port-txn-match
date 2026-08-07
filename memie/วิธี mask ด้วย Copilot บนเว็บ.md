## วิธี Mask ข้อมูลลูกค้า ด้วย Copilot ใน Excel (บนเว็บ)

ทำผ่าน **account บริษัท** ที่ microsoft365.com เท่านั้น (ห้ามใช้ account ส่วนตัว)

ก๊อป prompt แต่ละกล่องไปวางในช่อง Copilot ทีละอัน ตามลำดับ

---

## เป้าหมายการส่งข้อมูล

สุดท้ายต้องได้ทั้งหมด **3 ไฟล์**

### 1. Portfolio_MASKED.xlsx ✅ ส่งให้ Dev ได้

ประกอบด้วยข้อมูลธุรกิจและรหัสแทนตัวตนเท่านั้น

### 2. TXN_MASKED.xlsx ✅ ส่งให้ Dev ได้

ประกอบด้วยข้อมูลธุรกรรมและรหัสแทนตัวตนเท่านั้น

### 3. CUSTOMER_MAPPING.xlsx 🔒 ห้ามส่ง Dev

เก็บข้อมูลสำหรับแปลงกลับหาลูกค้าจริง

---

## เตรียมตัวก่อนเริ่ม

- Copy ไฟล์ต้นฉบับ (Portfolio, TXN) เก็บสำรองไว้อีกที่ก่อน
- เข้า microsoft365.com → Sign in ด้วย account บริษัท
- เปิดไฟล์ Portfolio (ebiz2 asof Jun 26).xlsx
- กดปุ่ม Copilot มุมขวาบน

---

# ไฟล์ที่ 1: Portfolio

## Prompt 1 — สร้างตารางแปลงรหัสลูกค้า

ในตารางนี้ ช่วยสร้างชีตใหม่ชื่อ customer_map

รวบรวมค่า cardid ที่ไม่ซ้ำกันทั้งหมด

และเพิ่มคอลัมน์ดังนี้

- cardid
- customer_key

โดยใส่ customer_key เรียงลำดับในรูปแบบ

CUST00001
CUST00002
CUST00003

ไปเรื่อย ๆ

## Prompt 2 — ใส่ customer_key แทน cardid

ในชีตข้อมูลหลัก ช่วยเพิ่มคอลัมน์ใหม่ชื่อ customer_key

โดยใช้ XLOOKUP ดึงรหัส CUST จากชีต customer_map มาจับคู่กับ cardid ของแต่ละแถว

## Prompt 3 — แปลงเลขบัญชีเป็นรหัส

ช่วยสร้างชีตใหม่ชื่อ account_map

รวบรวมค่า account ที่ไม่ซ้ำกัน

แล้วสร้าง account_key ในรูปแบบ

ACCT00001
ACCT00002
ACCT00003

จากนั้นเพิ่มคอลัมน์ account_key ในชีตข้อมูลหลัก

โดยใช้ XLOOKUP จับคู่จาก account_map

## Prompt 4 — แปลงชื่อ RM เป็นรหัส

ช่วยสร้างชีตใหม่ชื่อ rm_map

รวบรวมค่า marketing_name_th ที่ไม่ซ้ำกัน

แล้วสร้าง rm_id ในรูปแบบ

RM001
RM002
RM003

จากนั้นเพิ่มคอลัมน์ rm_id ในชีตข้อมูลหลัก

โดยใช้ XLOOKUP จับคู่จาก rm_map

## Prompt 5 — แปลงสูตรเป็นค่าคงที่

ช่วยแปลงคอลัมน์

- customer_key
- account_key
- rm_id

ให้กลายเป็นค่าคงที่ (Paste as Values)

## Prompt 6 — ลบคอลัมน์ PII เดิม

ช่วยลบคอลัมน์ต่อไปนี้ออกจากชีตข้อมูลหลัก

- cardid
- account
- marketing_name_th

ห้ามลบคอลัมน์อื่น

ตัวอย่างคอลัมน์ที่ต้องคงไว้:

- level3_team
- level4_team
- product_lv1
- product_lv2
- product_txt_key
- product_code
- product_name
- aum
- thb_unrealized_avg
- record_date
- customer_key
- account_key
- rm_id

## Prompt 7 — แยกไฟล์ Mapping

ช่วยสร้างไฟล์ใหม่ชื่อ CUSTOMER_MAPPING.xlsx

แล้วย้ายชีตต่อไปนี้ไปเก็บในไฟล์ใหม่

- customer_map
- account_map
- rm_map

โดยลบชีตทั้ง 3 ออกจากไฟล์ Portfolio หลังจากย้ายเสร็จ

## เซฟ

ไฟล์ที่ได้ต้องเป็น

- Portfolio_MASKED.xlsx
- CUSTOMER_MAPPING.xlsx

---

# ไฟล์ที่ 2: TXN

สำคัญมาก

เปิดไฟล์ TXN (ebiz2 YTD).xlsx

แล้วนำชีต

- customer_map
- account_map
- rm_map

จากไฟล์ CUSTOMER_MAPPING.xlsx

มาวางในไฟล์ TXN ก่อน

เพื่อให้ลูกค้าคนเดิมได้รหัสเดิมทุกไฟล์

## Prompt 8 — เพิ่มรหัสแทน PII

ในชีตข้อมูลหลัก

ช่วยเพิ่มคอลัมน์

- customer_key
- account_key
- rm_id

โดยใช้ XLOOKUP จาก

- customer_map
- account_map
- rm_map

## Prompt 9 — แปลงเป็นค่าคงที่

ช่วยแปลงคอลัมน์

- customer_key
- account_key
- rm_id

เป็นค่าคงที่ (Paste as Values)

## Prompt 10 — ลบ PII

ช่วยลบคอลัมน์ต่อไปนี้

- cardid
- cust_name_th
- account
- marketing_name_th

## Prompt 11 — ลบ Mapping ออกจากไฟล์ TXN

ช่วยลบชีต

- customer_map
- account_map
- rm_map

ออกจากไฟล์ TXN ก่อนบันทึก

## เซฟ

บันทึกเป็น TXN_MASKED.xlsx

---

# Checklist ก่อนส่ง Dev

## Portfolio_MASKED.xlsx

ต้องไม่มี

- cardid
- account
- marketing_name_th

ต้องมี

- customer_key
- account_key
- rm_id
- aum
- thb_unrealized_avg
- record_date

และข้อมูลธุรกิจอื่น ๆ ครบถ้วน

## TXN_MASKED.xlsx

ต้องไม่มี

- cardid
- cust_name_th
- account
- marketing_name_th

ต้องมี

- customer_key
- account_key
- rm_id

## CUSTOMER_MAPPING.xlsx

### customer_map

- cardid
- customer_key

### account_map

- account
- account_key

### rm_map

- marketing_name_th
- rm_id

## ตรวจสอบ Formula

คอลัมน์

- customer_key
- account_key
- rm_id

ต้องเป็นค่า ไม่ใช่สูตร

ตัวอย่างที่ถูก

CUST00045

ตัวอย่างที่ผิด

=XLOOKUP(...)

## ตรวจสอบการจับคู่ข้ามไฟล์

ลูกค้าคนเดียวกันใน

- Portfolio_MASKED.xlsx
- TXN_MASKED.xlsx

ต้องได้ customer_key เดียวกันเสมอ

Account เดียวกันต้องได้ account_key เดียวกันเสมอ

RM คนเดิมต้องได้ rm_id เดียวกันเสมอ

---

# กฎเหล็ก 3 ข้อ

1. ใช้ CUSTOMER_MAPPING.xlsx ชุดเดิมตลอด
   - ลูกค้าเก่าใช้รหัสเดิม
   - ลูกค้าใหม่ต่อท้าย
   - ห้ามสร้าง mapping ใหม่ทั้งชุด

2. ห้ามส่งไฟล์ต่อไปนี้ให้ Dev หรือ Upload เข้า AI
   - ไฟล์ต้นฉบับที่มี PII
   - CUSTOMER_MAPPING.xlsx

3. ส่งได้เฉพาะ
   - Portfolio_MASKED.xlsx
   - TXN_MASKED.xlsx
 