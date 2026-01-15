@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================================
echo Comfy install (winget) + CUDA setup script
echo ============================================================

set "FAILED=0"

REM --- Torrent link placeholder ---
REM Downloads a .torrent file and opens it (should hand off to qBittorrent).
REM Override by setting TORRENT_URL before running.
if not defined TORRENT_URL set "TORRENT_URL=https://1drv.ms/u/c/183babd82b1ba774/IQAmOUPRFcEJT54SUUyHG_h4AYBTW3wtZWyq-a-I_dy8K3Y?e=mlfd2t"

echo Installing qBittorrent.qBittorrent (source: winget)...
winget install --id qBittorrent.qBittorrent -e --source winget --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  set "FAILED=1"
  echo ERROR: qBittorrent install failed.
)

echo.
echo Downloading and opening torrent (placeholder)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $u=$env:TORRENT_URL; if(-not $u){ Write-Host 'TORRENT_URL is not set; skipping.'; exit 0 }; $dir=Join-Path $env:TEMP 'comfy-install'; New-Item -ItemType Directory -Force -Path $dir | Out-Null; $out=Join-Path $dir 'download.torrent'; try { [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12 } catch {} ; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri $u -OutFile $out -MaximumRedirection 10; $b=[System.IO.File]::ReadAllBytes($out); if($b.Length -lt 1 -or $b[0] -ne 100){ Write-Host 'NOTE: Download did not look like a .torrent (bencoded). Opening URL in browser instead...'; Start-Process $u; exit 0 }; Start-Process -FilePath $out" >nul
if errorlevel 1 (
  set "FAILED=1"
  echo ERROR: Torrent download/open failed.
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