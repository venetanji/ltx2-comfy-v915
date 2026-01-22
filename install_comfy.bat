@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================================
echo ComfyUI install (source) + models via torrents
echo ============================================================

set "FAILED=0"
set "SCRIPT_DIR=%~dp0"
set "UV_EXE="
set "GIT_EXE="

REM --- Install / locate uv ---
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

REM --- Clone ComfyUI from source ---
echo.
set "COMFY_DIR=%SCRIPT_DIR%ComfyUI"
if exist "%COMFY_DIR%\" (
  echo ComfyUI already exists at: "%COMFY_DIR%"
  echo Updating repo...
  call "%GIT_EXE%" -C "%COMFY_DIR%" pull
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to update ComfyUI repo.
  )
) else (
  echo Cloning ComfyUI...
  pushd "%SCRIPT_DIR%"
  call "%GIT_EXE%" clone https://github.com/Comfy-Org/ComfyUI
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

REM --- Ensure qBittorrent layout config (no subfolder) ---
REM This makes torrents extract their contents directly into the save path.
if "%FAILED%"=="0" call :QbtEnsureNoSubfolder

REM --- Torrent prompt (download models into ComfyUI folder) ---
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

      for %%S in (!TORRENT_SELECTION!) do (
        call set "TPATH=%%TORRENT[%%S]%%"
        call set "TNAME=%%TORRENT_NAME[%%S]%%"
        if defined TPATH (
          echo Opening "!TNAME!" with save path "%COMFY_DIR%"...
          start "" "%QBT_EXE%" --skip-dialog=true --save-path="%COMFY_DIR%" "!TPATH!"
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
  echo ERROR: requirements.txt not found in "%COMFY_DIR%".
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
echo Installing custom node: ComfyUI-Simple-Prompt-Batcher...
if not exist "custom_nodes\" mkdir "custom_nodes" >nul 2>nul
set "BATCHER_DIR=%CD%\custom_nodes\ComfyUI-Simple-Prompt-Batcher"
if exist "%BATCHER_DIR%\.git" (
  call "%GIT_EXE%" -C "%BATCHER_DIR%" pull
  if errorlevel 1 (
    set "FAILED=1"
    echo ERROR: Failed to update ComfyUI-Simple-Prompt-Batcher.
  )
) else (
  if exist "%BATCHER_DIR%\" (
    echo WARNING: "%BATCHER_DIR%" exists but is not a git repo; skipping clone.
  ) else (
    call "%GIT_EXE%" clone https://github.com/ai-joe-git/ComfyUI-Simple-Prompt-Batcher.git "%BATCHER_DIR%"
    if errorlevel 1 (
      set "FAILED=1"
      echo ERROR: Failed to clone ComfyUI-Simple-Prompt-Batcher.
    )
  )
)

echo.
if "%FAILED%"=="0" call :InstallNvidiaDriver

echo.
if "%FAILED%"=="0" (
  echo Starting ComfyUI...
  set "GIT_PYTHON_GIT_EXECUTABLE=%GIT_EXE%"
  call "%UV_EXE%" run python main.py --enable-manager
  set "EXITCODE=%ERRORLEVEL%"
  popd
  exit /b %EXITCODE%
) else (
  echo One or more steps failed. Fix errors above, then re-run.
  popd
  exit /b 2
)

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
powershell -NoProfile -Command "$ProgressPreference='Continue'; Invoke-WebRequest -Uri '%NVIDIA_URL%' -OutFile '%NVIDIA_EXE%'"

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
  set "UV_EXE=%%P"
  goto :eof
)
for /f "delims=" %%P in ('where uv 2^>nul') do (
  set "UV_EXE=%%P"
  goto :eof
)
if exist "%LocalAppData%\Microsoft\WinGet\Links\uv.exe" set "UV_EXE=%LocalAppData%\Microsoft\WinGet\Links\uv.exe"
goto :eof

:FindGit
set "GIT_EXE="
for /f "delims=" %%P in ('where git.exe 2^>nul') do (
  set "GIT_EXE=%%P"
  goto :eof
)
if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT_EXE=%ProgramFiles%\Git\cmd\git.exe"
if not defined GIT_EXE if exist "%ProgramFiles%\Git\bin\git.exe" set "GIT_EXE=%ProgramFiles%\Git\bin\git.exe"
if not defined GIT_EXE if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "GIT_EXE=%ProgramFiles(x86)%\Git\cmd\git.exe"
if not defined GIT_EXE if exist "%ProgramFiles(x86)%\Git\bin\git.exe" set "GIT_EXE=%ProgramFiles(x86)%\Git\bin\git.exe"
goto :eof

:QbtEnsureNoSubfolder
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

set "QBT_INI=%AppData%\qBittorrent\qBittorrent.ini"
if not exist "%AppData%\qBittorrent\" mkdir "%AppData%\qBittorrent" >nul 2>nul

echo.
echo Configuring qBittorrent to not create torrent subfolders...
set "QBT_PS1=%TEMP%\qbt_set_layout.ps1"
>  "%QBT_PS1%" echo $p = Join-Path $env:APPDATA 'qBittorrent\qBittorrent.ini'
>> "%QBT_PS1%" echo $section = 'BitTorrent'
>> "%QBT_PS1%" echo $key = 'Session\TorrentContentLayout'
>> "%QBT_PS1%" echo $val = 'NoSubfolder'
>> "%QBT_PS1%" echo if (-not (Test-Path -LiteralPath $p)) { New-Item -ItemType File -Force -Path $p ^| Out-Null }
>> "%QBT_PS1%" echo $lines = Get-Content -LiteralPath $p -ErrorAction SilentlyContinue
>> "%QBT_PS1%" echo if ($null -eq $lines) { $lines = @() }
>> "%QBT_PS1%" echo $out = New-Object 'System.Collections.Generic.List[string]'
>> "%QBT_PS1%" echo $inSection = $false
>> "%QBT_PS1%" echo $seenSection = $false
>> "%QBT_PS1%" echo $setKey = $false
>> "%QBT_PS1%" echo foreach ($line in $lines) {
>> "%QBT_PS1%" echo   $trim = $line.Trim()
>> "%QBT_PS1%" echo   if ($trim.StartsWith('[') -and $trim.EndsWith(']')) {
>> "%QBT_PS1%" echo     if ($inSection -and -not $setKey) { $out.Add($key + '=' + $val); $setKey = $true }
>> "%QBT_PS1%" echo     $name = $trim.Substring(1, $trim.Length - 2)
>> "%QBT_PS1%" echo     $inSection = ($name -ieq $section)
>> "%QBT_PS1%" echo     if ($inSection) { $seenSection = $true }
>> "%QBT_PS1%" echo     $out.Add($line)
>> "%QBT_PS1%" echo     continue
>> "%QBT_PS1%" echo   }
>> "%QBT_PS1%" echo   if ($inSection -and ($trim -like ($key + '=*'))) { $out.Add($key + '=' + $val); $setKey = $true } else { $out.Add($line) }
>> "%QBT_PS1%" echo }
>> "%QBT_PS1%" echo if ($inSection -and -not $setKey) { $out.Add($key + '=' + $val); $setKey = $true }
>> "%QBT_PS1%" echo if (-not $seenSection) {
>> "%QBT_PS1%" echo   if ($out.Count -gt 0 -and $out[$out.Count-1] -ne '') { $out.Add('') }
>> "%QBT_PS1%" echo   $out.Add('[' + $section + ']')
>> "%QBT_PS1%" echo   $out.Add($key + '=' + $val)
>> "%QBT_PS1%" echo }
>> "%QBT_PS1%" echo [System.IO.File]::WriteAllLines($p, $out.ToArray(), (New-Object System.Text.UTF8Encoding($false)))

powershell -NoProfile -ExecutionPolicy Bypass -File "%QBT_PS1%"
del /q "%QBT_PS1%" >nul 2>nul

exit /b 0