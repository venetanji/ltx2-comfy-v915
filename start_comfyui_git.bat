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
set "COMFY_DIR=%DOCS_DIR%\comfyui-git"
echo ComfyUI source folder: "%COMFY_DIR%"

set "INSTALLER_DIR=%DOCS_DIR%\comfyui-git-installer"

if not exist "%COMFY_DIR%\main.py" (
  echo ERROR: Could not find "%COMFY_DIR%\main.py".
  echo Run install_comfy.bat first - it bootstraps the installer repo and clones ComfyUI into Documents\comfyui-git.
  if exist "%INSTALLER_DIR%\install_comfy.bat" (
    echo(
    set "RUN_INSTALLER="
    set /p "RUN_INSTALLER=Run installer now? [Y/n]: "
    if /i not "%RUN_INSTALLER%"=="N" (
      call "%INSTALLER_DIR%\install_comfy.bat"
    )
  )
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

echo.
echo Starting ComfyUI...
echo ComfyUI will be available at: http://localhost:8188
echo (Browser will open automatically once the server is ready)

REM Pre-create the user/ dir so SQLite can open comfyui.db on first run.
REM ComfyUI always places the DB at <src>/user/comfyui.db regardless of --base-directory.
if not exist "%COMFY_DIR%\user\" mkdir "%COMFY_DIR%\user" >nul 2>nul

REM Build a safe sqlite:/// URL using forward slashes (avoids backslash issues on Windows).
set "COMFY_DB_PATH=%COMFY_DIR%\user\comfyui.db"
set "COMFY_DB_URL=sqlite:///%COMFY_DB_PATH:\=/%"

REM Poll localhost:8188 in the background; open browser as soon as it responds.
powershell -NoProfile -ExecutionPolicy RemoteSigned -WindowStyle Hidden -Command ^
  "Start-Job -ScriptBlock { $url='http://localhost:8188'; $max=120; $i=0; while($i -lt $max){ try{ $r=(Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop); if($r.StatusCode -lt 500){ Start-Process $url; break } }catch{}; Start-Sleep 2; $i++ } } | Out-Null"

pushd "%COMFY_DIR%"
"%UV_EXE%" run python main.py --port 8188 --reserve-vram 5 --listen 0.0.0.0 --enable-manager --use-sage-attention --base-directory "%COMFY_DATA%" --database-url "!COMFY_DB_URL!"
set "EXITCODE=%ERRORLEVEL%"
popd

if not "%EXITCODE%"=="0" (
  echo(
  echo ERROR: ComfyUI exited with code %EXITCODE%.
  pause
)

exit /b %EXITCODE%
