<#
.SYNOPSIS
    Sets PowerShell execution policy to RemoteSigned for the current user
    (only if not already sufficiently permissive), then launches the OpenClaw
    installer in a new terminal window.

.NOTES
    Safe to run multiple times; the policy check is idempotent.
#>
param()

$ErrorActionPreference = 'Continue'

# ── Execution policy ──────────────────────────────────────────────────────────
$permissive = @('RemoteSigned','Unrestricted','Bypass')
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

# ── OpenClaw installer ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Launching OpenClaw installer in a new window..."
Start-Process powershell -ArgumentList @(
    '-NoProfile',
    '-ExecutionPolicy', 'RemoteSigned',
    '-Command', "iwr -useb https://openclaw.ai/install.ps1 | iex; Write-Host ''; Write-Host 'OpenClaw install complete. Press Enter to close...'; Read-Host"
) -WindowStyle Normal

exit 0
