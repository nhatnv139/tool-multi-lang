@echo off
REM Dung phim hang loat - khong can mo trinh duyet, khong can bam gi.
REM Vi du:  chay-auto.bat --bai 7,8,9
REM         chay-auto.bat --tat-ca
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if "%~1"=="" (
  echo Cach dung: chay-auto.bat --bai 7,8,9   ^|   chay-auto.bat --tat-ca
  echo.
)
venv\Scripts\python.exe -u auto_film.py %*
echo.
pause
