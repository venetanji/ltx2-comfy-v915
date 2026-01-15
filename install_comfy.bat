@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================================
echo Comfy install (winget) + CUDA setup script
echo ============================================================

set "FAILED=0"

REM --- Torrent file (local) ---
REM The .torrent should be in the same folder as this .bat.
REM Override by setting TORRENT_FILE before running.
if not defined TORRENT_FILE set "TORRENT_FILE=ltx2-comfy.torrent"

echo Installing qBittorrent.qBittorrent (source: winget)...
winget install --id qBittorrent.qBittorrent -e --source winget --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  set "FAILED=1"
  echo ERROR: qBittorrent install failed.
)

echo.
echo Opening local torrent file...
set "SCRIPT_DIR=%~dp0"
set "TORRENT_PATH=%SCRIPT_DIR%%TORRENT_FILE%"
if exist "%TORRENT_PATH%" (
  start "" "%TORRENT_PATH%"
) else (
  set "FAILED=1"
  echo ERROR: Torrent file not found: "%TORRENT_PATH%"
  echo Put "%TORRENT_FILE%" next to this .bat, or set TORRENT_FILE to the filename.
)

echo.
echo Installing Git.Git (source: winget)...
winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  set "FAILED=1"
  echo ERROR: Git install failed.
)

echo.
echo Installing Comfy.ComfyUI-Desktop (source: winget)...
winget install --id Comfy.ComfyUI-Desktop -e --source winget --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  set "FAILED=1"
  echo ERROR: ComfyUI Desktop install failed.
)

echo.
echo ============================================================
if "%FAILED%"=="0" (
  echo Done.
  exit /b 0
) else (
  echo Done, but one or more steps failed.
  echo Tip: re-run this script in an elevated terminal if needed.
  exit /b 2
)