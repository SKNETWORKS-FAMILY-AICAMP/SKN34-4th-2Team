<#
.SYNOPSIS
    최신 공유 공고 DB를 안전하게 확인한 뒤 통합 백엔드 서버를 시작한다.

.DESCRIPTION
    크롤링·Pinecone 적재는 실행하지 않는다. Firebase Storage의 공유 SQLite generation이
    바뀐 경우에만 임시 파일로 받은 뒤 검증하고 로컬 DB를 원자 교체한다.
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$SkipJobStoreSync,
    [switch]$NoReload
)

# Windows PowerShell을 중첩 실행해도 Python의 한국어 로그가 깨지지 않게 맞춘다.
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot "playdata_venv\Scripts\python.exe"
$store = Join-Path $repoRoot "job_matching_bot\artifacts\job_store.sqlite"

if (-not (Test-Path -LiteralPath $python)) {
    throw "가상환경 Python이 없습니다: $python"
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
$portInUse = $null -ne $listener
if (-not $portInUse) {
    $probe = [System.Net.Sockets.TcpClient]::new()
    try {
        $connection = $probe.ConnectAsync("127.0.0.1", $Port)
        $portInUse = $connection.Wait(500) -and $probe.Connected
    }
    catch {
        $portInUse = $false
    }
    finally {
        $probe.Dispose()
    }
}
if ($portInUse) {
    throw "$Port 포트를 사용 중인 서버가 있습니다. 기존 백엔드를 먼저 종료해 주세요."
}

Push-Location $repoRoot
try {
    if (-not $SkipJobStoreSync) {
        Write-Host "[공고 DB] Firebase Storage 최신 공유본 확인"
        & $python -m job_matching_bot.sharing.share_store --download-if-newer
        if ($LASTEXITCODE -ne 0) {
            if (Test-Path -LiteralPath $store) {
                Write-Warning "공유 DB 확인에 실패해 기존 로컬 DB로 서버를 시작합니다."
            }
            else {
                throw "공유 DB 확인에 실패했고 기존 로컬 DB도 없습니다."
            }
        }
    }

    $uvicornArgs = @(
        "-m", "uvicorn", "app.integrated:app", "--app-dir", "cover_letter_rag",
        "--host", "0.0.0.0", "--port", "$Port"
    )
    if (-not $NoReload) {
        $uvicornArgs += "--reload"
    }
    Write-Host "[백엔드] http://127.0.0.1:$Port"
    & $python @uvicornArgs
}
finally {
    Pop-Location
}
