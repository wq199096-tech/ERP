$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$ApiProcess = Start-Process -FilePath $PythonExe -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--app-dir','services/api' -WorkingDirectory $RepoRoot -PassThru -WindowStyle Hidden
$AgentProcess = Start-Process -FilePath $PythonExe -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','17321','--app-dir','services/print-agent' -WorkingDirectory $RepoRoot -PassThru -WindowStyle Hidden
$ViteProcess = Start-Process -FilePath 'pnpm.cmd' -ArgumentList '--filter','@smartorder/desktop','dev:web','--host','127.0.0.1' -WorkingDirectory $RepoRoot -PassThru -WindowStyle Hidden

try {
    Start-Sleep -Seconds 6
    $ApiHealth = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health'
    $AgentHealth = Invoke-RestMethod 'http://127.0.0.1:17321/api/v1/health'
    $Web = Invoke-WebRequest 'http://127.0.0.1:5173' -UseBasicParsing
    $LoginBody = @{ email = 'admin@smartorder.local'; password = 'SmartOrder123!' } | ConvertTo-Json
    $Login = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/auth/login' -Method Post -ContentType 'application/json' -Body $LoginBody
    $Headers = @{ Authorization = "Bearer $($Login.access_token)" }
    $Sync = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/orders/mock/sync?count=25' -Method Post -Headers $Headers
    $AgentHeaders = @{ Authorization = 'Bearer replace-with-local-agent-token' }
    $PrintBody = @{
        idempotency_key = 'smoke-waybill-20261018'
        job_type = 'WAYBILL'
        payload = @{ order_no = 'SO-SMOKE-001' }
    } | ConvertTo-Json -Depth 4
    $Print = Invoke-RestMethod 'http://127.0.0.1:17321/api/v1/jobs' -Method Post -Headers $AgentHeaders -ContentType 'application/json' -Body $PrintBody
    Write-Output "API=$($ApiHealth.status) AGENT=$($AgentHealth.status) WEB=$($Web.StatusCode) LOGIN=$($Login.user.name) SYNC_CREATED=$($Sync.created) PRINT_STATUS=$($Print.status) PDF=$([bool](Test-Path $Print.output_file))"
}
finally {
    Stop-Process -Id $ApiProcess.Id,$AgentProcess.Id,$ViteProcess.Id -Force -ErrorAction SilentlyContinue
}

