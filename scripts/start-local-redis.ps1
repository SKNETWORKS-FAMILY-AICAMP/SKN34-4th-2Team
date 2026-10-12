<#
.SYNOPSIS
Keep the installed WSL Ubuntu Redis service available for local development.
.DESCRIPTION
Does not install packages, change Redis configuration, flush data, or shut
down WSL. Starts at most one matching hidden keepalive and verifies localhost
PING. Run before the local Django/AI backend.
#>
[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._ -]*$')]
    [string]$Distribution = 'Ubuntu',
    [ValidateRange(1, 65535)]
    [int]$Port = 6379,
    [ValidateRange(1, 60)]
    [int]$WaitSeconds = 15
)

$ErrorActionPreference = 'Stop'

function Test-LocalRedisPing {
    param([int]$RedisPort)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connection = $client.ConnectAsync('127.0.0.1', $RedisPort)
        if (-not $connection.Wait(1000)) { return $false }
        [void]$connection.GetAwaiter().GetResult()
        $stream = $client.GetStream()
        $stream.ReadTimeout = 1000
        $stream.WriteTimeout = 1000
        # Redis inline PING is read-only; no credentials or configuration read.
        $command = [System.Text.Encoding]::ASCII.GetBytes("PING`r`n")
        $stream.Write($command, 0, $command.Length)
        $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::ASCII)
        return $reader.ReadLine() -ceq '+PONG'
    }
    catch { return $false }
    finally { $client.Dispose() }
}

$wslPath = (Get-Command wsl.exe -ErrorAction Stop).Source
$distributionOutput = & $wslPath --list --quiet
if ($LASTEXITCODE -ne 0) { throw 'WSL 배포판 목록을 읽지 못했습니다.' }
$distributionNames = @($distributionOutput | ForEach-Object {
    ([string]$_).Replace([string][char]0, '').Trim().Trim([char]0xFEFF)
})
if ($distributionNames -notcontains $Distribution) {
    throw "WSL '$Distribution' 배포판이 없습니다. 설치를 자동으로 수행하지 않습니다."
}

$distributionPattern = [regex]::Escape($Distribution)
$keepalivePattern = '(?i)(?:^|\s)(?:-d|--distribution)\s+(?:"' + $distributionPattern +
    '"|' + $distributionPattern + ')\s+(?:--user\s+\S+\s+)?--exec\s+sleep\s+infinity(?:\s|$)'
$hashProvider = [System.Security.Cryptography.SHA256]::Create()
try {
    $distributionHash = ([BitConverter]::ToString(
        $hashProvider.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Distribution))
    )).Replace('-', '').Substring(0, 24)
}
finally { $hashProvider.Dispose() }
$mutex = [System.Threading.Mutex]::new($false, "Local\SKN34.LocalRedis.$distributionHash")
$mutexTaken = $false
$createdKeepalivePid = $null
try {
    try { $mutexTaken = $mutex.WaitOne(5000) }
    catch [System.Threading.AbandonedMutexException] { $mutexTaken = $true }
    if (-not $mutexTaken) { throw '다른 로컬 Redis helper가 실행 중입니다. 잠시 후 다시 실행해 주세요.' }
    $existing = @(Get-CimInstance Win32_Process -Filter "Name='wsl.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $keepalivePattern })
    if ($existing.Count -eq 0) {
        $process = Start-Process -FilePath $wslPath -ArgumentList @(
            '-d', ('"' + $Distribution + '"'), '--exec', 'sleep', 'infinity'
        ) -WindowStyle Hidden -PassThru
        $createdKeepalivePid = $process.Id
        $keepalivePids = @($process.Id)
    }
    else {
        $keepalivePids = @($existing | Select-Object -ExpandProperty ProcessId)
    }
}
finally {
    if ($mutexTaken) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}

Write-Host ("WSL 유지 프로세스 PID: " + ($keepalivePids -join ', '))
try {
    & $wslPath -d $Distribution --user root --exec /usr/bin/test -x /usr/bin/redis-server
    if ($LASTEXITCODE -ne 0) {
        throw 'redis-server가 설치되어 있지 않습니다. 설치를 자동으로 수행하지 않습니다.'
    }
    $unitState = & $wslPath -d $Distribution --user root --exec systemctl show redis-server --property=LoadState --value
    if ($LASTEXITCODE -ne 0 -or ([string]$unitState).Trim() -ne 'loaded') {
        throw 'redis-server systemd 서비스가 없습니다. 기존 설치·systemd 설정을 확인해 주세요.'
    }
    & $wslPath -d $Distribution --user root --exec systemctl start redis-server
    if ($LASTEXITCODE -ne 0) { throw '설치된 redis-server 서비스를 시작하지 못했습니다.' }
    $deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
    do {
        if (Test-LocalRedisPing -RedisPort $Port) {
            Write-Host "Redis 127.0.0.1:$Port PING: PONG"
            Write-Host '이제 로컬 Django/AI backend를 실행할 수 있습니다.'
            Write-Host '중지하려면 아래 PID의 명령행을 확인한 뒤 해당 유지 프로세스만 종료하세요.'
            foreach ($keepalivePid in $keepalivePids) {
                Write-Host "Get-CimInstance Win32_Process -Filter 'ProcessId=$keepalivePid' | Select-Object ProcessId,CommandLine"
                Write-Host "Stop-Process -Id $keepalivePid"
            }
            return
        }
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "localhost:$Port Redis PING 확인에 실패했습니다. WSL 서비스와 localhost 전달 상태를 확인해 주세요."
}
catch {
    if ($null -ne $createdKeepalivePid) {
        Write-Warning "진단을 위해 새 유지 프로세스 PID $createdKeepalivePid 는 남겨 둡니다. 필요하면 이 PID만 종료하세요."
    }
    throw
}
