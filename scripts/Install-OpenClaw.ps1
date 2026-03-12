<#
.SYNOPSIS
    Installs OpenClaw and copies the installer repo skills/ folder into
    ~/.openclaw/workspace/skills.

.PARAMETER SkillsSource
    Path to the skills/ folder in the installer repo.
    Defaults to the sibling skills/ directory next to this script.

.PARAMETER Wait
    If set, waits for a keypress before closing (useful when launched
    in a new terminal window).
#>
param(
    [string]$SkillsSource = (Join-Path $PSScriptRoot '..\skills'),
    [switch]$Wait
)

$ErrorActionPreference = 'Continue'

# -- Install OpenClaw ----------------------------------------------------------
Write-Host ""
$openClawCmd = Get-Command openclaw -ErrorAction SilentlyContinue
if ($openClawCmd) {
    Write-Host "OpenClaw already installed: $($openClawCmd.Source) -- skipping install."
} else {
    Write-Host "Installing OpenClaw..."
    try {
        iwr -useb https://openclaw.ai/install.ps1 | iex
    } catch {
        Write-Warning "OpenClaw installer failed: $_"
    }
}

# -- Copy skills ---------------------------------------------------------------
$skillsDest = Join-Path $env:USERPROFILE '.openclaw\workspace\skills'
$_resolved  = Resolve-Path $SkillsSource -ErrorAction SilentlyContinue
$skillsSrc  = if ($_resolved) { $_resolved.Path } else { $null }

Write-Host ""
if (-not $skillsSrc -or -not (Test-Path $skillsSrc)) {
    Write-Warning "Skills source not found: $SkillsSource -- skipping skills copy."
} else {
    Write-Host "Copying skills: $skillsSrc -> $skillsDest"
    if (-not (Test-Path $skillsDest)) {
        New-Item -ItemType Directory -Path $skillsDest -Force | Out-Null
    }
    # /E=subdirs, /IS /IT=overwrite changed files, /NFL /NDL=quiet output
    robocopy $skillsSrc $skillsDest /E /IS /IT /NFL /NDL | Out-Null
    Write-Host "Skills copied."
}

if ($Wait) {
    Write-Host ""
    Write-Host "OpenClaw setup complete. Press Enter to close..."
    Read-Host | Out-Null
}