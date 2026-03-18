<#
.SYNOPSIS
    Main installer orchestrator for the ComfyUI lab helper.

.DESCRIPTION
    Boots from the repo checkout in Documents when needed, then handles tool
    discovery, Desktop/source installs, custom nodes, torrents, NVIDIA driver
    setup, and the optional ComfyUI launch.
#>

$ErrorActionPreference = 'Continue'

$InstallerRepoUrl = 'https://github.com/venetanji/ltx2-comfy-v915'
$ComfyUiRepoUrl    = 'https://github.com/Comfy-Org/ComfyUI'

$NonInteractive              = $env:COMFY_NONINTERACTIVE -eq '1'
$SkipDesktop                 = $env:COMFY_SKIP_DESKTOP -eq '1'
$DisableNvidiaDriver         = $env:COMFY_DISABLE_NVIDIA_DRIVER -eq '1'
$NoPause                      = $env:COMFY_NO_PAUSE -eq '1'
$StrictCustomNodeRequirements = $env:STRICT_CUSTOM_NODE_REQUIREMENTS -eq '1'

function Get-DocumentsDir {
    $docs = [Environment]::GetFolderPath('MyDocuments')
    if (-not $docs) {
        $docs = Join-Path $env:USERPROFILE 'Documents'
    }
    return $docs
}

function Normalize-PathText {
    param([string]$Path)
    if (-not $Path) { return '' }
    return $Path.TrimEnd('\').ToLowerInvariant()
}

function Refresh-SessionPath {
    $machinePath = [Environment]::GetEnvironmentVariable('PATH', 'Machine')
    $userPath    = [Environment]::GetEnvironmentVariable('PATH', 'User')
    $env:PATH    = @($machinePath, $userPath) -join ';'
}

function Find-Executable {
    param(
        [string[]]$Names,
        [string[]]$KnownPaths
    )

    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
        if ($cmd) { return $cmd }
    }

    foreach ($path in $KnownPaths) {
        if ($path -and (Test-Path $path)) { return $path }
    }

    return $null
}

function Find-Git {
    $knownGit = @(
        "$env:LocalAppData\Microsoft\WinGet\Links\git.exe",
        "$env:LocalAppData\Programs\Git\cmd\git.exe",
        "$env:LocalAppData\Programs\Git\bin\git.exe",
        "$env:ProgramFiles\Git\cmd\git.exe",
        "$env:ProgramFiles\Git\bin\git.exe",
        "${env:ProgramFiles(x86)}\Git\cmd\git.exe",
        "${env:ProgramFiles(x86)}\Git\bin\git.exe"
    )

    foreach ($hive in 'HKLM:\SOFTWARE\GitForWindows', 'HKCU:\SOFTWARE\GitForWindows') {
        try {
            $installPath = (Get-ItemProperty $hive -ErrorAction Stop).InstallPath
            if ($installPath) {
                $knownGit += "$installPath\cmd\git.exe"
                $knownGit += "$installPath\bin\git.exe"
            }
        } catch {
        }
    }

    return Find-Executable -Names @('git', 'git.exe') -KnownPaths $knownGit
}

function Ensure-Git {
    $git = Find-Git
    if ($git) { return $git }

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        return $null
    }

    Write-Host 'Installing Git.Git via winget...'
    winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
    Refresh-SessionPath
    return Find-Git
}

function Read-ToolEnvFile {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }

    foreach ($line in Get-Content $Path) {
        if ($line -match '^(?<key>[^=]+)=(?<value>.*)$') {
            $map[$matches.key] = $matches.value
        }
    }

    return $map
}

function Invoke-HelperScript {
    param(
        [string]$ScriptName,
        [object[]]$Arguments = @()
    )

    $scriptPath = Join-Path $PSScriptRoot $ScriptName
    & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath @Arguments
    return $LASTEXITCODE
}

function Bootstrap-InstallerRepo {
    $docsDir = Get-DocumentsDir
    $installerRepo = Join-Path $docsDir 'comfyui-git-installer'

    if ($env:COMFY_BOOTSTRAPPED -eq '1') { return }

    $currentRoot = Normalize-PathText $PSScriptRoot
    $targetRoot  = Normalize-PathText $installerRepo
    if ($currentRoot -eq $targetRoot) { return }

    Write-Host ''
    Write-Host "This installer should run from: `"$installerRepo`""
    Write-Host 'Bootstrapping the installer repo and relaunching...'

    $git = Ensure-Git
    if (-not $git) {
        Write-Host 'ERROR: git is required to bootstrap but was not found.'
        exit 2
    }

    if (Test-Path (Join-Path $installerRepo '.git')) {
        & $git -C $installerRepo pull
    } else {
        if (Test-Path $installerRepo) {
            Write-Host "WARNING: `"$installerRepo`" exists but is not a git repo. Please delete it and re-run."
            exit 2
        }
        & $git clone --depth 1 $InstallerRepoUrl $installerRepo
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'ERROR: Failed to clone installer repo.'
            exit 2
        }
    }

    $relaunchedScript = Join-Path $installerRepo 'scripts\Install-Comfy.ps1'
    if (-not (Test-Path $relaunchedScript)) {
        Write-Host 'ERROR: Bootstrapped repo is missing scripts\Install-Comfy.ps1'
        exit 2
    }

    $env:COMFY_BOOTSTRAPPED = '1'
    Start-Process powershell -WindowStyle Normal -ArgumentList @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $relaunchedScript
    )
    exit 0
}

function Write-ExtraModelPaths {
    param([string]$ComfySrc, [string]$ComfyData)

    $yamlPath = Join-Path $ComfySrc 'extra_model_paths.yaml'
    $content = @(
        'comfyui:',
        "  base_path: '$($ComfyData -replace '\\','/')'"
    )
    Set-Content -Path $yamlPath -Value $content -Encoding UTF8
}

function Find-ComfyDesktop {
    $knownDesktop = @(
        "$env:LocalAppData\Programs\ComfyUI\ComfyUI.exe",
        "$env:LocalAppData\Programs\ComfyUI Desktop\ComfyUI.exe",
        "$env:ProgramFiles\ComfyUI\ComfyUI.exe",
        "$env:ProgramFiles\ComfyUI Desktop\ComfyUI.exe",
        "${env:ProgramFiles(x86)}\ComfyUI\ComfyUI.exe",
        "${env:ProgramFiles(x86)}\ComfyUI Desktop\ComfyUI.exe"
    )

    return Find-Executable -Names @('ComfyUI.exe') -KnownPaths $knownDesktop
}

function Install-Desktop {
    param([string]$ComfyDesktopExe)

    if ($ComfyDesktopExe) {
        Write-Host "ComfyUI Desktop already installed: `"$ComfyDesktopExe`""
        return
    }

    if ($SkipDesktop) {
        Write-Host 'COMFY_SKIP_DESKTOP=1; skipping Desktop download.'
        return
    }

    Write-Host 'Installing ComfyUI Desktop via NSIS installer...'
    $downloadUrl = 'https://download.comfy.org/windows/nsis/x64'
    $downloadPath = Join-Path $env:TEMP 'comfyui-desktop-setup.exe'

    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $downloadUrl -OutFile $downloadPath -UseBasicParsing
    } catch {
        Write-Host 'WARNING: Could not auto-download Desktop installer.'
        Start-Process $downloadUrl
        return
    }

    if (Test-Path $downloadPath) {
        Write-Host 'Running Desktop installer silently...'
        Start-Process $downloadPath -ArgumentList '/S' -Wait
    } else {
        Write-Host 'WARNING: Desktop installer did not download correctly.'
        Start-Process $downloadUrl
    }
}

function Install-SourceCheckout {
    param(
        [string]$GitExe,
        [string]$ComfySrc,
        [string]$ComfyData
    )

    if (Test-Path (Join-Path $ComfySrc '.git')) {
        Write-Host 'Updating ComfyUI repo...'
        & $GitExe -C $ComfySrc pull
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'WARNING: git pull failed, continuing with existing checkout.'
        }
    } else {
        Write-Host "Cloning ComfyUI into `"$ComfySrc`"..."
        & $GitExe clone --depth 1 $ComfyUiRepoUrl $ComfySrc
        if ($LASTEXITCODE -ne 0) {
            throw 'git clone failed.'
        }
    }

    if (-not (Test-Path (Join-Path $ComfySrc 'main.py'))) {
        throw "ComfyUI not found at `"$(Join-Path $ComfySrc 'main.py')`" after clone/pull."
    }

    Write-Host "Writing `"$(Join-Path $ComfySrc 'extra_model_paths.yaml')`"..."
    Write-ExtraModelPaths -ComfySrc $ComfySrc -ComfyData $ComfyData
}

function Ensure-Venv {
    param([string]$UvExe, [string]$ComfySrc)

    $venvPython = Join-Path $ComfySrc '.venv\Scripts\python.exe'
    if (Test-Path $venvPython) {
        Write-Host 'Existing venv found; reusing.'
        return $true
    }

    Write-Host "Creating Python venv in `"$ComfySrc`"..."
    & $UvExe venv --python 3.12 (Join-Path $ComfySrc '.venv')
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'uv venv failed; attempting "uv python install 3.12" then retry...'
        & $UvExe python install 3.12
        & $UvExe venv --python 3.12 (Join-Path $ComfySrc '.venv')
    }

    return ($LASTEXITCODE -eq 0)
}

function Install-SourceDependencies {
    param(
        [string]$UvExe,
        [string]$ComfySrc,
        [string]$InstallerRoot,
        [string]$CustomNodesDir,
        [string]$GitExe
    )

    Push-Location $ComfySrc
    try {
        Write-Host 'Installing torch + torchvision + torchaudio (CUDA 13.0 wheels)...'
        & $UvExe pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
        if ($LASTEXITCODE -ne 0) { throw 'Failed to install torch packages.' }

        Write-Host 'Installing ComfyUI requirements...'
        if (Test-Path 'requirements.txt') {
            & $UvExe pip install -r requirements.txt
            if ($LASTEXITCODE -ne 0) { throw 'Failed to install requirements.txt.' }
        } else {
            throw 'requirements.txt not found in ComfyUI checkout.'
        }

        $installerRequirements = Join-Path $InstallerRoot 'requirements.txt'
        if (Test-Path $installerRequirements) {
            Write-Host 'Installing installer repo requirements...'
            & $UvExe pip install -r $installerRequirements
        }

        if (Test-Path 'manager_requirements.txt') {
            & $UvExe pip install -r manager_requirements.txt
            if ($LASTEXITCODE -ne 0) { throw 'Failed to install manager_requirements.txt.' }
        }

        Write-Host 'Installing custom node requirements into venv...'
        foreach ($nodeDir in Get-ChildItem -Path $CustomNodesDir -Directory -ErrorAction SilentlyContinue) {
            $req = Join-Path $nodeDir.FullName 'requirements.txt'
            if (Test-Path $req) {
                & $UvExe pip install -r $req
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "WARNING: requirements failed for $($nodeDir.Name)"
                }
            }
        }

        Write-Host 'Installing common custom-node dependencies...'
        & $UvExe pip install opencv-python imageio-ffmpeg
    } finally {
        Pop-Location
    }
}

function Start-ComfyUi {
    param(
        [string]$UvExe,
        [string]$ComfySrc,
        [string]$ComfyData,
        [string]$GitExe
    )

    if (-not (Test-Path (Join-Path $ComfySrc 'main.py'))) {
        Write-Host 'WARNING: ComfyUI source not found; skipping launch.'
        return 0
    }

    if (-not (Test-Path (Join-Path $ComfySrc 'user'))) {
        New-Item -ItemType Directory -Path (Join-Path $ComfySrc 'user') -Force | Out-Null
    }

    Start-Job -ScriptBlock {
        param($Url, $MaxIterations)
        $i = 0
        while ($i -lt $MaxIterations) {
            try {
                $response = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
                if ($response.StatusCode -lt 500) {
                    Start-Process $Url
                    break
                }
            } catch {
            }
            Start-Sleep -Seconds 2
            $i++
        }
    } -ArgumentList 'http://localhost:8188', 120 | Out-Null

    $env:GIT_PYTHON_GIT_EXECUTABLE = $GitExe
    Push-Location $ComfySrc
    try {
        & $UvExe run python main.py --reserve-vram 5 --listen 0.0.0.0 --enable-manager --use-sage-attention --base-directory $ComfyData
        return $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

function Invoke-Choice {
    param(
        [string]$Prompt,
        [string[]]$Choices,
        [string]$Default,
        [int]$TimeoutSeconds = 5
    )

    if ($NonInteractive) {
        return $Default
    }

    $choiceArgs = @('/c', ($Choices -join ''), '/n', '/t', $TimeoutSeconds, '/d', $Default, '/m', $Prompt)
    cmd /c choice @choiceArgs | Out-Null
    $result = $LASTEXITCODE
    if ($result -lt 1 -or $result -gt $Choices.Count) { return $Default }
    return $Choices[$result - 1]
}

function Main {
    Bootstrap-InstallerRepo

    $docsDir = Get-DocumentsDir
    $installerRoot = $PSScriptRoot
    $comfySrc = Join-Path $docsDir 'comfyui-git'
    $comfyData = Join-Path $docsDir 'ComfyUI'
    $customNodesList = Join-Path $installerRoot 'custom_nodes.txt'
    $customNodesDir = Join-Path $comfyData 'custom_nodes'
    $workflowsDir = Join-Path $comfyData 'user\default\workflows'
    $toolsEnv = Join-Path $env:TEMP 'comfy_tools.env'

    New-Item -ItemType Directory -Path $comfyData -Force | Out-Null
    New-Item -ItemType Directory -Path $customNodesDir -Force | Out-Null
    New-Item -ItemType Directory -Path $workflowsDir -Force | Out-Null

    Write-Host ''
    Write-Host '============================================================'
    Write-Host 'ComfyUI install (university lab helper)'
    Write-Host '- Installs into Documents (safe if run from a .zip)'
    Write-Host '- Models download to a single shared folder'
    Write-Host '============================================================'
    Write-Host "Shared ComfyUI data folder : `"$comfyData`""
    Write-Host "Installer repo folder      : `"$installerRoot`""
    Write-Host "ComfyUI source folder      : `"$comfySrc`""

    Write-Host ''
    Write-Host '[Step 2] Setting execution policy and launching OpenClaw...'
    Invoke-HelperScript -ScriptName 'Set-ExecutionPolicy.ps1' -Arguments @('-SkillsSource', (Join-Path $installerRoot '..\skills')) | Out-Null

    Write-Host ''
    Write-Host '[Step 3] Locating required tools...'
    Invoke-HelperScript -ScriptName 'Find-Tools.ps1' -Arguments @(
        '-OutFile', $toolsEnv,
        '-InstallMissing',
        '-Tools', 'git,uv,qbittorrent'
    ) | Out-Null

    $toolMap = Read-ToolEnvFile $toolsEnv
    $gitExe = $toolMap['GIT_EXE']
    $uvExe  = $toolMap['UV_EXE']
    $qbtExe = $toolMap['QBT_EXE']

    if (-not $gitExe) {
        Write-Host 'ERROR: git is not available. Aborting.'
        exit 2
    }
    if (-not $uvExe) {
        Write-Host 'ERROR: uv is not available. Aborting.'
        exit 2
    }

    Write-Host "git found : `"$gitExe`""
    Write-Host "uv  found : `"$uvExe`""
    if ($qbtExe) { Write-Host "qbt found : `"$qbtExe`"" }

    Write-Host ''
    Write-Host 'Choose install method:'
    Write-Host '  1) Desktop app (download)            [recommended for students]'
    Write-Host '  2) Source (git clone + Python deps)  [advanced / for devs]'

    $installMode = if ($NonInteractive) { '2' } else { Invoke-Choice -Prompt 'Choice [1-2] (default 2): ' -Choices @('1','2') -Default '2' }
    $doSource = $installMode -eq '2'
    $runSource = $doSource

    if ($installMode -eq '1') {
        Install-Desktop -ComfyDesktopExe (Find-ComfyDesktop)
    }

    Write-Host ''
    Write-Host 'Preparing ComfyUI source checkout...'
    try {
        Install-SourceCheckout -GitExe $gitExe -ComfySrc $comfySrc -ComfyData $comfyData
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)"
        exit 2
    }

    if ($installMode -eq '1' -and -not (Test-Path (Join-Path $comfySrc 'main.py'))) {
        $installSourceToo = if ($NonInteractive) { 'N' } else { Invoke-Choice -Prompt 'Also install ComfyUI source? [Y/N] (default N): ' -Choices @('Y','N') -Default 'N' }
        if ($installSourceToo -eq 'Y') {
            $doSource = $true
            if (-not (Test-Path (Join-Path $comfySrc '.git'))) {
                & $gitExe clone --depth 1 $ComfyUiRepoUrl $comfySrc
            } else {
                & $gitExe -C $comfySrc pull
            }
            if (Test-Path (Join-Path $comfySrc 'main.py')) {
                Write-ExtraModelPaths -ComfySrc $comfySrc -ComfyData $comfyData
            }
        }
    }

    Write-Host ''
    Write-Host 'Ensuring ComfyUI source checkout exists...'
    if (Test-Path (Join-Path $comfySrc '.git')) {
        & $gitExe -C $comfySrc pull | Out-Null
    } else {
        Write-Host 'WARNING: ComfyUI source not found. start_comfyui_git.bat will not work.'
    }

    if (Test-Path (Join-Path $installerRoot 'workflows')) {
        Write-Host ''
        Write-Host "[Step 6] Syncing workflows into `"$workflowsDir`"..."
        Copy-Item -Path (Join-Path $installerRoot 'workflows\*') -Destination $workflowsDir -Recurse -Force
    }

    if ($doSource -and (Test-Path (Join-Path $comfySrc '.venv\Scripts\python.exe'))) {
        Write-Host ''
        Write-Host '[Step 6b] Installing torch CUDA 13.0 wheels into venv before custom nodes...'
        Push-Location $comfySrc
        try {
            & $uvExe pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
            if ($LASTEXITCODE -ne 0) {
                Write-Host 'WARNING: torch CUDA pre-install failed; custom nodes may pull CPU torch.'
            }
        } finally {
            Pop-Location
        }
    }

    Write-Host ''
    Write-Host '[Step 7] Installing custom nodes...'
    Invoke-HelperScript -ScriptName 'Install-CustomNodes.ps1' -Arguments @(
        '-ListFile', $customNodesList,
        '-DestDir', $customNodesDir,
        '-UvExe', $uvExe,
        '-GitExe', $gitExe,
        '-VenvDir', (Join-Path $comfySrc '.venv')
    ) | Out-Null
    if ($LASTEXITCODE -ne 0) {
        if ($StrictCustomNodeRequirements) {
            Write-Host 'ERROR: Custom node install failed in strict mode.'
            exit 2
        }
        Write-Host 'WARNING: Some custom node requirements failed; continuing.'
    }

    $desktopVenvPython = Join-Path $comfyData '.venv\Scripts\python.exe'
    if (Test-Path $desktopVenvPython) {
        Write-Host ''
        Write-Host '[Step 8] Desktop venv detected; installing common deps + custom node requirements...'
        Push-Location $comfyData
        try {
            & $uvExe pip install opencv-python imageio-ffmpeg
            foreach ($nodeDir in Get-ChildItem -Path $customNodesDir -Directory -ErrorAction SilentlyContinue) {
                $req = Join-Path $nodeDir.FullName 'requirements.txt'
                if (Test-Path $req) {
                    & $uvExe pip install -r $req
                }
            }
        } finally {
            Pop-Location
        }
    }

    Write-Host ''
    Write-Host '[Step 9] Handling model torrents...'
    if ($qbtExe) {
        Invoke-HelperScript -ScriptName 'Handle-Torrents.ps1' -Arguments @(
            '-TorrentDir', $installerRoot,
            '-SavePath', $comfyData,
            '-QbtExe', $qbtExe
        ) | Out-Null
    } else {
        Write-Host 'WARNING: qBittorrent not found; skipping torrent step.'
    }

    if (-not $DisableNvidiaDriver) {
        Write-Host ''
        Write-Host '[Step 10] NVIDIA driver check (target 591.86)'
        $driverArgs = @('-ScriptDir', $installerRoot)
        if ($qbtExe) { $driverArgs += @('-QbtExe', $qbtExe) }
        if ($NonInteractive) { $driverArgs += '-NonInteractive' }
        Invoke-HelperScript -ScriptName 'Install-NvidiaDriver.ps1' -Arguments $driverArgs | Out-Null
    }

    if (-not $doSource) {
        Write-Host ''
        Write-Host 'Desktop install selected; skipping Python environment setup.'
        Invoke-HelperScript -ScriptName 'Patch-ManagerConfig.ps1' -Arguments @('-ComfySrc', $comfySrc, '-ComfyData', $comfyData) | Out-Null
        Write-Host ''
        Write-Host 'Done.'
        Write-Host "- Shared models folder : `"$comfyData\models`""
        Write-Host "- Shared custom nodes  : `"$customNodesDir`""
        Write-Host "- Shared workflows     : `"$workflowsDir`""
        Write-Host '- If you installed Desktop, launch it from the Start Menu.'
        Write-Host '- If you installed Source, re-run this script to update.'
        return 0
    }

    Write-Host ''
    Write-Host "[Step 11] Setting up Python environment in `"$comfySrc`"..."
    if (-not (Ensure-Venv -UvExe $uvExe -ComfySrc $comfySrc)) {
        Write-Host 'ERROR: Failed to create venv.'
        exit 2
    }

    Push-Location $comfySrc
    try {
        Write-Host 'Installing torch + torchvision + torchaudio (CUDA 13.0 wheels)...'
        & $uvExe pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130

        Write-Host 'Installing ComfyUI requirements...'
        & $uvExe pip install -r requirements.txt

        $installerRequirements = Join-Path $installerRoot 'requirements.txt'
        if (Test-Path $installerRequirements) {
            Write-Host 'Installing installer repo requirements...'
            & $uvExe pip install -r $installerRequirements
        }

        if (Test-Path 'manager_requirements.txt') {
            & $uvExe pip install -r manager_requirements.txt
        }

        Write-Host 'Installing custom node requirements into venv...'
        foreach ($nodeDir in Get-ChildItem -Path $customNodesDir -Directory -ErrorAction SilentlyContinue) {
            $req = Join-Path $nodeDir.FullName 'requirements.txt'
            if (Test-Path $req) {
                & $uvExe pip install -r $req
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "WARNING: requirements failed for $($nodeDir.Name)"
                }
            }
        }

        Write-Host 'Installing common custom-node dependencies...'
        & $uvExe pip install opencv-python imageio-ffmpeg
    } finally {
        Pop-Location
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Host 'One or more steps failed. Fix errors above, then re-run.'
        exit 2
    }

    if ($runSource) {
        Write-Host ''
        Write-Host 'Starting ComfyUI...'
        Write-Host 'ComfyUI will be available at: http://localhost:8188'
        Write-Host 'Browser will open automatically once the server is ready.'
        $exitCode = Start-ComfyUi -UvExe $uvExe -ComfySrc $comfySrc -ComfyData $comfyData -GitExe $gitExe
        Invoke-HelperScript -ScriptName 'Patch-ManagerConfig.ps1' -Arguments @('-ComfySrc', $comfySrc, '-ComfyData', $comfyData) | Out-Null
        exit $exitCode
    }

    Invoke-HelperScript -ScriptName 'Patch-ManagerConfig.ps1' -Arguments @('-ComfySrc', $comfySrc, '-ComfyData', $comfyData) | Out-Null

    Write-Host ''
    Write-Host 'Done.'
    Write-Host "- Shared models folder : `"$comfyData\models`""
    Write-Host "- Shared custom nodes  : `"$customNodesDir`""
    Write-Host "- Shared workflows     : `"$workflowsDir`""
    Write-Host '- If you installed Desktop, launch it from the Start Menu.'
    Write-Host '- If you installed Source, re-run this script to update.'

    if (-not $NoPause) {
        Write-Host ''
        Write-Host 'Press Enter to close...'
        [void](Read-Host)
    }
}

Main