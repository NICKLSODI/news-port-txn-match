# เปิดระบบแบบคลิกเดียว — ใช้กับ shortcut บน Desktop (assets\matchport.ico)
#   .\launch.ps1            เปิดเซิร์ฟเวอร์ + เปิดเบราว์เซอร์ให้เอง
#   .\launch.ps1 -Dev       โหมด dev (backend :8000 + vite :5173)
#   .\launch.ps1 -Setup     สั่งตั้งต้นข้อมูลก่อนเปิด

param(
    [int]$Port = 8000,
    [switch]$Dev,
    [switch]$Setup
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$uiPort = if ($Dev) { 5173 } else { $Port }
$url = "http://127.0.0.1:$uiPort"

function Test-Port([int]$p) {
    $c = New-Object Net.Sockets.TcpClient
    try { $c.Connect('127.0.0.1', $p); return $true } catch { return $false } finally { $c.Dispose() }
}

# ถ้าเปิดอยู่แล้ว แค่เด้งเบราว์เซอร์
if (Test-Port $uiPort) {
    Write-Host "เซิร์ฟเวอร์เปิดอยู่แล้วที่ $url" -ForegroundColor Green
    Start-Process $url
    Start-Sleep -Seconds 2
    exit 0
}

# ---------------------------------------------------------------------------
# ตรวจล็อกอิน Claude Code ก่อนเปิดเว็บ
#
# ฟีเจอร์ให้ AI อ่านข่าวใช้สิทธิ์ Claude Code ของเครื่องนี้ ไม่ได้ใช้ API key
# พอล็อกอินหมดอายุ ปุ่ม "ให้ AI อ่านข่าว" จะเงียบไปเฉย ๆ โดยหน้าจอไม่บอกอะไร
# จึงต้องรู้ตั้งแต่ก่อนเปิด ไม่ใช่ไปงงตอนกดปุ่มแล้วไม่มีอะไรเกิดขึ้น
#
# ล็อกอินไม่ผ่านก็ยังเปิดระบบต่อ — การจับคู่ข่าวกับลูกค้าทำงานได้โดยไม่ต้องมี AI
# มีแค่ปุ่มให้ AI อ่านที่จะหายไป จึงไม่ควรบล็อกทั้งโปรแกรมเพราะเรื่องนี้
# ---------------------------------------------------------------------------
function Test-ClaudeLogin {
    $claude = (Get-Command claude -ErrorAction SilentlyContinue)
    if (-not $claude) {
        Write-Host ''
        Write-Host '  ! ไม่พบโปรแกรม Claude Code บนเครื่องนี้' -ForegroundColor Yellow
        Write-Host '    ระบบยังเปิดได้ตามปกติ แต่ปุ่ม "ให้ AI อ่านข่าว" จะใช้ไม่ได้' -ForegroundColor DarkGray
        Write-Host '    ถ้าต้องการใช้: ติดตั้งจาก https://claude.com/claude-code แล้วเปิดโปรแกรมนี้ใหม่' -ForegroundColor DarkGray
        Write-Host ''
        return $false
    }
    try {
        $raw = & claude auth status --json 2>$null | Out-String
        $st = $raw | ConvertFrom-Json
    } catch { $st = $null }

    if ($st -and $st.loggedIn) {
        Write-Host "  ✓ Claude Code พร้อมใช้งาน ($($st.email))" -ForegroundColor Green
        return $true
    }

    Write-Host ''
    Write-Host '  ! ยังไม่ได้ล็อกอิน Claude Code (หรือล็อกอินหมดอายุแล้ว)' -ForegroundColor Yellow
    Write-Host '    เดี๋ยวจะเปิดหน้าล็อกอินให้ — ทำตามนี้:' -ForegroundColor White
    Write-Host '      1. เบราว์เซอร์จะเด้งขึ้นมา ให้ล็อกอินบัญชี Claude ให้เรียบร้อย' -ForegroundColor White
    Write-Host '      2. เสร็จแล้วกลับมาที่หน้าต่างสีดำนี้ รอสักครู่' -ForegroundColor White
    Write-Host '    (ถ้าไม่อยากล็อกอินตอนนี้ กด Ctrl+C ระบบจะเปิดโดยไม่มีฟีเจอร์ AI)' -ForegroundColor DarkGray
    Write-Host ''
    Start-Sleep -Seconds 2

    try { & claude auth login } catch {}

    try {
        $st = (& claude auth status --json 2>$null | Out-String) | ConvertFrom-Json
    } catch { $st = $null }

    if ($st -and $st.loggedIn) {
        Write-Host ''
        Write-Host "  ✓ ล็อกอินสำเร็จ ($($st.email))" -ForegroundColor Green
        return $true
    }
    Write-Host ''
    Write-Host '  ! ยังล็อกอินไม่สำเร็จ — ระบบจะเปิดโดยไม่มีฟีเจอร์ AI' -ForegroundColor Yellow
    Write-Host '    ล็อกอินทีหลังได้: เปิด Command Prompt แล้วพิมพ์  claude auth login' -ForegroundColor DarkGray
    Write-Host '    แล้วปิด-เปิดโปรแกรมนี้ใหม่' -ForegroundColor DarkGray
    Write-Host ''
    return $false
}

Write-Host 'ตรวจสอบก่อนเริ่ม...' -ForegroundColor Cyan
Test-ClaudeLogin | Out-Null

# ยังไม่มี DB -> ตั้งต้นข้อมูลให้เอง
$db = Join-Path $root 'backend\matchport.db'
if (-not (Test-Path $db)) {
    Write-Host 'ไม่พบ backend\matchport.db — จะตั้งต้นข้อมูลก่อน (ใช้เวลาหลายนาที)' -ForegroundColor Yellow
    $Setup = $true
}

# watcher เงียบ ๆ: รอพอร์ตเปิดแล้วเด้งเบราว์เซอร์ (ไม่บล็อกหน้าต่างนี้)
$watcher = @"
`$deadline = (Get-Date).AddMinutes(20)
while ((Get-Date) -lt `$deadline) {
    `$c = New-Object Net.Sockets.TcpClient
    try { `$c.Connect('127.0.0.1', $uiPort); `$c.Dispose(); Start-Sleep -Seconds 1; Start-Process '$url'; break }
    catch { `$c.Dispose(); Start-Sleep -Seconds 2 }
}
"@
Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $watcher
) | Out-Null

Write-Host "กำลังเปิดระบบ... เบราว์เซอร์จะเปิด $url ให้เองเมื่อพร้อม" -ForegroundColor Cyan
Write-Host 'ปิดหน้าต่างนี้ = ปิดเซิร์ฟเวอร์' -ForegroundColor DarkGray

# รัน start.ps1 ในหน้าต่างนี้ (log เซิร์ฟเวอร์อยู่ตรงนี้)
$startArgs = @{ Port = $Port }
if ($Dev) { $startArgs['Dev'] = $true }
if ($Setup) { $startArgs['Setup'] = $true }
& (Join-Path $root 'start.ps1') @startArgs
