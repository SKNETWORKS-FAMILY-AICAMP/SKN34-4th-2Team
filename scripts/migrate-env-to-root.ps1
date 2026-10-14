<#!
.SYNOPSIS
Builds the root .env from existing module-local .env files without printing secrets.

.DESCRIPTION
The root .env.example supplies non-secret defaults. Existing cover_letter_rag/.env and
functions/.env values override those defaults, in that order. Source files are retained
for rollback and can be removed after both servers have been verified.
#>
[CmdletBinding()]
param()

$repoRoot = Split-Path -Parent $PSScriptRoot
$target = Join-Path $repoRoot '.env'
if (Test-Path -LiteralPath $target) {
    throw '루트 .env가 이미 있습니다. 기존 값을 덮어쓰지 않습니다.'
}

function Read-EnvPairs([string]$path) {
    $values = [ordered]@{}
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $values }
    foreach ($line in Get-Content -LiteralPath $path -Encoding utf8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
        $key, $value = $trimmed.Split('=', 2)
        if ($key.Trim()) { $values[$key.Trim()] = $value.Trim() }
    }
    return $values
}

$merged = Read-EnvPairs (Join-Path $repoRoot '.env.example')
foreach ($source in @(
    (Join-Path $repoRoot 'cover_letter_rag/.env'),
    (Join-Path $repoRoot 'functions/.env')
)) {
    foreach ($entry in (Read-EnvPairs $source).GetEnumerator()) {
        # 기존 모듈 파일에 빈 키가 있어도 .env.example의 안전한 기본값을 지우지 않는다.
        if (-not [string]::IsNullOrWhiteSpace($entry.Value)) {
            $merged[$entry.Key] = $entry.Value
        }
    }
}

$lines = foreach ($entry in $merged.GetEnumerator()) { "$($entry.Key)=$($entry.Value)" }
[System.IO.File]::WriteAllLines($target, $lines, [System.Text.UTF8Encoding]::new($false))
Write-Output "루트 .env를 생성했습니다. $($merged.Count)개 키를 이관했고 값은 출력하지 않습니다."
