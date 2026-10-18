$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DesktopExe = Join-Path $RepoRoot 'apps\desktop\release-local\win-unpacked\智单 ERP.exe'
if (-not (Test-Path $DesktopExe)) { throw "未找到客户端：$DesktopExe" }

$Client = Start-Process -FilePath $DesktopExe -PassThru -WindowStyle Hidden
try {
    Start-Sleep -Seconds 6
    if ($Client.HasExited) { throw "Windows 客户端提前退出，退出码：$($Client.ExitCode)" }
    Write-Output "DESKTOP_RUNNING PID=$($Client.Id) PATH=$DesktopExe"
}
finally {
    Stop-Process -Id $Client.Id -Force -ErrorAction SilentlyContinue
}

