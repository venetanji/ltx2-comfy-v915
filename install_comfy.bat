@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================================
echo ComfyUI install (source) + models via torrents
echo ============================================================

set "FAILED=0"
set "SCRIPT_DIR=%~dp0"

REM --- Install uv ---
echo.
where uv >nul 2>nul
if errorlevel 1 (
  where winget >nul 2>nul
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: uv not found and winget is not available.
    echo Install "App Installer" from Microsoft Store or install uv manually.
  ) else (
  echo Installing astral-sh.uv ^(source: winget^)...
  winget install --id=astral-sh.uv -e --source winget --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo WARNING: uv install via winget failed.
  )
  )
) 
where uv >nul 2>nul
if errorlevel 1 (
  set "FAILED=1"
  echo ERROR: uv is still not available on PATH.
) else (
  echo uv already available; skipping install.
)

REM --- Install Git ---
echo.
where git >nul 2>nul
if errorlevel 1 (
  where winget >nul 2>nul
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: git not found and winget is not available.
    echo Install "App Installer" from Microsoft Store or install Git manually.
  ) else (
  echo Installing Git.Git ^(source: winget^)...
  winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo WARNING: Git install via winget failed.
  )
  )
) 
where git >nul 2>nul
if errorlevel 1 (
  set "FAILED=1"
  echo ERROR: git is still not available on PATH.
) else (
  echo Git already available; skipping install.
)

REM --- Clone ComfyUI from source ---
echo.
set "COMFY_DIR=%SCRIPT_DIR%ComfyUI"
if exist "%COMFY_DIR%\" (
  echo ComfyUI already exists at: "%COMFY_DIR%"
  echo Updating repo...
  git -C "%COMFY_DIR%" pull
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to update ComfyUI repo.
  )
) else (
  echo Cloning ComfyUI...
  pushd "%SCRIPT_DIR%"
  git clone https://github.com/Comfy-Org/ComfyUI
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to clone ComfyUI.
  )
  popd
)

if not exist "%COMFY_DIR%\main.py" (
  echo ERROR: ComfyUI repo not present or incomplete at: "%COMFY_DIR%"
  echo Aborting.
  exit /b 2
)

REM --- Install qBittorrent ---
echo.
set "QBT_DEFAULT=C:\Program Files (x86)\qBittorrent\qbittorrent.exe"
if exist "%QBT_DEFAULT%" (
  echo qBittorrent already installed at default path; skipping winget install.
) else (
  where winget >nul 2>nul
  if errorlevel 1 (
    echo WARNING: qBittorrent not found at default path and winget is not available.
  ) else (
    echo Installing qBittorrent.qBittorrent ^(source: winget^)...
    winget install --id qBittorrent.qBittorrent -e --source winget --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
      echo WARNING: qBittorrent install via winget failed.
    )
  )
)

REM --- Locate qBittorrent executable ---
set "QBT_EXE="
for /f "delims=" %%P in ('where qbittorrent.exe 2^>nul') do (
  set "QBT_EXE=%%P"
  goto :qbt_found
)

if exist "%ProgramFiles%\qBittorrent\qbittorrent.exe" set "QBT_EXE=%ProgramFiles%\qBittorrent\qbittorrent.exe"
if not defined QBT_EXE if exist "%ProgramFiles(x86)%\qBittorrent\qbittorrent.exe" set "QBT_EXE=%ProgramFiles(x86)%\qBittorrent\qbittorrent.exe"
if not defined QBT_EXE if exist "%LocalAppData%\Programs\qBittorrent\qbittorrent.exe" set "QBT_EXE=%LocalAppData%\Programs\qBittorrent\qbittorrent.exe"

:qbt_found
if not defined QBT_EXE (
  set "FAILED=1"
  echo ERROR: Could not locate qbittorrent.exe after install.
) else (
  echo qBittorrent found: "%QBT_EXE%"
)

REM --- Torrent prompt (download models into ComfyUI folder) ---
echo.
echo Looking for .torrent files next to this script...
set "TORRENT_COUNT=0"
for %%F in ("%SCRIPT_DIR%*.torrent") do (
  set /a TORRENT_COUNT+=1
  set "TORRENT[!TORRENT_COUNT!]=%%~fF"
  set "TORRENT_NAME[!TORRENT_COUNT!]=%%~nxF"
)

if "%TORRENT_COUNT%"=="0" (
  echo No .torrent files found in: "%SCRIPT_DIR%"
  echo Skipping torrent step.
) else (
  echo.
  echo Available torrents:
  for /l %%I in (1,1,!TORRENT_COUNT!) do (
    echo   %%I^) !TORRENT_NAME[%%I]!
  )
  echo.
  echo Enter one or more numbers ^(space-separated^) to open in qBittorrent.
  echo Enter ALL to open all torrents.
  echo Leave blank to skip.
  set "TORRENT_SELECTION="
  set /p "TORRENT_SELECTION=Selection: "

  if /i "!TORRENT_SELECTION!"=="" (
    echo Skipping torrent step.
  ) else (
    if /i "!TORRENT_SELECTION!"=="ALL" (
      set "TORRENT_SELECTION="
      for /l %%I in (1,1,!TORRENT_COUNT!) do set "TORRENT_SELECTION=!TORRENT_SELECTION! %%I"
    )

    if defined QBT_EXE (
      echo.
      echo Starting qBittorrent...
      start "" "%QBT_EXE%"
      REM Give the UI a moment to initialize so the next invocation is handled.
      timeout /t 2 /nobreak >nul

      for %%S in (!TORRENT_SELECTION!) do (
        call set "TPATH=%%TORRENT[%%S]%%"
        call set "TNAME=%%TORRENT_NAME[%%S]%%"
        if defined TPATH (
          echo Opening "!TNAME!" with save path "%COMFY_DIR%"...
          start "" "%QBT_EXE%" --skip-dialogue=true --save-path="%COMFY_DIR%" "!TPATH!"
        ) else (
          echo WARNING: Invalid selection: %%S
        )
      )
      echo.
      echo NOTE: These torrents should contain a "models" folder.
      echo       Saving into the ComfyUI folder merges into "%COMFY_DIR%\models".
    ) else (
      set "FAILED=1"
      echo ERROR: qBittorrent not available; cannot open torrents.
    )
  )
)

REM --- Create uv environment + install dependencies ---
echo.
echo Setting up Python environment in "%COMFY_DIR%"...
pushd "%COMFY_DIR%"

if exist ".venv\Scripts\python.exe" (
  echo Existing venv found at ".venv"; reusing.
) else (
  call uv venv --python 3.12
  if errorlevel 1 (
    echo uv venv failed; attempting "uv python install 3.12" then retry...
    call uv python install 3.12
    call uv venv --python 3.12
  )
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to create uv venv.
  )
)

echo.
echo Installing torch + torchvision + torchaudio (CUDA 13.0 wheels)...
call uv pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
if errorlevel 1 (
  set "FAILED=1"
  echo ERROR: Failed to install torch packages.
)

echo.
echo Installing requirements...
if exist "requirements.txt" (
  call uv pip install -r requirements.txt
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to install requirements.txt
  )
) else (
  set "FAILED=1"
  echo ERROR: requirements.txt not found in "%COMFY_DIR%".
)

if exist "manager_requirements.txt" (
  call uv pip install -r manager_requirements.txt
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to install manager_requirements.txt
  )
) else (
  echo WARNING: manager_requirements.txt not found; skipping.
)

echo.
echo Installing custom node: ComfyUI-Simple-Prompt-Batcher...
if not exist "custom_nodes\" mkdir "custom_nodes" >nul 2>nul
set "BATCHER_DIR=%CD%\custom_nodes\ComfyUI-Simple-Prompt-Batcher"
if exist "%BATCHER_DIR%\.git" (
  git -C "%BATCHER_DIR%" pull
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to update ComfyUI-Simple-Prompt-Batcher.
  )
) else (
  if exist "%BATCHER_DIR%\" (
    echo WARNING: "%BATCHER_DIR%" exists but is not a git repo; skipping clone.
  ) else (
    git clone https://github.com/ai-joe-git/ComfyUI-Simple-Prompt-Batcher.git "%BATCHER_DIR%"
    if errorlevel 1 (
      set "FAILED=1"
      echo ERROR: Failed to clone ComfyUI-Simple-Prompt-Batcher.
    )
  )
)

echo.
if "%FAILED%"=="0" (
  echo Starting ComfyUI...
  call uv run python main.py --enable-manager
  set "EXITCODE=%ERRORLEVEL%"
  popd
  exit /b %EXITCODE%
) else (
  echo One or more steps failed. Fix errors above, then re-run.
  popd
  exit /b 2
)