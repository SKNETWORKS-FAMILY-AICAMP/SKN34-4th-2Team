@echo off
chcp 65001 >nul
echo ========================================
echo  Cursor 업데이트 잠금 해제 도우미
echo ========================================
echo.
echo 1) 이 창을 연 뒤 Cursor를 모두 종료하세요.
echo 2) 아무 키나 누르면 Cursor 프로세스를 강제 종료합니다.
echo.
pause

echo.
echo Cursor 프로세스 종료 중...
taskkill /F /IM Cursor.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

echo 남은 프로세스 확인...
tasklist /FI "IMAGENAME eq Cursor.exe" 2>nul | find /I "Cursor.exe" >nul
if %ERRORLEVEL%==0 (
  echo 아직 Cursor.exe 가 실행 중입니다. 작업 관리자에서 수동 종료 후 다시 실행하세요.
  pause
  exit /b 1
)

echo.
echo 업데이트 캐시 정리 중...
if exist "%LOCALAPPDATA%\cursor-updater" (
  rmdir /S /Q "%LOCALAPPDATA%\cursor-updater" 2>nul
)
if exist "%TEMP%\cursor-*" (
  for /d %%D in ("%TEMP%\cursor-*") do rmdir /S /Q "%%D" 2>nul
)

echo.
echo 완료. 이제 시작 메뉴에서 Cursor를 다시 실행하세요.
echo (업데이트가 있으면 종료된 상태에서 적용됩니다.)
echo.
pause
