<#
.SYNOPSIS
Copies the repository's single local .env source into functions/.env for Firebase CLI.

.DESCRIPTION
Firebase Functions expects its deployment environment file inside functions/.env.
Do not edit that generated file manually; edit the repository root .env and rerun this script.

Firebase CLI rejects keys starting with reserved prefixes:
X_GOOGLE_ / FIREBASE_ / EXT_ / KIT_

Secret Manager 키는 functions/.env에 넣지 않습니다. 같은 이름을
defineSecret과 일반 env에 동시에 두면 Cloud Run 배포가 400으로 실패합니다.
등록: firebase functions:secrets:set <NAME>
#>
[CmdletBinding()]
param()

$repoRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repoRoot '.env'
$destination = Join-Path $repoRoot 'functions/.env'

if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "루트 .env가 없습니다. .env.example을 복사해 먼저 설정하세요."
}

$reserved = [regex]'^\s*(export\s+)?(X_GOOGLE_|FIREBASE_|EXT_|KIT_)'
$secrets = [regex]'^\s*(export\s+)?(OPENAI_API_KEY|PINECONE_API_KEY|PINECONE_API_KEY1|PINECONE_API_KEY2|DISCORD_BOT_TOKEN|GOOGLE_FORM_WEBHOOK_SECRET)='
$keepNames = @('DISCORD_COHORT_ID', 'DATA_GO_KR_SERVICE_KEY')
$existing = @{}
if (Test-Path -LiteralPath $destination -PathType Leaf) {
    foreach ($line in Get-Content -LiteralPath $destination -Encoding UTF8) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$' -and $keepNames -contains $matches[1]) {
            $existing[$matches[1]] = $matches[2]
        }
    }
}

$lines = Get-Content -LiteralPath $source -Encoding UTF8
$present = @{}
$filtered = foreach ($line in $lines) {
    if ($line -match $reserved) { continue }
    if ($line -match $secrets) { continue }
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=') { $present[$matches[1]] = $true }
    $line
}
$kept = foreach ($name in $keepNames) {
    if ($present.ContainsKey($name)) { continue }
    $value = if ($existing.ContainsKey($name)) { $existing[$name] } elseif ($name -eq 'DISCORD_COHORT_ID') { 'cohort_34' } else { '' }
    "$name=$value"
}
Set-Content -LiteralPath $destination -Value (@($filtered) + @($kept)) -Encoding UTF8
Write-Output 'functions/.env를 루트 .env 기준으로 동기화했습니다(예약 prefix·Secret 키 제외). 값은 출력하지 않습니다.'
