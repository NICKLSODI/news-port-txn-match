# สร้าง shortcut ที่มีไอคอน ไว้กดเปิดระบบ (รันครั้งเดียว)
#   .\install-shortcut.ps1                 -> วางบน Desktop
#   .\install-shortcut.ps1 -StartMenu      -> วางใน Start Menu ด้วย
#   .\install-shortcut.ps1 -Name 'ชื่ออื่น'

param(
    [string]$Name = 'News Matching (INVX)',
    [switch]$StartMenu
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$target = Join-Path $root 'MatchPort.cmd'
$icon = Join-Path $root 'assets\matchport.ico'

foreach ($f in @($target, $icon)) {
    if (-not (Test-Path $f)) { throw "ไม่พบ $f (ถ้าไอคอนหาย รัน: python frontend\scripts\make_icons.py)" }
}

$dests = @([Environment]::GetFolderPath('Desktop'))
if ($StartMenu) {
    $dests += Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'Microsoft\Windows\Start Menu\Programs'
}

$shell = New-Object -ComObject WScript.Shell
try {
    foreach ($dir in $dests) {
        $lnk = Join-Path $dir "$Name.lnk"
        $s = $shell.CreateShortcut($lnk)
        $s.TargetPath = $target
        $s.WorkingDirectory = $root
        $s.IconLocation = "$icon,0"
        $s.Description = 'เปิดระบบจับคู่ข่าว-ลูกค้า (INVX)'
        $s.WindowStyle = 1
        $s.Save()
        Write-Host "สร้างแล้ว: $lnk" -ForegroundColor Green
    }
}
finally { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell) }
