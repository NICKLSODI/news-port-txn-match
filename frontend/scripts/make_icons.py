"""สร้างไอคอนทั้งชุดจากดีไซน์เดียว (รันซ้ำได้)

    python frontend/scripts/make_icons.py

ผลลัพธ์
    frontend/public/favicon.ico          16/32/48/64/128/256 (สำหรับ browser tab)
    frontend/public/favicon.svg          เวกเตอร์ (browser ที่รองรับจะใช้ตัวนี้ก่อน)
    frontend/public/apple-touch-icon.png 180x180
    frontend/public/icon-192.png         PWA / manifest
    frontend/public/icon-512.png         PWA / manifest
    assets/matchport.ico                 ไอคอนของ shortcut บน Windows

ดีไซน์: สี่เหลี่ยมมนสีน้ำเงิน accent (--accent #1f6fd0) กับสัญลักษณ์ "จับคู่" —
สองจุดเชื่อมกันด้วยเส้นทึบ จุดล่างซ้าย = ข่าว (ขาว), จุดบนขวา = ลูกค้า (ส้ม --s2)
วาดที่ 1024px แล้วย่อด้วย LANCZOS เพื่อให้คมทุกขนาด
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "frontend" / "public"
ASSETS = ROOT / "assets"

# สีเดียวกับ frontend/src/index.css (โหมด light)
BG = "#1f6fd0"          # --accent
FG = "#ffffff"          # --accent-ink
NODE2 = "#eb6834"       # --s2

MASTER = 1024


def draw_master(pad: float = 0.0) -> Image.Image:
    """วาดไอคอนขนาด MASTER. pad = สัดส่วนขอบเผื่อของ glyph (ใช้กับ icon แบบ maskable)"""
    s = MASTER
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # พื้นหลังสี่เหลี่ยมมน
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(0.22 * s), fill=BG)

    # glyph — ย่อเข้ามาตาม pad เพื่อไม่ให้ถูก crop เวลา OS ทำ mask
    k = 1.0 - 2 * pad

    def p(x: float, y: float) -> tuple[float, float]:
        return (s * (pad + x * k), s * (pad + y * k))

    r = 0.135 * s * k
    a = p(0.32, 0.68)      # จุดข่าว (ล่างซ้าย)
    b = p(0.68, 0.32)      # จุดลูกค้า (บนขวา)

    # เส้นเชื่อม — วาดก่อนจุด ปลายเส้นจะถูกจุดทับ
    d.line([a, b], fill=FG, width=int(0.105 * s * k))

    d.ellipse([a[0] - r, a[1] - r, a[0] + r, a[1] + r], fill=FG)
    d.ellipse([b[0] - r, b[1] - r, b[0] + r, b[1] + r], fill=NODE2)
    return img


def resized(master: Image.Image, size: int) -> Image.Image:
    return master.resize((size, size), Image.LANCZOS)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="{bg}"/>
  <line x1="20.5" y1="43.5" x2="43.5" y2="20.5" stroke="{fg}" stroke-width="6.7" stroke-linecap="round"/>
  <circle cx="20.5" cy="43.5" r="8.6" fill="{fg}"/>
  <circle cx="43.5" cy="20.5" r="8.6" fill="{node2}"/>
</svg>
"""


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    master = draw_master()
    padded = draw_master(pad=0.10)   # เผื่อขอบให้ maskable icon ของ PWA

    # .ico — ใส่หลายขนาดในไฟล์เดียว ย่อเองทีละขนาดให้คมกว่าปล่อยให้ ICO plugin ย่อ
    ico_sizes = [256, 128, 64, 48, 32, 16]
    frames = [resized(master, n) for n in ico_sizes]
    for path in (PUBLIC / "favicon.ico", ASSETS / "matchport.ico"):
        frames[0].save(
            path,
            format="ICO",
            sizes=[(n, n) for n in ico_sizes],
            append_images=frames[1:],
        )
        print("wrote", path.relative_to(ROOT))

    # PNG
    for name, size, src in (
        ("apple-touch-icon.png", 180, master),
        ("icon-192.png", 192, padded),
        ("icon-512.png", 512, padded),
    ):
        resized(src, size).save(PUBLIC / name, format="PNG", optimize=True)
        print("wrote", (PUBLIC / name).relative_to(ROOT))

    (PUBLIC / "favicon.svg").write_text(
        SVG.format(bg=BG, fg=FG, node2=NODE2), encoding="utf-8"
    )
    print("wrote", (PUBLIC / "favicon.svg").relative_to(ROOT))


if __name__ == "__main__":
    main()
