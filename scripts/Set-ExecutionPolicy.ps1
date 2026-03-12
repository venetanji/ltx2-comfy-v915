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
# NOTE: All powershell invocations in install_comfy.bat use -ExecutionPolicy Bypass,
# so this step is best-effort only. GPO at MachinePolicy/UserPolicy scope will
# override CurrentUser/LocalMachine settings -- that is fine, we just skip.
$permissive = @('RemoteSigned', 'Unrestricted', 'Bypass')
$effective  = Get-ExecutionPolicy   # effective (all scopes merged)
$current    = Get-ExecutionPolicy -Scope CurrentUser

if ($permissive -contains $effective) {
    Write-Host "PowerShell execution policy already sufficient: $effective"
} else {
    Write-Host "Attempting to set execution policy to RemoteSigned (current user)..."
    $set = $false
    foreach ($scope in @('CurrentUser', 'LocalMachine')) {
        try {
            Set-ExecutionPolicy -Scope $scope -ExecutionPolicy RemoteSigned -Force -ErrorAction Stop
            Write-Host "Execution policy set to RemoteSigned at scope: $scope"
            $set = $true
            break
        } catch {
            Write-Host "Could not set at scope $scope (may be GPO-locked): $($_.Exception.Message.Split([char]10)[0])"
        }
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
Start-Process powershell -ArgumentList @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $openClawScript,
    '-SkillsSource', $SkillsSource,
    '-Wait'
) -WindowStyle Normal

exit 0
