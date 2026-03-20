@echo off
setlocal EnableExtensions

:: ─────────────────────────────────────────────────────────────────────────────
::  install_comfy.bat
::
::  Can be downloaded and run as a completely standalone file.
::
::  * Fast path  : if scripts\Install-Comfy.ps1 already exists next to this
::    bat (i.e. the repo is already cloned here), it is called directly.
::  * Bootstrap  : otherwise the bat installs git if needed, clones the repo
::    into Documents\comfyui-git-installer, then runs Install-Comfy.ps1 from
::    there -- so a bare "download + double-click" workflow works.
:: ─────────────────────────────────────────────────────────────────────────────

:: Fast path: running from inside the cloned repo already
if exist "%~dp0scripts\Install-Comfy.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Install-Comfy.ps1"
    exit /b %ERRORLEVEL%
)

echo.
echo ComfyUI standalone bootstrap
echo =============================
echo scripts\Install-Comfy.ps1 not found next to this bat -- running bootstrap.
echo.

:: Write a tiny bootstrap helper to %%TEMP%% and execute it.
:: All escaping below follows CMD rules for ( )-grouped echo blocks:
::   ( and ) -> ^( and ^)     | -> ^|     & -> ^&
set "BS=%TEMP%\comfy_bootstrap.ps1"

(
  echo $RepoUrl = 'https://github.com/venetanji/ltx2-comfy-v915'
  echo $docs    = [Environment]::GetFolderPath^('MyDocuments'^)
  echo if ^(-not $docs^) { $docs = Join-Path $env:USERPROFILE 'Documents' }
  echo $repo    = Join-Path $docs 'comfyui-git-installer'
  echo.
  echo function Find-Git {
  echo     $known = @^(
  echo         "$env:LocalAppData\Microsoft\WinGet\Links\git.exe",
  echo         "$env:LocalAppData\Programs\Git\cmd\git.exe",
  echo         "$env:LocalAppData\Programs\Git\bin\git.exe",
  echo         "$env:ProgramFiles\Git\cmd\git.exe",
  echo         "$env:ProgramFiles\Git\bin\git.exe"
  echo     ^)
  echo     $g = Get-Command git -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty Source -First 1
  echo     if ^($g^) { return $g }
  echo     foreach ^($p in $known^) { if ^(Test-Path $p^) { return $p } }
  echo     return $null
  echo }
  echo.
  echo $git = Find-Git
  echo if ^(-not $git^) {
  echo     Write-Host 'git not found -- attempting install via winget...'
  echo     if ^(Get-Command winget -ErrorAction SilentlyContinue^) {
  echo         winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
  echo         $env:PATH = [Environment]::GetEnvironmentVariable^('PATH','Machine'^) + ';' + [Environment]::GetEnvironmentVariable^('PATH','User'^)
  echo         $git = Find-Git
  echo     }
  echo }
  echo if ^(-not $git^) {
  echo     Write-Host ''
  echo     Write-Host 'ERROR: git could not be found or installed automatically.'
  echo     Write-Host 'Please install git from https://git-scm.com and re-run this script.'
  echo     exit 2
  echo }
  echo Write-Host "git : $git"
  echo.
  echo if ^(Test-Path ^(Join-Path $repo '.git'^)^) {
  echo     Write-Host "Updating $repo ..."
  echo     ^& $git -C $repo pull
  echo } else {
  echo     Write-Host "Cloning $RepoUrl into $repo ..."
  echo     ^& $git clone --depth 1 $RepoUrl $repo
  echo     if ^($LASTEXITCODE -ne 0^) {
  echo         Write-Host 'ERROR: git clone failed.'
  echo         exit 2
  echo     }
  echo }
  echo.
  echo $ps1 = Join-Path $repo 'scripts\Install-Comfy.ps1'
  echo if ^(-not ^(Test-Path $ps1^)^) {
  echo     Write-Host "ERROR: $ps1 not found after clone."
  echo     exit 2
  echo }
  echo $env:COMFY_BOOTSTRAPPED = '1'
  echo Write-Host "Launching $ps1 ..."
  echo ^& powershell -NoProfile -ExecutionPolicy Bypass -File $ps1
  echo exit $LASTEXITCODE
) > "%BS%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%BS%"
set "EC=%ERRORLEVEL%"
del "%BS%" 2>nul
exit /b %EC%