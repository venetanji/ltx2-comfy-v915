@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================================
echo Start ComfyUI (git/vendored)
echo - Uses uv to run ComfyUI\main.py
echo - Shared data folder: (resolved at runtime)
echo ============================================================

set "DOCS_DIR="
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('MyDocuments')" 2^>nul`) do set "DOCS_DIR=%%D"
if not defined DOCS_DIR set "DOCS_DIR=%USERPROFILE%\Documents"

set "COMFY_DATA=%DOCS_DIR%\ComfyUI"
echo Shared ComfyUI data folder: "%COMFY_DATA%"
for %%I in ("%~dp0.") do set "REPO_DIR=%%~fI"
set "COMFY_DIR=%REPO_DIR%\ComfyUI"

if not exist "%COMFY_DIR%\main.py" (
  echo ERROR: Could not find "%COMFY_DIR%\main.py".
  echo Run install_comfy.bat first - it bootstraps the repo into Documents\comfyui-git.
  pause
  exit /b 2
)

set "UV_EXE="
for /f "delims=" %%P in ('where uv.exe 2^>nul') do (
  if not defined UV_EXE set "UV_EXE=%%P"
)
if not defined UV_EXE (
  for /f "delims=" %%P in ('where uv 2^>nul') do (
    if not defined UV_EXE set "UV_EXE=%%P"
  )
)
if not defined UV_EXE if exist "%LocalAppData%\Microsoft\WinGet\Links\uv.exe" set "UV_EXE=%LocalAppData%\Microsoft\WinGet\Links\uv.exe"

if not defined UV_EXE (
  echo ERROR: uv was not found.
  echo Install it via install_comfy.bat ^(Source mode^) or winget: astral-sh.uv
  pause
  exit /b 2
)

if not exist "%COMFY_DATA%" (
  mkdir "%COMFY_DATA%" >nul 2>nul
)

pushd "%COMFY_DIR%"
"%UV_EXE%" run python main.py --enable-manager --base-directory "%COMFY_DATA%"
set "EXITCODE=%ERRORLEVEL%"
popd

if not "%EXITCODE%"=="0" (
  echo(
  echo ERROR: ComfyUI exited with code %EXITCODE%.
  pause
)

exit /b %EXITCODE%
