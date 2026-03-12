<#
.SYNOPSIS
    Locates (and optionally installs via winget) git, uv, and qBittorrent.
    Writes results to a .env-style file so the BAT caller can read them back.

.PARAMETER OutFile
    Path to the output file where discovered tool paths are written.
    Each line: KEY=VALUE (no quotes). The BAT reads these with a FOR /F loop.

.PARAMETER InstallMissing
    If set, attempts to install missing tools via winget.

.PARAMETER Tools
    Comma-separated list of tools to find: git, uv, qbittorrent (default: all).
#>
param(
    [string]$OutFile = "$env:TEMP\comfy_tools.env",
    [switch]$InstallMissing,
    [string]$Tools = "git,uv,qbittorrent"
)

$ErrorActionPreference = 'Continue'
$wanted = $Tools -split ',' | ForEach-Object { $_.Trim().ToLower() }
$results = @{}

function Find-Exe {
    param([string[]]$Names, [string[]]$KnownPaths)
    foreach ($n in $Names) {
        $found = Get-Command $n -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
        if ($found) { return $found }
    }
    foreach ($p in $KnownPaths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Install-Winget {
    param([string]$Id, [string]$Label)
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Warning "winget not available; cannot install $Label automatically."
        return $false
    }
    Write-Host "Installing $Label via winget ($Id)..."
    winget install --id $Id -e --source winget --accept-source-agreements --accept-package-agreements
    return $LASTEXITCODE -eq 0
}

# ── git ──────────────────────────────────────────────────────────────────────
if ($wanted -contains 'git') {
    $knownGit = @(
        "$env:LocalAppData\Microsoft\WinGet\Links\git.exe",
        "$env:LocalAppData\Programs\Git\cmd\git.exe",
        "$env:LocalAppData\Programs\Git\bin\git.exe",
        "$env:ProgramFiles\Git\cmd\git.exe",
        "$env:ProgramFiles\Git\bin\git.exe",
        "${env:ProgramFiles(x86)}\Git\cmd\git.exe",
        "${env:ProgramFiles(x86)}\Git\bin\git.exe"
    )
    # Registry-based detection
    foreach ($hive in 'HKLM:\SOFTWARE\GitForWindows','HKCU:\SOFTWARE\GitForWindows') {
        try {
            $ip = (Get-ItemProperty $hive -ErrorAction Stop).InstallPath
            if ($ip) {
                $knownGit += "$ip\cmd\git.exe"
                $knownGit += "$ip\bin\git.exe"
            }
        } catch {}
    }

    $git = Find-Exe -Names 'git','git.exe' -KnownPaths $knownGit
    if (-not $git -and $InstallMissing) {
        Install-Winget 'Git.Git' 'Git for Windows' | Out-Null
        $git = Find-Exe -Names 'git','git.exe' -KnownPaths $knownGit
    }
    if ($git) {
        Write-Host "git found: $git"
        $results['GIT_EXE'] = $git
    } else {
        Write-Warning "git not found."
        $results['GIT_EXE'] = ''
    }
}

# ── uv ───────────────────────────────────────────────────────────────────────
if ($wanted -contains 'uv') {
    $knownUv = @(
        "$env:LocalAppData\Microsoft\WinGet\Links\uv.exe",
        "$env:LocalAppData\Programs\uv\uv.exe",
        "$env:ProgramFiles\uv\uv.exe"
    )
    $uv = Find-Exe -Names 'uv','uv.exe' -KnownPaths $knownUv
    if (-not $uv -and $InstallMissing) {
        Install-Winget 'astral-sh.uv' 'uv' | Out-Null
        $uv = Find-Exe -Names 'uv','uv.exe' -KnownPaths $knownUv
    }
    if ($uv) {
        Write-Host "uv found: $uv"
        $results['UV_EXE'] = $uv
    } else {
        Write-Warning "uv not found."
        $results['UV_EXE'] = ''
    }
}

# ── qBittorrent ───────────────────────────────────────────────────────────────
if ($wanted -contains 'qbittorrent') {
    $knownQbt = @(
        "$env:ProgramFiles\qBittorrent\qbittorrent.exe",
        "${env:ProgramFiles(x86)}\qBittorrent\qbittorrent.exe",
        "$env:LocalAppData\Programs\qBittorrent\qbittorrent.exe"
    )
    $qbt = Find-Exe -Names 'qbittorrent','qbittorrent.exe' -KnownPaths $knownQbt
    if (-not $qbt -and $InstallMissing) {
        Install-Winget 'qBittorrent.qBittorrent' 'qBittorrent' | Out-Null
        $qbt = Find-Exe -Names 'qbittorrent','qbittorrent.exe' -KnownPaths $knownQbt
    }
    if ($qbt) {
        Write-Host "qBittorrent found: $qbt"
        $results['QBT_EXE'] = $qbt
    } else {
        Write-Warning "qBittorrent not found."
        $results['QBT_EXE'] = ''
    }
}

# ── ComfyUI Desktop ───────────────────────────────────────────────────────────
if ($wanted -contains 'comfydesktop') {
    $knownDesktop = @(
        "$env:LocalAppData\Programs\ComfyUI\ComfyUI.exe",
        "$env:LocalAppData\Programs\ComfyUI Desktop\ComfyUI.exe",
        "$env:ProgramFiles\ComfyUI\ComfyUI.exe",
        "$env:ProgramFiles\ComfyUI Desktop\ComfyUI.exe",
        "${env:ProgramFiles(x86)}\ComfyUI\ComfyUI.exe",
        "${env:ProgramFiles(x86)}\ComfyUI Desktop\ComfyUI.exe"
    )
    $desktop = Find-Exe -Names @() -KnownPaths $knownDesktop
    $results['COMFY_DESKTOP_EXE'] = if ($desktop) { $desktop } else { '' }
    if ($desktop) { Write-Host "ComfyUI Desktop found: $desktop" }
}

# ── Write output file ─────────────────────────────────────────────────────────
$lines = $results.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
$lines | Set-Content -Path $OutFile -Encoding UTF8
Write-Host "Tool paths written to: $OutFile"

# Exit non-zero if any mandatory tool is missing
$missing = $results.GetEnumerator() | Where-Object { $_.Value -eq '' }
if ($missing) { exit 1 }
exit 0
