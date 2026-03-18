<#
.SYNOPSIS
    Sets PowerShell execution policy to RemoteSigned for the current user
    when needed, then launches Install-OpenClaw.ps1 in a new terminal window.

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
# NOTE: install_comfy.bat invokes this helper with -ExecutionPolicy Bypass so the
# helper itself can always run. That process-scoped setting does not persist, so
# we must check/write the CurrentUser scope explicitly.
$permissive = @('RemoteSigned', 'Unrestricted', 'Bypass')
$desired    = 'RemoteSigned'
$current    = Get-ExecutionPolicy -Scope CurrentUser
$useBypass  = $false

if ($permissive -contains $current) {
    Write-Host "PowerShell execution policy already sufficient for CurrentUser: $current"
} else {
    Write-Host "Attempting to set execution policy to RemoteSigned (CurrentUser)..."
    $set = $false
    try {
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy $desired -Force -ErrorAction Stop
        Write-Host "Execution policy set to RemoteSigned at scope: CurrentUser"
        $set = $true
    } catch {
        Write-Host "Could not set CurrentUser policy (may be GPO-locked): $($_.Exception.Message.Split([char]10)[0])"
        $useBypass = $true
    }
    if (-not $set) {
        Write-Host "NOTE: Execution policy is controlled by Group Policy. This is OK --"
        Write-Host "      install_comfy.bat invokes all scripts with -ExecutionPolicy Bypass."
    }
}

# ── Launch OpenClaw install + skills copy in a new window ────────────────────
$openClawScript = Join-Path $PSScriptRoot 'Install-OpenClaw.ps1'
Write-Host ""
Write-Host "Launching OpenClaw installer in a new window..."
$argumentList = @('-NoProfile')
if ($useBypass) {
    $argumentList += @('-ExecutionPolicy', 'Bypass')
}
$argumentList += @(
    '-File', $openClawScript,
    '-SkillsSource', $SkillsSource,
    '-Wait'
)
Start-Process powershell -ArgumentList $argumentList -WindowStyle Normal

exit 0
