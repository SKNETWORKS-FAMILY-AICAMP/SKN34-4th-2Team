# Firebase 초기 시드 실행 스크립트 (PowerShell)
# 사전 조건: Firebase Console에서 Authentication > 이메일/비밀번호 활성화

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Fb = Join-Path $Root "config\firebase"

Write-Host "`n[1/4] Bootstrap Rules 배포..." -ForegroundColor Cyan
Copy-Item "$Fb\firestore.rules.production" "$Fb\firestore.rules.production.bak" -ErrorAction SilentlyContinue
Copy-Item "$Fb\firestore.rules" "$Fb\firestore.rules.production" -Force
Copy-Item "$Fb\firestore.rules.bootstrap" "$Fb\firestore.rules" -Force
Set-Location $Root
firebase deploy --only firestore:rules

Write-Host "`n[2/4] 계정 + 데이터 시드..." -ForegroundColor Cyan
Set-Location "$Root\scripts"
node seed-via-client.mjs

Write-Host "`n[3/4] Production Rules 복원..." -ForegroundColor Cyan
Copy-Item "$Fb\firestore.rules.production" "$Fb\firestore.rules" -Force
Set-Location $Root
firebase deploy --only firestore:rules

Write-Host "`n[4/4] 완료! flutter run -d chrome 후 로그인하세요." -ForegroundColor Green
Write-Host "  관리자: admin@playdata.co.kr / Playdata123!"
Write-Host "  강사:   instructor@playdata.co.kr / Playdata123!"
Write-Host "  학생:   student@playdata.co.kr / Playdata123!`n"
