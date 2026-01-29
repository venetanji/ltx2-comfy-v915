@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================================
echo ComfyUI install (university lab helper)
echo - Installs into Documents (safe if run from a .zip)
echo - Models download to a single shared folder
echo ============================================================

set "FAILED=0"
set "SCRIPT_DIR=%~dp0"
set "UV_EXE="
set "GIT_EXE="

REM --- Self-bootstrap: ensure we run from the cloned lab repo in Documents ---
set "LAB_REPO=%USERPROFILE%\Documents\comfyui-git"
set "SCRIPT_DIR_NORM=%SCRIPT_DIR%"
if "%SCRIPT_DIR_NORM:~-1%"=="\" set "SCRIPT_DIR_NORM=%SCRIPT_DIR_NORM:~0,-1%"
set "LAB_REPO_NORM=%LAB_REPO%"
if "%LAB_REPO_NORM:~-1%"=="\" set "LAB_REPO_NORM=%LAB_REPO_NORM:~0,-1%"

if /i not "%COMFY_BOOTSTRAPPED%"=="1" (
  if /i not "%SCRIPT_DIR_NORM%"=="%LAB_REPO_NORM%" (
    echo.
    echo This installer should run from: "%LAB_REPO%"
    echo Bootstrapping ^(clone/update^) the repo and relaunching...

    REM Find git quickly (bootstrap path) and try winget install if missing.
    for /f "delims=" %%P in ('where git.exe 2^>nul') do (
      if not defined GIT_EXE set "GIT_EXE=%%P"
    )
    if not defined GIT_EXE if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT_EXE=%ProgramFiles%\Git\cmd\git.exe"
    if not defined GIT_EXE if exist "%ProgramFiles%\Git\bin\git.exe" set "GIT_EXE=%ProgramFiles%\Git\bin\git.exe"
    if not defined GIT_EXE if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "GIT_EXE=%ProgramFiles(x86)%\Git\cmd\git.exe"
    if not defined GIT_EXE if exist "%ProgramFiles(x86)%\Git\bin\git.exe" set "GIT_EXE=%ProgramFiles(x86)%\Git\bin\git.exe"
    if not defined GIT_EXE (
      where winget >nul 2>nul
      if errorlevel 1 (
        echo ERROR: git is required to bootstrap but was not found, and winget is unavailable.
        echo Install Git for Windows, then re-run this script.
        exit /b 2
      )
      echo Installing Git.Git ^(source: winget^)...
      winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
      for /f "delims=" %%P in ('where git.exe 2^>nul') do (
        if not defined GIT_EXE set "GIT_EXE=%%P"
      )
    )
    if not defined GIT_EXE (
      echo ERROR: git is still not available after install.
      exit /b 2
    )

    if exist "%LAB_REPO%\.git" (
      "!GIT_EXE!" -C "%LAB_REPO%" pull
    ) else (
      if exist "%LAB_REPO%\" (
        echo WARNING: "%LAB_REPO%" exists but is not a git repo; skipping bootstrap.
        echo Please delete the folder and re-run.
        exit /b 2
      )
      "!GIT_EXE!" clone --depth 1 https://github.com/venetanji/ltx2-comfy-v915 "%LAB_REPO%"
      if errorlevel 1 (
        echo ERROR: Failed to clone lab repo.
        exit /b 2
      )
    )

    if not exist "%LAB_REPO%\install_comfy.bat" (
      echo ERROR: Bootstrapped repo is missing install_comfy.bat
      exit /b 2
    )

    set "COMFY_BOOTSTRAPPED=1"
    call "%LAB_REPO%\install_comfy.bat"
    exit /b %ERRORLEVEL%
  )
)

REM --- Fixed install locations (do not depend on where the .bat lives) ---
set "COMFY_DATA=%USERPROFILE%\Documents\ComfyUI"
set "COMFY_SRC=%LAB_REPO%\ComfyUI"
set "CUSTOM_NODES_LIST=%SCRIPT_DIR%custom_nodes.txt"
set "CUSTOM_NODES_DIR=%COMFY_DATA%\custom_nodes"
set "WORKFLOWS_DIR=%COMFY_DATA%\workflows"

if not exist "%COMFY_DATA%\" mkdir "%COMFY_DATA%" >nul 2>nul
if not exist "%CUSTOM_NODES_DIR%\" mkdir "%CUSTOM_NODES_DIR%" >nul 2>nul
if not exist "%WORKFLOWS_DIR%\" mkdir "%WORKFLOWS_DIR%" >nul 2>nul

echo.
echo Shared ComfyUI data folder: "%COMFY_DATA%"
echo Lab repo folder: "%LAB_REPO%"
echo Source (vendored) folder: "%COMFY_SRC%"

REM --- Choose install mode (default: Desktop) ---
set "INSTALL_MODE="
echo.
echo Choose install method:
echo   1^) Desktop app (download)            [recommended for students]
echo   2^) Source (git clone + Python deps)  [advanced / for devs]
set /p "INSTALL_MODE=Choice [1-2] (default 1): "
if not defined INSTALL_MODE set "INSTALL_MODE=1"
if not "%INSTALL_MODE%"=="1" if not "%INSTALL_MODE%"=="2" set "INSTALL_MODE=1"

set "DO_SOURCE=0"
set "RUN_SOURCE=0"
if "%INSTALL_MODE%"=="2" (
  set "DO_SOURCE=1"
  set "RUN_SOURCE=1"
)

REM --- Install / locate uv (source install only) ---
if "%DO_SOURCE%"=="1" (
  echo.
  call :FindUv
  if not defined UV_EXE (
    where winget >nul 2>nul
    if errorlevel 1 (
      set "FAILED=1"
      echo ERROR: uv not found and winget is not available.
      echo Install "App Installer" from Microsoft Store or install uv manually.
    ) else (
      echo Installing astral-sh.uv ^(source: winget^)...
      winget install --id=astral-sh.uv -e --source winget --accept-source-agreements --accept-package-agreements
      if errorlevel 1 echo WARNING: uv install via winget failed.
      call :FindUv
    )
  )
  if not defined UV_EXE (
    set "FAILED=1"
    echo ERROR: uv is still not available after install.
  ) else (
    echo uv found: "%UV_EXE%"
  )
)

REM --- Install / locate Git ---
echo.
call :FindGit
if not defined GIT_EXE (
  where winget >nul 2>nul
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: git not found and winget is not available.
    echo Install "App Installer" from Microsoft Store or install Git manually.
  ) else (
    echo Installing Git.Git ^(source: winget^)...
    winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
    if errorlevel 1 echo WARNING: Git install via winget failed.
    call :FindGit
  )
)
if not defined GIT_EXE (
  set "FAILED=1"
  echo ERROR: git is still not available after install.
) else (
  echo git found: "%GIT_EXE%"
)


if "%FAILED%"=="1" (
  echo.
  echo Aborting due to missing prerequisites.
  exit /b 2
)

REM --- Install ComfyUI Desktop (winget) OR clone ComfyUI source ---
if "%INSTALL_MODE%"=="1" goto :install_desktop
goto :install_source_primary

:install_desktop
echo.
echo Installing ComfyUI Desktop via NSIS installer...
set "COMFY_DESKTOP_DL=https://download.comfy.org/windows/nsis/x64"
set "COMFY_DESKTOP_EXE=%TEMP%\comfyui-desktop-setup.exe"

powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; Write-Host ('Downloading: %COMFY_DESKTOP_DL%'); $wc = New-Object Net.WebClient; $wc.Headers.Add('User-Agent','comfy-lab-installer'); $wc.DownloadFile('%COMFY_DESKTOP_DL%','%COMFY_DESKTOP_EXE%');"
if errorlevel 1 (
  echo WARNING: Could not auto-download Desktop installer.
  echo Opening download page: %COMFY_DESKTOP_DL%
  start "" "%COMFY_DESKTOP_DL%"
) else (
  if exist "%COMFY_DESKTOP_EXE%" (
    echo Running Desktop installer...
    start "" /wait "%COMFY_DESKTOP_EXE%" /S
  ) else (
    echo WARNING: Desktop installer did not download correctly.
    start "" "%COMFY_DESKTOP_DL%"
  )
)
goto :after_primary_install

:install_source_primary
echo.
echo Preparing ComfyUI source (vendored in lab repo)...
if exist "%LAB_REPO%\.git" (
  echo Updating lab repo...
  call "%GIT_EXE%" -C "%LAB_REPO%" pull
  if errorlevel 1 (
    echo WARNING: Failed to update lab repo; continuing.
  )
)

if not exist "%COMFY_SRC%\main.py" (
  echo ERROR: Vendored ComfyUI not found at: "%COMFY_SRC%"
  echo        Expected: "%COMFY_SRC%\main.py"
  exit /b 2
)

REM Ensure extra_model_paths.yaml points at the shared Documents folder.
REM This keeps model discovery consistent even if users forget --base-directory.
echo.
echo Writing "%COMFY_SRC%\extra_model_paths.yaml"...
>  "%COMFY_SRC%\extra_model_paths.yaml" echo comfyui:
>> "%COMFY_SRC%\extra_model_paths.yaml" echo   base_path: "%COMFY_DATA%"

:after_primary_install

REM --- Offer to install source alongside Desktop (useful on second run) ---
if "%INSTALL_MODE%"=="1" (
  if not exist "%COMFY_SRC%\main.py" (
    echo.
    echo Optional: install ComfyUI source checkout into "%COMFY_SRC%" as well?
    set "INSTALL_SOURCE_TOO="
    set /p "INSTALL_SOURCE_TOO=Install source too? [y/N]: "
    if /i "%INSTALL_SOURCE_TOO%"=="Y" set "DO_SOURCE=1"
    if /i "%INSTALL_SOURCE_TOO%"=="YES" set "DO_SOURCE=1"
    if "%DO_SOURCE%"=="1" (
      echo.
      call :FindUv
      if not defined UV_EXE (
        where winget >nul 2>nul
        if errorlevel 1 (
          set "FAILED=1"
          echo ERROR: uv not found and winget is not available.
          echo Install "App Installer" from Microsoft Store or install uv manually.
        ) else (
          echo Installing astral-sh.uv ^(source: winget^)...
          winget install --id=astral-sh.uv -e --source winget --accept-source-agreements --accept-package-agreements
          if errorlevel 1 echo WARNING: uv install via winget failed.
          call :FindUv
        )
      )
      if not defined UV_EXE (
        set "FAILED=1"
        echo ERROR: uv is still not available after install.
      ) else (
        echo uv found: "%UV_EXE%"
      )
      if "%FAILED%"=="1" exit /b 2
      goto :install_source_after_desktop
    )
  )
)

goto :after_install_choice

:install_source_after_desktop
echo.
echo Preparing ComfyUI source (vendored in lab repo)...
if exist "%LAB_REPO%\.git" (
  echo Updating lab repo...
  call "%GIT_EXE%" -C "%LAB_REPO%" pull
  if errorlevel 1 echo WARNING: Failed to update lab repo.
)
if exist "%COMFY_SRC%\main.py" (
  echo.
  echo Writing "%COMFY_SRC%\extra_model_paths.yaml"...
  >  "%COMFY_SRC%\extra_model_paths.yaml" echo comfyui:
  >> "%COMFY_SRC%\extra_model_paths.yaml" echo   base_path: "%COMFY_DATA%"
 ) else (
  echo ERROR: Vendored ComfyUI not found at: "%COMFY_SRC%"
  exit /b 2
)

:after_install_choice

REM --- Copy workflows into the shared workflows folder (used by Desktop) ---
if exist "%SCRIPT_DIR%workflows\" (
  echo.
  echo Syncing workflows into "%WORKFLOWS_DIR%"...
  xcopy "%SCRIPT_DIR%workflows\*" "%WORKFLOWS_DIR%\" /E /I /Y >nul
) else (
  echo.
  echo No workflows folder found next to this script; skipping workflow copy.
)

REM --- Install/update custom nodes into the shared Documents folder ---
echo.
if not exist "%CUSTOM_NODES_LIST%" (
  echo No "%CUSTOM_NODES_LIST%" found; skipping custom nodes.
) else (
  echo Installing custom nodes into: "%CUSTOM_NODES_DIR%"
  for /f "usebackq delims=" %%L in ("%CUSTOM_NODES_LIST%") do (
    set "LINE=%%L"
    if defined LINE (
      for /f "tokens=* delims= " %%A in ("!LINE!") do set "LINE=%%A"
      if not "!LINE:~0,1!"=="#" if not "!LINE:~0,1!"==";" (
        if defined LINE call :InstallCustomNode "!LINE!"
      )
    )
  )
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
  if not defined QBT_EXE set "QBT_EXE=%%P"
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

REM --- Ensure qBittorrent layout config (no subfolder) ---
REM This makes torrents extract their contents directly into the save path.
if "%FAILED%"=="0" call :QbtEnsureNoSubfolder

REM --- Torrent prompt (download models into the shared Documents folder) ---
echo.
echo Looking for .torrent files next to this script...
set "TORRENT_COUNT=0"
for %%F in ("%SCRIPT_DIR%*.torrent") do (
  REM Exclude NVIDIA driver torrent from the models list.
  if /i not "%%~nxF"=="nvidia-driver.torrent" (
    set /a TORRENT_COUNT+=1
    set "TORRENT[!TORRENT_COUNT!]=%%~fF"
    set "TORRENT_NAME[!TORRENT_COUNT!]=%%~nxF"
  )
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

      echo.
      echo Opening the models folder in Explorer...
      start "" explorer "%COMFY_DATA%"

      for %%S in (!TORRENT_SELECTION!) do (
        call set "TPATH=%%TORRENT[%%S]%%"
        call set "TNAME=%%TORRENT_NAME[%%S]%%"
        if defined TPATH (
          echo Opening "!TNAME!" with save path "%COMFY_DATA%"...
          start "" "%QBT_EXE%" --skip-dialog=true --save-path="%COMFY_DATA%" "!TPATH!"
        ) else (
          echo WARNING: Invalid selection: %%S
        )
      )
      echo.
      echo NOTE: These torrents should contain a "models" folder.
      echo       Saving into "%COMFY_DATA%" merges into "%COMFY_DATA%\models".
    ) else (
      set "FAILED=1"
      echo ERROR: qBittorrent not available; cannot open torrents.
    )
  )
)

REM --- If installing from source: create uv environment + install dependencies ---
echo.
if "%DO_SOURCE%"=="0" (
  echo Desktop install selected; skipping Python environment setup.
  goto :after_python_setup
)

echo Setting up Python environment in "%COMFY_SRC%"...
pushd "%COMFY_SRC%"

if exist ".venv\Scripts\python.exe" (
  echo Existing venv found at ".venv"; reusing.
) else (
  call "%UV_EXE%" venv --python 3.12
  if errorlevel 1 (
    echo uv venv failed; attempting "uv python install 3.12" then retry...
    call "%UV_EXE%" python install 3.12
    call "%UV_EXE%" venv --python 3.12
  )
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to create uv venv.
  )
)

echo.
echo Installing torch + torchvision + torchaudio (CUDA 13.0 wheels)...
call "%UV_EXE%" pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
if errorlevel 1 (
  set "FAILED=1"
  echo ERROR: Failed to install torch packages.
)

echo.
echo Installing requirements...
if exist "requirements.txt" (
  call "%UV_EXE%" pip install -r requirements.txt
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to install requirements.txt
  )
) else (
  set "FAILED=1"
  echo ERROR: requirements.txt not found in "%COMFY_SRC%".
)

if exist "manager_requirements.txt" (
  call "%UV_EXE%" pip install -r manager_requirements.txt
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to install manager_requirements.txt
  )
) else (
  echo WARNING: manager_requirements.txt not found; skipping.
)

echo.
echo Custom nodes already installed into "%CUSTOM_NODES_DIR%".

echo.
echo NVIDIA driver install is disabled by default for lab machines.
echo If you need it, re-enable the :InstallNvidiaDriver call in this script.
REM if "%FAILED%"=="0" call :InstallNvidiaDriver

echo.
if "%FAILED%"=="0" (
  if "%RUN_SOURCE%"=="1" (
    echo Starting ComfyUI...
    set "GIT_PYTHON_GIT_EXECUTABLE=%GIT_EXE%"
    call "%UV_EXE%" run python main.py --enable-manager --base-directory "%COMFY_DATA%"
    set "EXITCODE=%ERRORLEVEL%"
    popd
    exit /b %EXITCODE%
  ) else (
    echo.
    echo Source installed/updated. Desktop install remains the default launcher.
    popd
    goto :after_python_setup
  )
) else (
  echo One or more steps failed. Fix errors above, then re-run.
  popd
  exit /b 2
)

:after_python_setup
echo.
echo Done.
echo - Shared models folder: "%COMFY_DATA%\models"
echo - Shared custom nodes folder: "%CUSTOM_NODES_DIR%"
echo - Shared workflows folder: "%WORKFLOWS_DIR%"
echo - If you installed Desktop, launch it from Start Menu.
echo - If you installed Source, re-run this script to update.
exit /b 0

:InstallCustomNode
REM Installs/updates a custom node from a line in custom_nodes.txt
REM Supported formats:
REM   https://github.com/OWNER/REPO.git
REM   https://github.com/OWNER/REPO.git|FolderName
REM   https://github.com/OWNER/REPO.git#branch
REM   https://github.com/OWNER/REPO.git#branch|FolderName
set "RAW=%~1"
set "URL=%RAW%"
set "FOLDER="
set "BRANCH="

REM Split optional folder name using |
for /f "tokens=1,2 delims=|" %%A in ("%RAW%") do (
  set "URL=%%~A"
  set "FOLDER=%%~B"
)

REM Split optional branch using #
for /f "tokens=1,2 delims=#" %%A in ("%URL%") do (
  set "URL_ONLY=%%~A"
  set "BRANCH=%%~B"
)
if not defined URL_ONLY set "URL_ONLY=%URL%"

if not defined FOLDER (
  REM Common case: https://github.com/OWNER/REPO(.git)
  for /f "tokens=1-5 delims=/" %%a in ("!URL_ONLY!") do set "FOLDER=%%e"

  REM Fallback: take the last token if the above didn't yield a name.
  if not defined FOLDER (
    set "URL_TOKENS=!URL_ONLY:/= !"
    for %%Z in (!URL_TOKENS!) do set "FOLDER=%%Z"
  )

  if /i "!FOLDER:~-4!"==".git" set "FOLDER=!FOLDER:~0,-4!"
)

if not defined FOLDER (
  echo WARNING: Could not parse custom node line: %RAW%
  goto :eof
)

set "DEST=%CUSTOM_NODES_DIR%\%FOLDER%"
echo(
echo [custom_nodes] %FOLDER%
echo   url: %URL_ONLY%
if defined BRANCH echo   branch: %BRANCH%
echo   path: %DEST%

if exist "%DEST%\.git" (
  call "%GIT_EXE%" -C "%DEST%" pull
  if errorlevel 1 echo WARNING: Failed to update %FOLDER%
  goto :eof
)

if exist "%DEST%\" (
  echo WARNING: "%DEST%" exists but is not a git repo; skipping.
  goto :eof
)

if defined BRANCH (
  call "%GIT_EXE%" clone --depth 1 --branch "%BRANCH%" "%URL_ONLY%" "%DEST%"
) else (
  call "%GIT_EXE%" clone --depth 1 "%URL_ONLY%" "%DEST%"
)
if errorlevel 1 echo WARNING: Failed to clone %FOLDER%
goto :eof

:InstallNvidiaDriver
set "NVIDIA_TARGET=591.74"
set "NVIDIA_URL=https://us.download.nvidia.com/Windows/591.74/591.74-desktop-win10-win11-64bit-international-dch-whql.exe"
set "NVIDIA_EXE=%TEMP%\nvidia-driver-591.74.exe"
set "NVIDIA_DL_DIR=%TEMP%\nvidia-driver-%NVIDIA_TARGET%"

echo Installing NVIDIA driver (%NVIDIA_TARGET%)...

REM Check installed NVIDIA driver version; skip if already up-to-date.
set "NVIDIA_UPTODATE="
for /f "usebackq delims=" %%V in (`powershell -NoProfile -Command "$vc = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' } | Select-Object -First 1; if (-not $vc) { 'NO_NVIDIA' ; exit 0 }; $dv = [string]$vc.DriverVersion; $last4 = ($dv -replace '[^0-9]',''); if ($last4.Length -ge 4) { $last4 = $last4.Substring($last4.Length-4) } else { $last4 = '' }; if ($last4 -match '^[0-9]{4}$') { $major = 500 + [int]$last4.Substring(0,2); $minor = [int]$last4.Substring(2,2); '{0}.{1:00}' -f $major,$minor } else { 'UNKNOWN' }"`) do set "NVIDIA_INSTALLED=%%V"

if /i "%NVIDIA_INSTALLED%"=="NO_NVIDIA" (
  echo No NVIDIA GPU detected; skipping NVIDIA driver install.
  exit /b 0
)

if /i "%NVIDIA_INSTALLED%"=="UNKNOWN" (
  echo WARNING: Could not determine installed NVIDIA driver version; will run installer.
) else (
  echo Detected NVIDIA driver: %NVIDIA_INSTALLED%
  for /f "tokens=1,2 delims=." %%A in ("%NVIDIA_INSTALLED%") do (
    set "INST_MAJOR=%%A"
    set "INST_MINOR=%%B"
  )
  for /f "tokens=1,2 delims=." %%A in ("%NVIDIA_TARGET%") do (
    set "TGT_MAJOR=%%A"
    set "TGT_MINOR=%%B"
  )
  if not defined INST_MAJOR set "INST_MAJOR=0"
  if not defined INST_MINOR set "INST_MINOR=0"
  if not defined TGT_MAJOR set "TGT_MAJOR=0"
  if not defined TGT_MINOR set "TGT_MINOR=0"

  if !INST_MAJOR! GTR !TGT_MAJOR! (
    echo NVIDIA driver already up to date; skipping.
    exit /b 0
  )
  if !INST_MAJOR! EQU !TGT_MAJOR! if !INST_MINOR! GEQ !TGT_MINOR! (
    echo NVIDIA driver already up to date; skipping.
    exit /b 0
  )
)

if exist "%NVIDIA_EXE%" goto :nvidia_run

REM Locate an optional NVIDIA driver torrent next to the script.
set "NVIDIA_TORRENT="
if exist "%SCRIPT_DIR%nvidia-driver.torrent" set "NVIDIA_TORRENT=%SCRIPT_DIR%nvidia-driver.torrent"

echo.
echo NVIDIA driver installer not found locally.
echo Choose how to obtain it:
echo   1^) Skip NVIDIA driver install
echo   2^) Download via web ^(Invoke-WebRequest; can be slow^)
if defined NVIDIA_TORRENT (
  echo   3^) Download via torrent: "%NVIDIA_TORRENT%"
) else (
  echo   3^) Download via torrent: ^(no NVIDIA/driver .torrent found next to this script^)
)

set "NVIDIA_GET="
if defined NVIDIA_TORRENT (
  set /p "NVIDIA_GET=Choice [1-3] (default 3): "
  if not defined NVIDIA_GET set "NVIDIA_GET=3"
) else (
  set /p "NVIDIA_GET=Choice [1-3] (default 2): "
  if not defined NVIDIA_GET set "NVIDIA_GET=2"
)

if "%NVIDIA_GET%"=="1" (
  echo Skipping NVIDIA driver install.
  exit /b 0
)

if "%NVIDIA_GET%"=="3" (
  if not defined NVIDIA_TORRENT (
    echo ERROR: No NVIDIA/driver torrent found next to this script.
    echo        Place a file like "nvidia-driver.torrent" next to this .bat, or choose option 2.
    set "FAILED=1"
    exit /b 0
  )
  if not exist "%NVIDIA_DL_DIR%" mkdir "%NVIDIA_DL_DIR%" >nul 2>nul

  if not defined QBT_EXE (
    echo ERROR: qBittorrent not available; cannot use torrent download.
    set "FAILED=1"
    exit /b 0
  )

  echo.
  echo Starting qBittorrent for NVIDIA driver torrent...
  start "" "%QBT_EXE%"
  timeout /t 2 /nobreak >nul
  echo Opening NVIDIA driver torrent with save path "%NVIDIA_DL_DIR%"...
  start "" "%QBT_EXE%" --skip-dialog=true --save-path="%NVIDIA_DL_DIR%" "%NVIDIA_TORRENT%"
  echo.
  echo Wait for the driver download to finish, then press Enter to continue.
  pause >nul

  set "NVIDIA_EXE_TORRENT="
  for /r "%NVIDIA_DL_DIR%" %%X in (*.exe) do (
    if not defined NVIDIA_EXE_TORRENT set "NVIDIA_EXE_TORRENT=%%~fX"
  )
  if defined NVIDIA_EXE_TORRENT (
    set "NVIDIA_EXE=!NVIDIA_EXE_TORRENT!"
  )
  if not exist "!NVIDIA_EXE!" (
    set "FAILED=1"
    echo ERROR: Could not find a downloaded NVIDIA driver .exe in "%NVIDIA_DL_DIR%".
    exit /b 0
  )
  goto :nvidia_run
)

REM Option 2: web download
echo.
echo Downloading: %NVIDIA_URL%
echo Please wait, this can take several minutes...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%NVIDIA_URL%' -OutFile '%NVIDIA_EXE%'"

if not exist "%NVIDIA_EXE%" (
  set "FAILED=1"
  echo ERROR: Failed to download NVIDIA driver.
  exit /b 0
)

:nvidia_run
echo Launching NVIDIA driver installer...
echo IMPORTANT: DO NOT REBOOT this computer. These machines are reset on reboot.
echo If the installer requests a reboot, close it and proceed without rebooting.
start "" /wait "%NVIDIA_EXE%"
exit /b 0

:FindUv
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
exit /b 0

:FindGit
set "GIT_EXE="
for /f "delims=" %%P in ('where git.exe 2^>nul') do (
  if not defined GIT_EXE set "GIT_EXE=%%P"
)
if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT_EXE=%ProgramFiles%\Git\cmd\git.exe"
if not defined GIT_EXE if exist "%ProgramFiles%\Git\bin\git.exe" set "GIT_EXE=%ProgramFiles%\Git\bin\git.exe"
if not defined GIT_EXE if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "GIT_EXE=%ProgramFiles(x86)%\Git\cmd\git.exe"
if not defined GIT_EXE if exist "%ProgramFiles(x86)%\Git\bin\git.exe" set "GIT_EXE=%ProgramFiles(x86)%\Git\bin\git.exe"
exit /b 0

:QbtEnsureNoSubfolder
set "QBT_INI=%AppData%\qBittorrent\qBittorrent.ini"
if not exist "%AppData%\qBittorrent\" mkdir "%AppData%\qBittorrent" >nul 2>nul

REM If already configured, do nothing (common on second run).
if exist "%QBT_INI%" (
  findstr /i /c:"Session\TorrentContentLayout=NoSubfolder" "%QBT_INI%" >nul 2>nul
  if not errorlevel 1 (
    echo(
    echo qBittorrent already configured ^(NoSubfolder^). Skipping config patch.
    exit /b 0
  )
)


REM If qBittorrent is currently running, it won't pick up ini changes.
tasklist /fi "imagename eq qbittorrent.exe" 2>nul | find /i "qbittorrent.exe" >nul
if not errorlevel 1 (
  echo.
  echo qBittorrent is currently running.
  echo Please CLOSE qBittorrent completely so the config change takes effect.
  echo Then press Enter to continue...
  pause >nul
  goto :QbtEnsureNoSubfolder
)


echo.
echo Configuring qBittorrent to not create torrent subfolders...
echo.>> "%QBT_INI%"
echo [BitTorrent]>> "%QBT_INI%"
echo Session\TorrentContentLayout=NoSubfolder>> "%QBT_INI%"

exit /b 0