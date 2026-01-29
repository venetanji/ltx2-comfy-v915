@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================================
echo Start ComfyUI (git/vendored)
echo - Uses uv to run ComfyUI\main.py
echo - Shared data folder: %USERPROFILE%\Documents\ComfyUI
echo ============================================================

set "COMFY_DATA=%USERPROFILE%\Documents\ComfyUI"
set "REPO_DIR=%~dp0"
if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"
set "COMFY_DIR=%REPO_DIR%\ComfyUI"

if not exist "%COMFY_DIR%\main.py" (
  echo ERROR: Could not find "%COMFY_DIR%\main.py".
  echo Run install_comfy.bat first (it bootstraps the repo into Documents\comfyui-git).
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
  echo Install it via install_comfy.bat (Source mode) or winget: astral-sh.uv
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
