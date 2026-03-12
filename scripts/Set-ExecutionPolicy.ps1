<#
.SYNOPSIS
    Sets PowerShell execution policy to RemoteSigned for the current user
    (only if not already sufficiently permissive), then launches
    Install-OpenClaw.ps1 in a new terminal window.

.PARAMETER SkillsSource
    Forwarded to Install-OpenClaw.ps1 — path to the skills/ folder to copy.

.NOTES
    Safe to run multiple times; the policy check is idempotent.
#>
param(
    [string]$SkillsSource = (Join-Path $PSScriptRoot '..\skills')
)

$ErrorActionPreference = 'Continue'

# ── Execution policy ──────────────────────────────────────────────────────────
$permissive = @('RemoteSigned', 'Unrestricted', 'Bypass')
$current = Get-ExecutionPolicy -Scope CurrentUser

if ($permissive -contains $current) {
    Write-Host "PowerShell execution policy already sufficient: $current"
} else {
    Write-Host "Setting execution policy to RemoteSigned for current user (was: $current)..."
    try {
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
        Write-Host "Execution policy set to RemoteSigned."
    } catch {
        Write-Warning "Failed to set execution policy: $_"
    }
}

# ── Launch OpenClaw install + skills copy in a new window ────────────────────
$openClawScript = Join-Path $PSScriptRoot 'Install-OpenClaw.ps1'
Write-Host ""
Write-Host "Launching OpenClaw installer in a new window..."
Start-Process powershell -ArgumentList @(
    '-NoProfile',
    '-ExecutionPolicy', 'RemoteSigned',
    '-File', $openClawScript,
    '-SkillsSource', $SkillsSource,
    '-Wait'
) -WindowStyle Normal

exit 0
