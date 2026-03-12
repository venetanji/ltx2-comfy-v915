<#
.SYNOPSIS
    Patches ComfyUI Manager's config.ini to enable automatic dependency
    installation (security_level=weak, auto_install_reqs=True).

    Safe to run multiple times (idempotent key/value update).

.PARAMETER ComfySrc
    Path to the ComfyUI source checkout (e.g. Documents\comfyui-git).

.PARAMETER ComfyData
    Path to the shared ComfyUI data folder (e.g. Documents\ComfyUI).

.NOTES
    The Manager generates config.ini on first run. This script should be
    called after ComfyUI has been launched at least once.
#>
param(
    [Parameter(Mandatory)][string]$ComfySrc,
    [Parameter(Mandatory)][string]$ComfyData
)

$ErrorActionPreference = 'Continue'

# Settings to enforce (key -> value)
$desired = [ordered]@{
    'security_level'    = 'weak'
    'auto_install_reqs' = 'True'
}

# Candidate config locations (Manager uses different paths depending on version / install type)
$candidates = @(
    (Join-Path $ComfySrc  'custom_nodes\ComfyUI-Manager\config.ini'),
    (Join-Path $ComfyData 'custom_nodes\ComfyUI-Manager\config.ini'),
    (Join-Path $ComfyData 'user\default\ComfyUI-Manager\config.ini')
)

function Update-IniFile {
    param([string]$Path)

    Write-Host "Patching: $Path"
    $lines = if (Test-Path $Path) { Get-Content $Path } else { @() }

    foreach ($key in $desired.Keys) {
        $val   = $desired[$key]
        $found = $false
        $lines = $lines | ForEach-Object {
            if ($_ -match ('^\s*' + [regex]::Escape($key) + '\s*=')) {
                $found = $true
                "$key = $val"
            } else { $_ }
        }
        if (-not $found) {
            $lines += "$key = $val"
        }
    }

    Set-Content -Path $Path -Value $lines -Encoding UTF8
    Write-Host "  -> security_level = weak, auto_install_reqs = True"
}

$patched = 0
foreach ($ini in $candidates) {
    if (Test-Path $ini) {
        Update-IniFile $ini
        $patched++
    }
}

if ($patched -eq 0) {
    Write-Warning "No ComfyUI Manager config.ini found. Run ComfyUI once to generate it, then re-run this script."
    exit 1
}

exit 0
