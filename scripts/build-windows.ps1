$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DesktopRoot = Join-Path $RepoRoot 'apps\desktop'
$ElectronPackage = Get-ChildItem -LiteralPath (Join-Path $RepoRoot 'node_modules\.pnpm') -Directory |
    Where-Object { $_.Name -like 'electron@*' } |
    Select-Object -First 1

if (-not $ElectronPackage) {
    throw '未找到 Electron 运行时，请先执行 pnpm install。'
}

$ElectronDist = Join-Path $ElectronPackage.FullName 'node_modules\electron\dist'
if (-not (Test-Path (Join-Path $ElectronDist 'electron.exe'))) {
    throw 'Electron 运行时不完整，请重新执行 Electron 安装脚本。'
}

Push-Location $DesktopRoot
try {
    pnpm exec electron-builder --win nsis --x64 `
        --config.directories.output=release-local `
        --config.electronDist="$ElectronDist"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

