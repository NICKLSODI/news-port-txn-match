# รันระบบทั้งหมด — News-Customer Matching
#   .\start.ps1              เปิดเซิร์ฟเวอร์ (ถ้ายังไม่มี DB จะตั้งต้นให้เอง)
#   .\start.ps1 -Setup       สร้าง refdata + นำเข้าไฟล์ลูกค้า + ดึงข่าว + จับคู่ แล้วค่อยเปิด
#   .\start.ps1 -Dev         โหมด dev (uvicorn --reload + vite dev server)

param(
    [switch]$Setup,
    [switch]$Dev,
    [int]$Port = 8000,
    [int]$NewsPages = 4
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

Push-Location $backend
try {
    if ($Setup) {
        Step 'ดึงตารางอ้างอิงจากไฟล์ spec (STEP2/3/4)'
        python -m scripts.build_refdata
        if (-not $?) { throw 'build_refdata failed' }

        # ไฟล์ลูกค้าไม่ได้อยู่ใน git (เป็นข้อมูลจริง) เครื่องที่เพิ่ง clone มาจึงไม่มี
        # ไม่มีก็เปิดระบบได้ — ข่าวยังดึงได้ตามปกติ แค่ยังไม่มีใครให้จับคู่
        # ผู้ใช้อัปโหลดผ่านหน้าเว็บทีหลังได้ ซึ่งมีตัวตรวจไฟล์ให้ด้วย ดีกว่าวางไฟล์เอง
        $hasPortfolio = @(Get-ChildItem (Join-Path $root 'data') -Filter *.xlsx -ErrorAction SilentlyContinue |
                          Where-Object { $_.Name -match 'portfolio|port' }).Count -gt 0
        $hasTxn = @(Get-ChildItem (Join-Path $root 'data') -Filter *.xlsx -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -match 't_match|txn|transaction' }).Count -gt 0

        if ($hasPortfolio -and $hasTxn) {
            Step 'นำเข้าไฟล์ลูกค้า + คำนวณ feature และ persona (STEP1/STEP5)'
            python -m scripts.pipeline ingest
            if (-not $?) { throw 'ingest failed' }
        }
        else {
            Write-Host ''
            Write-Host '  ! ยังไม่มีไฟล์ลูกค้าในโฟลเดอร์ data — ข้ามขั้นตอนนำเข้าไปก่อน' -ForegroundColor Yellow
            Write-Host '    ระบบจะเปิดได้ตามปกติ มีข่าวครบ แต่ยังไม่มีรายชื่อลูกค้าให้จับคู่' -ForegroundColor DarkGray
            Write-Host '    วิธีใส่ข้อมูล: เปิดเว็บแล้วไปเมนู "นำเข้าไฟล์" อัปโหลดสองไฟล์ได้เลย' -ForegroundColor White
            Write-Host '    (ไฟล์ลูกค้าไม่ได้อยู่ใน git เพราะเป็นข้อมูลจริง ต้องขอจากผู้ดูแล)' -ForegroundColor DarkGray
            Write-Host ''
        }

        Step "ดึงข่าวจาก Cafe Invest API ($($NewsPages * 100) ชิ้นล่าสุด)"
        python -m scripts.pipeline news --pages $NewsPages
        if (-not $?) { throw 'news failed' }

        if ($hasPortfolio -and $hasTxn) {
            Step 'จับคู่ข่าวกับลูกค้า (STEP6)'
            python -m scripts.pipeline match
            if (-not $?) { throw 'match failed' }
        }
    }

    $dist = Join-Path $frontend 'dist'
    if (-not (Test-Path $dist) -and -not $Dev) {
        Step 'build หน้าเว็บ'
        Push-Location $frontend
        try {
            if (-not (Test-Path 'node_modules')) { npm install --no-audit --no-fund }
            npm run build
        } finally { Pop-Location }
    }

    if ($Dev) {
        Step "โหมด dev — backend :$Port / frontend :5173"
        Start-Process powershell -ArgumentList @(
            '-NoExit', '-Command',
            "Set-Location '$frontend'; npm run dev"
        )
        python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
    }
    else {
        Step "เปิดที่ http://127.0.0.1:$Port"
        python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
    }
}
finally { Pop-Location }
