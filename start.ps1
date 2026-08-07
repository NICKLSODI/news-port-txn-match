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

        Step 'นำเข้าไฟล์ลูกค้า + คำนวณ feature และ persona (STEP1/STEP5)'
        python -m scripts.pipeline ingest
        if (-not $?) { throw 'ingest failed' }

        Step "ดึงข่าวจาก Cafe Invest API ($($NewsPages * 100) ชิ้นล่าสุด)"
        python -m scripts.pipeline news --pages $NewsPages
        if (-not $?) { throw 'news failed' }

        Step 'จับคู่ข่าวกับลูกค้า (STEP6)'
        python -m scripts.pipeline match
        if (-not $?) { throw 'match failed' }
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
