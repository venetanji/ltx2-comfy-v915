<#
.SYNOPSIS
    Creates or patches ComfyUI Manager's config.ini with the desired settings.
    Safe to run multiple times (idempotent key/value update).
    Will create the file (and parent directory) if it does not exist yet.

.PARAMETER ComfySrc
    Path to the ComfyUI source checkout (e.g. Documents\comfyui-git).

.PARAMETER ComfyData
    Path to the shared ComfyUI data folder (e.g. Documents\ComfyUI).

.NOTES
    Manager stores config at: <ComfyData>\user\__manager\config.ini
    Fallback legacy paths are also patched if present.
#>
param(
    [Parameter(Mandatory)][string]$ComfySrc,
    [Parameter(Mandatory)][string]$ComfyData
)

$ErrorActionPreference = 'Continue'

# Settings to enforce (key -> value)
$desired = [ordered]@{
    'git_exe'            = ''
    'use_uv'             = 'True'
    'security_level'     = 'normal'
    'network_mode'       = 'personal_cloud'
    'db_mode'            = 'cache'
    'file_logging'       = 'True'
    'always_lazy_install'= 'False'
}

# Primary path (current Manager stores config here)
$primaryDir = Join-Path $ComfyData 'user\__manager'
$primaryIni = Join-Path $primaryDir 'config.ini'

# Legacy / alternative locations to patch if they already exist
$legacyCandidates = @(
    (Join-Path $ComfySrc  'custom_nodes\ComfyUI-Manager\config.ini'),
    (Join-Path $ComfyData 'custom_nodes\ComfyUI-Manager\config.ini'),
    (Join-Path $ComfyData 'user\default\ComfyUI-Manager\config.ini')
)

function Update-IniFile {
    param([string]$Path, [bool]$CreateIfMissing = $false)

    if (-not (Test-Path $Path)) {
        if (-not $CreateIfMissing) { return $false }
        $dir = Split-Path $Path
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        Write-Host "Creating: $Path"
        # Start with a minimal [default] section
        $lines = @('[default]')
    } else {
        Write-Host "Patching: $Path"
        $lines = Get-Content $Path
    }

    # Ensure [default] section exists
    if (-not ($lines -match '^\[default\]')) {
        $lines = @('[default]') + $lines
    }

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
    Write-Host "  -> Done (security_level=normal, network_mode=personal_cloud, use_uv=True)"
    return $true
}

# Always ensure primary config exists and is patched
Update-IniFile -Path $primaryIni -CreateIfMissing $true | Out-Null

# Patch legacy locations if they exist
foreach ($ini in $legacyCandidates) {
    if (Test-Path $ini) {
        Update-IniFile -Path $ini -CreateIfMissing $false | Out-Null
    }
}

exit 0
