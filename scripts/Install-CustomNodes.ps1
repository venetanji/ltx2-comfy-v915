<#
.SYNOPSIS
    Clones or updates custom nodes listed in a text file, then installs their
    Python requirements into the specified uv-managed venv.

.PARAMETER ListFile
    Path to the custom_nodes.txt file. Each non-comment line is a git URL,
    optionally with a branch (#branch) and/or a folder name (|FolderName).

.PARAMETER DestDir
    Destination directory where node repos are cloned (e.g. %COMFY_DATA%\custom_nodes).

.PARAMETER UvExe
    Path to the uv executable. If omitted, tries to find uv on PATH.

.PARAMETER GitExe
    Path to the git executable. If omitted, tries git on PATH.

.PARAMETER VenvDir
    Path to the .venv directory created by "uv venv" (e.g. %COMFY_SRC%\.venv).
    If omitted or the venv does not yet exist, requirements install is skipped.

.PARAMETER Strict
    Exit non-zero if any requirements.txt install fails.
#>
param(
    [Parameter(Mandatory)][string]$ListFile,
    [Parameter(Mandatory)][string]$DestDir,
    [string]$UvExe   = 'uv',
    [string]$GitExe  = 'git',
    [string]$VenvDir = '',
    [switch]$Strict
)

$ErrorActionPreference = 'Continue'
$failed = $false

if (-not (Test-Path $ListFile)) {
    Write-Warning "Custom nodes list not found: $ListFile"
    exit 0
}

if (-not (Test-Path $DestDir)) {
    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
}

function Install-CustomNode {
    param([string]$Raw)

    $raw = $Raw.Trim()
    if (-not $raw -or $raw -match '^[#;]') { return }

    # Split optional folder name  url|FolderName
    $url    = $raw
    $folder = $null
    if ($raw -match '\|') {
        $parts  = $raw -split '\|', 2
        $url    = $parts[0].Trim()
        $folder = $parts[1].Trim()
    }

    # Split optional branch  url#branch
    $branch  = $null
    $urlOnly = $url
    if ($url -match '#') {
        $parts   = $url -split '#', 2
        $urlOnly = $parts[0].Trim()
        $branch  = $parts[1].Trim()
    }

    # Derive folder name from last URL segment if not supplied
    if (-not $folder) {
        $folder = ($urlOnly -split '/')[-1] -replace '\.git$', ''
    }
    if (-not $folder) {
        Write-Warning "Could not parse node line: $Raw"
        return
    }

    $dest = Join-Path $DestDir $folder
    Write-Host ""
    Write-Host "[custom_nodes] $folder"
    Write-Host "  url: $urlOnly"
    if ($branch) { Write-Host "  branch: $branch" }
    Write-Host "  path: $dest"

    if (Test-Path (Join-Path $dest '.git')) {
        & $GitExe -C $dest pull
        if ($LASTEXITCODE -ne 0) { Write-Warning "Failed to update $folder" }
        return
    }

    if (Test-Path $dest) {
        Write-Warning "$dest exists but is not a git repo; skipping."
        return
    }

    $cloneArgs = @('clone', '--depth', '1')
    if ($branch) { $cloneArgs += @('--branch', $branch) }
    $cloneArgs += @($urlOnly, $dest)

    & $GitExe @cloneArgs
    if ($LASTEXITCODE -ne 0) { Write-Warning "Failed to clone $folder" }
}

function Install-NodeRequirements {
    param([string]$NodeDir)
    $req = Join-Path $NodeDir 'requirements.txt'
    if (-not (Test-Path $req)) { return }

    $name = Split-Path $NodeDir -Leaf

    # Resolve venv python.exe - must exist before we can install
    $venvPy = $null
    if ($VenvDir) { $venvPy = Join-Path $VenvDir 'Scripts\python.exe' }

    if (-not $venvPy -or -not (Test-Path $venvPy)) {
        Write-Host "[custom_nodes] Venv not ready; skipping requirements for $name"
        return
    }

    Write-Host ""
    Write-Host "[custom_nodes] Installing requirements for $name..."
    & $UvExe pip install --python $venvPy -r $req
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to install requirements for $name"
        if ($Strict) { $script:failed = $true }
    }
}

# Clone / update all nodes
Get-Content $ListFile | ForEach-Object { Install-CustomNode $_ }

# Install Python requirements into venv
Write-Host ""
Write-Host "Installing custom node Python requirements..."
Get-ChildItem -Path $DestDir -Directory | ForEach-Object {
    Install-NodeRequirements $_.FullName
}

if ($failed) { exit 1 }
exit 0