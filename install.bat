@echo off
cd /d "%~dp0"
echo === Cai dat ViTranscript ===
where uv >nul 2>nul
if errorlevel 1 (
  echo Dang cai cong cu uv...
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
uv python install 3.12
uv sync
echo.
echo Cai dat hoan tat! Mo ung dung bang file run.bat
pause
