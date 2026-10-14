<#
.SYNOPSIS
    야간 수집 배치를 Windows 작업 스케줄러에 등록·해제·확인한다.

.DESCRIPTION
    매일 23:00에 `python -m job_matching_bot.crawling.nightly`를 저장소 루트에서 돌린다.
    출력은 job_matching_bot/artifacts/nightly/log/<날짜>.log 에 남는다.
    가상환경(playdata_venv)의 python을 쓴다. Pinecone·OpenAI 패키지가 거기 있다.

    노트북이 꺼져 있으면 그 밤은 건너뛴다(다음 밤에 이어서 받는다). 배터리 상태에서도 돌고,
    켜져 있기만 하면 잠자기에서 깨워서 돈다.

.EXAMPLE
    .\job_matching_bot\crawling\schedule_nightly.ps1 -Register
    .\job_matching_bot\crawling\schedule_nightly.ps1 -Status
    .\job_matching_bot\crawling\schedule_nightly.ps1 -RunNow
    .\job_matching_bot\crawling\schedule_nightly.ps1 -Unregister
#>
[CmdletBinding()]
param(
    [switch]$Register,
    [switch]$Unregister,
    [switch]$Status,
    [switch]$RunNow,
    [string]$At = "23:00",
    [string]$TaskName = "JobMatchingBot Nightly"
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot "playdata_venv\Scripts\python.exe"
$logDir = Join-Path $repoRoot "job_matching_bot\artifacts\nightly\log"

if ($Register) {
    if (-not (Test-Path $python)) {
        Write-Error "가상환경 python이 없습니다: $python"
        exit 1
    }
    New-Item -ItemType Directory -Force $logDir | Out-Null
    # cmd로 감싸서 표준 출력·오류를 날짜별 로그로 보낸다.
    #
    # 명령 전체를 따옴표로 한 번 더 감싼다. `cmd /c`는 인자가 따옴표로 시작하면 바깥
    # 따옴표 한 쌍을 벗겨 내므로, 감싸지 않으면 python 경로 앞과 로그 경로 뒤의 따옴표가
    # 사라져 리다이렉션 대상이 반쪽짜리 경로가 된다. 실제로 첫 밤 배치가 이것 때문에
    # 로그 한 줄 남기지 못하고 죽었다(작업 결과 1).
    # -u 로 출력 버퍼를 끈다. 없으면 파이썬이 8KB씩 모아 뒀다 쓰므로 한 시간짜리 배치가
    # 끝날 때까지 로그가 0바이트다. 도는 중에 어디까지 갔는지 볼 수 없다.
    $command = "`"$python`" -u -m job_matching_bot.crawling.nightly >> `"$logDir\%DATE:~0,10%.log`" 2>&1"
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$command`"" -WorkingDirectory $repoRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -WakeToRun -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 8) `
        -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "등록: '$TaskName' 매일 $At · 로그 $logDir"
}

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "해제: '$TaskName'"
}

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "시작: '$TaskName' (로그 $logDir)"
}

if ($Status -or -not ($Register -or $Unregister -or $RunNow)) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "'$TaskName' 은 등록돼 있지 않습니다. -Register 로 등록하세요."
        exit 0
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "작업: $TaskName ($($task.State))"
    Write-Host "  다음 실행: $($info.NextRunTime)"
    Write-Host "  마지막 실행: $($info.LastRunTime) (결과 코드 $($info.LastTaskResult))"
    $latest = Get-ChildItem $logDir -Filter *.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($latest) { Write-Host "  최근 로그: $($latest.FullName)" }

    # 실패를 조용히 넘기지 않는다. 첫 밤 배치가 결과 1로 죽었는데 아무도 몰랐다.
    if ($info.LastTaskResult -ne 0 -and $info.LastRunTime) {
        Write-Warning "마지막 실행이 실패했습니다 (결과 코드 $($info.LastTaskResult))."
        if (-not $latest -or $latest.LastWriteTime -lt $info.LastRunTime) {
            Write-Warning "그 실행의 로그가 없습니다. 배치가 시작조차 못 한 것입니다 - 등록된 명령을 확인하세요:"
            Write-Host "  $($task.Actions[0].Execute) $($task.Actions[0].Arguments)"
        }
        else {
            Write-Host "  로그 끝부분:"
            Get-Content $latest.FullName -Tail 15 | ForEach-Object { Write-Host "    $_" }
        }
    }
}
