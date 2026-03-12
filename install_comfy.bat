@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================================
echo ComfyUI install (university lab helper)
echo - Installs into Documents (safe if run from a .zip)
echo - Models download to a single shared folder
echo ============================================================

set "FAILED=0"
set "EXITCODE=0"
set "STRICT_CUSTOM_NODE_REQUIREMENTS=0"
set "SCRIPT_DIR=%~dp0"
set "UV_EXE="
set "GIT_EXE="
set "QBT_EXE="
set "TOOLS_ENV=%TEMP%\comfy_tools.env"

REM --- Resolve the real Documents path (handles OneDrive/redirected profiles) ---
set "DOCS_DIR="
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('MyDocuments')" 2^>nul`) do set "DOCS_DIR=%%D"
if not defined DOCS_DIR set "DOCS_DIR=%USERPROFILE%\Documents"

REM --- Repo / path layout ---
set "INSTALLER_REPO=%DOCS_DIR%\comfyui-git-installer"
set "COMFY_SRC=%DOCS_DIR%\comfyui-git"
set "INSTALLER_REPO_URL=https://github.com/venetanji/ltx2-comfy-v915"
set "COMFYUI_REPO_URL=https://github.com/Comfy-Org/ComfyUI"

set "COMFY_DATA=%DOCS_DIR%\ComfyUI"
set "COMFY_DATA_YAML=%COMFY_DATA:\=/%"
set "CUSTOM_NODES_LIST=%SCRIPT_DIR%custom_nodes.txt"
set "CUSTOM_NODES_DIR=%COMFY_DATA%\custom_nodes"
set "WORKFLOWS_DIR=%COMFY_DATA%\user\default\workflows"

REM ============================================================
REM STEP 0 -- Self-bootstrap (ensure we run from installer repo)
REM ============================================================
set "SCRIPT_DIR_NORM=%SCRIPT_DIR%"
if "%SCRIPT_DIR_NORM:~-1%"=="\" set "SCRIPT_DIR_NORM=%SCRIPT_DIR_NORM:~0,-1%"
set "INSTALLER_REPO_NORM=%INSTALLER_REPO%"
if "%INSTALLER_REPO_NORM:~-1%"=="\" set "INSTALLER_REPO_NORM=%INSTALLER_REPO_NORM:~0,-1%"

if /i not "%COMFY_BOOTSTRAPPED%"=="1" (
  if /i not "%SCRIPT_DIR_NORM%"=="%INSTALLER_REPO_NORM%" (
    echo.
    echo This installer should run from: "%INSTALLER_REPO%"
    echo Bootstrapping the installer repo and relaunching...

    for /f "usebackq delims=" %%G in (`powershell -NoProfile -Command "$p=@('%LocalAppData%\Programs\Git\cmd\git.exe','%ProgramFiles%\Git\cmd\git.exe'); $p | Where-Object { Test-Path $_ } | Select-Object -First 1; if (Get-Command git -ErrorAction SilentlyContinue) { (Get-Command git).Source }" 2^>nul`) do (
      if not defined GIT_EXE set "GIT_EXE=%%G"
    )

    if not defined GIT_EXE (
      where winget >nul 2>nul
      if errorlevel 1 (
        echo ERROR: git is required to bootstrap but was not found, and winget is unavailable.
        echo Install Git for Windows, then re-run this script.
        set "EXITCODE=2" & goto :Exit
      )
      echo Installing Git.Git via winget...
      winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
      for /f "usebackq delims=" %%G in (`powershell -NoProfile -Command "$p=@('%LocalAppData%\Programs\Git\cmd\git.exe','%ProgramFiles%\Git\cmd\git.exe'); $p | Where-Object { Test-Path $_ } | Select-Object -First 1" 2^>nul`) do (
        if not defined GIT_EXE set "GIT_EXE=%%G"
      )
    )
    if not defined GIT_EXE (
      echo ERROR: git still not available after install attempt.
      set "EXITCODE=2" & goto :Exit
    )

    if exist "%INSTALLER_REPO%\.git" (
      "!GIT_EXE!" -C "%INSTALLER_REPO%" pull
    ) else (
      if exist "%INSTALLER_REPO%\" (
        echo WARNING: "%INSTALLER_REPO%" exists but is not a git repo. Please delete it and re-run.
        set "EXITCODE=2" & goto :Exit
      )
      "!GIT_EXE!" clone --depth 1 "%INSTALLER_REPO_URL%" "%INSTALLER_REPO%"
      if errorlevel 1 (
        echo ERROR: Failed to clone installer repo.
        set "EXITCODE=2" & goto :Exit
      )
    )
    if not exist "%INSTALLER_REPO%\install_comfy.bat" (
      echo ERROR: Bootstrapped repo is missing install_comfy.bat
      set "EXITCODE=2" & goto :Exit
    )
    set "COMFY_BOOTSTRAPPED=1"
    call "%INSTALLER_REPO%\install_comfy.bat"
    set "EXITCODE=!ERRORLEVEL!" & goto :Exit
  )
)

REM ============================================================
REM STEP 1 -- Create shared folders
REM ============================================================
if not exist "%COMFY_DATA%\"        mkdir "%COMFY_DATA%"        >nul 2>nul
if not exist "%CUSTOM_NODES_DIR%\"  mkdir "%CUSTOM_NODES_DIR%"  >nul 2>nul
if not exist "%WORKFLOWS_DIR%\"     mkdir "%WORKFLOWS_DIR%"     >nul 2>nul

echo.
echo Shared ComfyUI data folder : "%COMFY_DATA%"
echo Installer repo folder      : "%SCRIPT_DIR_NORM%"
echo ComfyUI source folder      : "%COMFY_SRC%"

REM ============================================================
REM STEP 2 -- Execution policy + OpenClaw
REM ============================================================
echo.
echo [Step 2] Setting execution policy and launching OpenClaw...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\Set-ExecutionPolicy.ps1"

REM ============================================================
REM STEP 3 -- Find / install tools (git, uv, qBittorrent)
REM ============================================================
echo.
echo [Step 3] Locating required tools...

REM Use Find-Tools.ps1 to install missing tools via winget (it refreshes PATH too).
REM We don't rely on its output file for paths -- we resolve them ourselves below
REM to avoid FOR /F splitting issues with spaces in paths.
powershell -NoProfile -ExecutionPolicy RemoteSigned ^
  -File "%SCRIPT_DIR%scripts\Find-Tools.ps1" ^
  -OutFile "%TOOLS_ENV%" ^
  -InstallMissing ^
  -Tools "git,uv,qbittorrent"

REM Resolve tool paths directly in BAT after Find-Tools has ensured they are installed.
REM Order: WinGet shim -> known per-user locations -> system locations -> PATH fallback.
call :FindUv
call :FindGit
call :FindQbt

if not defined GIT_EXE (
  set "FAILED=1"
  echo ERROR: git is not available. Aborting.
  set "EXITCODE=2" & goto :Exit
)
if not defined UV_EXE (
  set "FAILED=1"
  echo ERROR: uv is not available. Aborting.
  set "EXITCODE=2" & goto :Exit
)

echo git found : "%GIT_EXE%"
echo uv  found : "%UV_EXE%"
if defined QBT_EXE echo qbt found : "%QBT_EXE%"

REM ============================================================
REM STEP 4 -- Choose install mode
REM ============================================================
set "INSTALL_MODE="
echo.
echo Choose install method:
echo   1^) Desktop app (download)            [recommended for students]
echo   2^) Source (git clone + Python deps)  [advanced / for devs]
if /i "%COMFY_NONINTERACTIVE%"=="1" (
  set "INSTALL_MODE=2"
) else (
  echo (Auto-selecting default in 5 seconds...)
  choice /c 12 /n /t 5 /d 2 /m "Choice [1-2] (default 2): "
  if errorlevel 2 (set "INSTALL_MODE=2") else (set "INSTALL_MODE=1")
)
if not defined INSTALL_MODE set "INSTALL_MODE=2"

set "DO_SOURCE=0"
set "RUN_SOURCE=0"
if "%INSTALL_MODE%"=="2" (
  set "DO_SOURCE=1"
  set "RUN_SOURCE=1"
)

REM ============================================================
REM STEP 5 -- Primary install (Desktop or source clone)
REM ============================================================
if "%INSTALL_MODE%"=="1" goto :install_desktop
goto :install_source_primary

:install_desktop
echo.
call :FindComfyDesktop
if defined COMFY_DESKTOP_EXE (
  echo ComfyUI Desktop already installed: "%COMFY_DESKTOP_EXE%"
  goto :after_primary_install
)
if /i "%COMFY_SKIP_DESKTOP%"=="1" (
  echo COMFY_SKIP_DESKTOP=1; skipping Desktop download.
  goto :after_primary_install
)
echo Installing ComfyUI Desktop via NSIS installer...
set "COMFY_DESKTOP_DL=https://download.comfy.org/windows/nsis/x64"
set "COMFY_DL_EXE=%TEMP%\comfyui-desktop-setup.exe"
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; $wc=New-Object Net.WebClient; $wc.Headers.Add('User-Agent','comfy-lab-installer'); $wc.DownloadFile('%COMFY_DESKTOP_DL%','%COMFY_DL_EXE%')"
if errorlevel 1 (
  echo WARNING: Could not auto-download Desktop installer.
  start "" "%COMFY_DESKTOP_DL%"
) else (
  if exist "%COMFY_DL_EXE%" (
    echo Running Desktop installer silently...
    start "" /wait "%COMFY_DL_EXE%" /S
  ) else (
    echo WARNING: Desktop installer did not download correctly.
    start "" "%COMFY_DESKTOP_DL%"
  )
)
goto :after_primary_install

:install_source_primary
echo.
echo Preparing ComfyUI source checkout...
call :EnsureComfyUiRepo
if errorlevel 1 ( set "EXITCODE=2" & goto :Exit )
if not exist "%COMFY_SRC%\main.py" (
  echo ERROR: ComfyUI not found at "%COMFY_SRC%\main.py"
  set "EXITCODE=2" & goto :Exit
)
echo Writing "%COMFY_SRC%\extra_model_paths.yaml"...
>  "%COMFY_SRC%\extra_model_paths.yaml" echo comfyui:
>> "%COMFY_SRC%\extra_model_paths.yaml" echo   base_path: '%COMFY_DATA_YAML%'

:after_primary_install

REM --- Optional source install alongside Desktop ---
if "%INSTALL_MODE%"=="1" (
  if not exist "%COMFY_SRC%\main.py" (
    echo.
    set "INSTALL_SOURCE_TOO=N"
    if /i not "%COMFY_NONINTERACTIVE%"=="1" (
      echo (Auto-selecting default in 5 seconds...)
      choice /c YN /n /t 5 /d N /m "Also install ComfyUI source? [Y/N] (default N): "
      if errorlevel 2 (set "INSTALL_SOURCE_TOO=N") else (set "INSTALL_SOURCE_TOO=Y")
    )
    if /i "%INSTALL_SOURCE_TOO%"=="Y" (
      set "DO_SOURCE=1"
      call :EnsureComfyUiRepo
      if exist "%COMFY_SRC%\main.py" (
        >  "%COMFY_SRC%\extra_model_paths.yaml" echo comfyui:
        >> "%COMFY_SRC%\extra_model_paths.yaml" echo   base_path: '%COMFY_DATA_YAML%'
      )
    )
  )
)

REM Ensure source checkout always exists (start_comfyui_git.bat depends on it)
echo.
echo Ensuring ComfyUI source checkout exists...
call :EnsureComfyUiRepo
if errorlevel 1 (
  echo WARNING: Could not prepare ComfyUI source checkout.
  echo          start_comfyui_git.bat will not work until this is fixed.
)

REM ============================================================
REM STEP 6 -- Copy workflows
REM ============================================================
if exist "%SCRIPT_DIR%workflows\" (
  echo.
  echo [Step 6] Syncing workflows into "%WORKFLOWS_DIR%"...
  xcopy "%SCRIPT_DIR%workflows\*" "%WORKFLOWS_DIR%\" /E /I /Y >nul
)

REM ============================================================
REM STEP 7 -- Install custom nodes
REM ============================================================
echo.
echo [Step 7] Installing custom nodes...
powershell -NoProfile -ExecutionPolicy RemoteSigned ^
  -File "%SCRIPT_DIR%scripts\Install-CustomNodes.ps1" ^
  -ListFile "%CUSTOM_NODES_LIST%" ^
  -DestDir  "%CUSTOM_NODES_DIR%" ^
  -UvExe   "%UV_EXE%" ^
  -GitExe  "%GIT_EXE%"
if errorlevel 1 (
  if "%STRICT_CUSTOM_NODE_REQUIREMENTS%"=="1" (
    set "FAILED=1"
    echo ERROR: Custom node install failed in strict mode.
  ) else (
    echo WARNING: Some custom node requirements failed; continuing.
  )
)

REM ============================================================
REM STEP 8 -- Desktop venv deps (if Desktop venv exists)
REM ============================================================
set "DESKTOP_VENV_PY=%COMFY_DATA%\.venv\Scripts\python.exe"
if exist "%DESKTOP_VENV_PY%" (
  echo.
  echo [Step 8] Desktop venv detected; installing common deps + custom node requirements...
  pushd "%COMFY_DATA%"
  call "%UV_EXE%" pip install opencv-python imageio-ffmpeg
  for /d %%D in ("%CUSTOM_NODES_DIR%\*") do (
    if exist "%%~fD\requirements.txt" (
      call "%UV_EXE%" pip install -r "%%~fD\requirements.txt"
    )
  )
  popd
)

REM ============================================================
REM STEP 9 -- qBittorrent + torrent model downloads
REM ============================================================
echo.
echo [Step 9] Handling model torrents...
if defined QBT_EXE (
  powershell -NoProfile -ExecutionPolicy RemoteSigned ^
    -File "%SCRIPT_DIR%scripts\Handle-Torrents.ps1" ^
    -TorrentDir "%SCRIPT_DIR%" ^
    -SavePath   "%COMFY_DATA%" ^
    -QbtExe     "%QBT_EXE%"
) else (
  echo WARNING: qBittorrent not found; skipping torrent step.
)

REM ============================================================
REM STEP 10 -- NVIDIA driver
REM ============================================================
if /i not "%COMFY_DISABLE_NVIDIA_DRIVER%"=="1" (
  echo.
  echo [Step 10] NVIDIA driver check (target 591.86)...
  set "NVIDIA_PS_ARGS=-File ""%SCRIPT_DIR%scripts\Install-NvidiaDriver.ps1"" -ScriptDir ""%SCRIPT_DIR%"""
  if defined QBT_EXE set "NVIDIA_PS_ARGS=!NVIDIA_PS_ARGS! -QbtExe ""%QBT_EXE%"""
  if /i "%COMFY_NONINTERACTIVE%"=="1" set "NVIDIA_PS_ARGS=!NVIDIA_PS_ARGS! -NonInteractive"
  powershell -NoProfile -ExecutionPolicy RemoteSigned !NVIDIA_PS_ARGS!
)

REM ============================================================
REM STEP 11 -- Python environment (source install only)
REM ============================================================
if "%DO_SOURCE%"=="0" (
  echo.
  echo Desktop install selected; skipping Python environment setup.
  goto :after_python_setup
)

echo.
echo [Step 11] Setting up Python environment in "%COMFY_SRC%"...
pushd "%COMFY_SRC%"

if exist ".venv\Scripts\python.exe" (
  echo Existing venv found; reusing.
) else (
  call "%UV_EXE%" venv --python 3.12
  if errorlevel 1 (
    echo uv venv failed; attempting "uv python install 3.12" then retry...
    call "%UV_EXE%" python install 3.12
    call "%UV_EXE%" venv --python 3.12
  )
  if errorlevel 1 ( set "FAILED=1" & echo ERROR: Failed to create venv. )
)

echo Installing torch + torchvision + torchaudio (CUDA 13.0 wheels)...
call "%UV_EXE%" pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
if errorlevel 1 ( set "FAILED=1" & echo ERROR: Failed to install torch packages. )

echo Installing ComfyUI requirements...
if exist "requirements.txt" (
  call "%UV_EXE%" pip install -r requirements.txt
  if errorlevel 1 ( set "FAILED=1" & echo ERROR: Failed to install requirements.txt )
) else (
  set "FAILED=1" & echo ERROR: requirements.txt not found in "%COMFY_SRC%".
)

if exist "%SCRIPT_DIR%requirements.txt" (
  echo Installing installer repo requirements...
  call "%UV_EXE%" pip install -r "%SCRIPT_DIR%requirements.txt"
  if errorlevel 1 echo WARNING: Installer repo requirements.txt had failures.
)

if exist "manager_requirements.txt" (
  call "%UV_EXE%" pip install -r manager_requirements.txt
  if errorlevel 1 ( set "FAILED=1" & echo ERROR: Failed to install manager_requirements.txt )
)

echo Installing common custom-node dependencies...
call "%UV_EXE%" pip install opencv-python imageio-ffmpeg
if errorlevel 1 echo WARNING: Optional custom-node deps had failures.

if "%FAILED%"=="0" (
  if "%RUN_SOURCE%"=="1" (
    echo.
    echo Starting ComfyUI...
    echo ComfyUI will be available at: http://localhost:8188
    echo (Browser will open automatically once the server is ready)

    REM Pre-create the user/ dir so SQLite can open comfyui.db on first run.
    REM ComfyUI always places the DB at <src>/user/comfyui.db regardless of --base-directory.
    if not exist "%COMFY_SRC%\user\" mkdir "%COMFY_SRC%\user" >nul 2>nul

    REM Build a safe sqlite:/// URL using forward slashes (avoids backslash issues on Windows).
    set "COMFY_DB_PATH=%COMFY_SRC%\user\comfyui.db"
    set "COMFY_DB_URL=sqlite:///%COMFY_DB_PATH:\=/%"

    REM Launch a background watcher that polls localhost:8188 and opens the
    REM browser as soon as ComfyUI responds -- avoids the 0.0.0.0 confusion.
    powershell -NoProfile -ExecutionPolicy RemoteSigned -WindowStyle Hidden -Command ^
      "Start-Job -ScriptBlock { $url='http://localhost:8188'; $max=120; $i=0; while($i -lt $max){ try{ $r=(Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop); if($r.StatusCode -lt 500){ Start-Process $url; break } }catch{}; Start-Sleep 2; $i++ } } | Out-Null"

    set "GIT_PYTHON_GIT_EXECUTABLE=%GIT_EXE%"
    call "%UV_EXE%" run python main.py --reserve-vram 5 --listen 0.0.0.0 --enable-manager --use-sage-attention --base-directory "%COMFY_DATA%" --database-url "!COMFY_DB_URL!"
    set "EXITCODE=%ERRORLEVEL%"
    popd

    echo.
    echo [Post-run] Patching ComfyUI Manager config...
    powershell -NoProfile -ExecutionPolicy RemoteSigned ^
      -File "%SCRIPT_DIR%scripts\Patch-ManagerConfig.ps1" ^
      -ComfySrc  "%COMFY_SRC%" ^
      -ComfyData "%COMFY_DATA%"

    goto :Exit
  ) else (
    echo.
    echo Source installed/updated. Desktop install remains the default launcher.
    popd
    powershell -NoProfile -ExecutionPolicy RemoteSigned ^
      -File "%SCRIPT_DIR%scripts\Patch-ManagerConfig.ps1" ^
      -ComfySrc  "%COMFY_SRC%" ^
      -ComfyData "%COMFY_DATA%"
    goto :after_python_setup
  )
) else (
  echo One or more steps failed. Fix errors above, then re-run.
  popd
  set "EXITCODE=2" & goto :Exit
)

:after_python_setup
echo.
echo Done.
echo - Shared models folder : "%COMFY_DATA%\models"
echo - Shared custom nodes  : "%CUSTOM_NODES_DIR%"
echo - Shared workflows     : "%WORKFLOWS_DIR%"
echo - If you installed Desktop, launch it from the Start Menu.
echo - If you installed Source, re-run this script to update.
set "EXITCODE=0" & goto :Exit

REM ============================================================
REM Subroutines
REM ============================================================

:FindUv
set "UV_EXE="
if exist "%LocalAppData%\Microsoft\WinGet\Links\uv.exe" set "UV_EXE=%LocalAppData%\Microsoft\WinGet\Links\uv.exe"
if not defined UV_EXE if exist "%LocalAppData%\uv\uv.exe" set "UV_EXE=%LocalAppData%\uv\uv.exe"
if not defined UV_EXE if exist "%LocalAppData%\Programs\uv\uv.exe" set "UV_EXE=%LocalAppData%\Programs\uv\uv.exe"
if not defined UV_EXE if exist "%ProgramFiles%\uv\uv.exe" set "UV_EXE=%ProgramFiles%\uv\uv.exe"
if not defined UV_EXE for /f "delims=" %%P in ('where uv.exe 2^>nul') do if not defined UV_EXE set "UV_EXE=%%P"
exit /b 0

:FindGit
set "GIT_EXE="
if exist "%LocalAppData%\Microsoft\WinGet\Links\git.exe" set "GIT_EXE=%LocalAppData%\Microsoft\WinGet\Links\git.exe"
if not defined GIT_EXE if exist "%LocalAppData%\Programs\Git\cmd\git.exe" set "GIT_EXE=%LocalAppData%\Programs\Git\cmd\git.exe"
if not defined GIT_EXE if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT_EXE=%ProgramFiles%\Git\cmd\git.exe"
if not defined GIT_EXE if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "GIT_EXE=%ProgramFiles(x86)%\Git\cmd\git.exe"
if not defined GIT_EXE for /f "delims=" %%P in ('where git.exe 2^>nul') do if not defined GIT_EXE set "GIT_EXE=%%P"
if not defined GIT_EXE for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\GitForWindows" /v InstallPath 2^>nul ^| findstr /i "InstallPath"') do if exist "%%B\cmd\git.exe" set "GIT_EXE=%%B\cmd\git.exe"
exit /b 0

:FindQbt
set "QBT_EXE="
if exist "%ProgramFiles%\qBittorrent\qbittorrent.exe" set "QBT_EXE=%ProgramFiles%\qBittorrent\qbittorrent.exe"
if not defined QBT_EXE if exist "%ProgramFiles(x86)%\qBittorrent\qbittorrent.exe" set "QBT_EXE=%ProgramFiles(x86)%\qBittorrent\qbittorrent.exe"
if not defined QBT_EXE if exist "%LocalAppData%\Programs\qBittorrent\qbittorrent.exe" set "QBT_EXE=%LocalAppData%\Programs\qBittorrent\qbittorrent.exe"
if not defined QBT_EXE for /f "delims=" %%P in ('where qbittorrent.exe 2^>nul') do if not defined QBT_EXE set "QBT_EXE=%%P"
exit /b 0

:FindComfyDesktop
set "COMFY_DESKTOP_EXE="
for %%P in (
  "%LocalAppData%\Programs\ComfyUI\ComfyUI.exe"
  "%LocalAppData%\Programs\ComfyUI Desktop\ComfyUI.exe"
  "%ProgramFiles%\ComfyUI\ComfyUI.exe"
  "%ProgramFiles%\ComfyUI Desktop\ComfyUI.exe"
  "%ProgramFiles(x86)%\ComfyUI\ComfyUI.exe"
  "%ProgramFiles(x86)%\ComfyUI Desktop\ComfyUI.exe"
) do (
  if not defined COMFY_DESKTOP_EXE if exist "%%~P" set "COMFY_DESKTOP_EXE=%%~P"
)
exit /b 0

:EnsureComfyUiRepo
if not defined GIT_EXE ( echo ERROR: git not found. & exit /b 1 )
if exist "%COMFY_SRC%\.git" (
  echo Updating ComfyUI repo...
  call "%GIT_EXE%" -C "%COMFY_SRC%" pull
  if not exist "%COMFY_SRC%\main.py" (
    echo ERROR: ComfyUI checkout looks incomplete (missing main.py).
    exit /b 1
  )
  exit /b 0
)
if exist "%COMFY_SRC%\" (
  echo ERROR: "%COMFY_SRC%" exists but is not a git repo. Delete it and re-run.
  exit /b 1
)
echo Cloning ComfyUI into "%COMFY_SRC%"...
call "%GIT_EXE%" clone --depth 1 "%COMFYUI_REPO_URL%" "%COMFY_SRC%"
if errorlevel 1 (
  echo Shallow clone failed; retrying full clone...
  call "%GIT_EXE%" clone "%COMFYUI_REPO_URL%" "%COMFY_SRC%"
)
if errorlevel 1 ( echo ERROR: Failed to clone ComfyUI. & exit /b 1 )
if not exist "%COMFY_SRC%\main.py" (
  echo ERROR: Clone completed but main.py is missing.
  exit /b 1
)
exit /b 0

:Exit
if not defined EXITCODE set "EXITCODE=0"
if "%EXITCODE%"=="0" (
  echo.
  echo ============================================================
  echo SUCCESS: Installation completed.
  echo ============================================================
) else (
  echo.
  echo Installer failed with exit code %EXITCODE%.
)
echo.
if /i not "%COMFY_NO_PAUSE%"=="1" (
  echo Press any key to close...
  pause >nul
)
exit /b %EXITCODE%