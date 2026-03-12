<#
.SYNOPSIS
    Checks the installed NVIDIA driver version and installs 591.86 if outdated.
    Supports three download methods: skip, web (Invoke-WebRequest), torrent.

.PARAMETER TargetVersion
    Driver version to target (default: 591.86).

.PARAMETER DriverUrl
    Direct download URL for the driver installer.

.PARAMETER ScriptDir
    Directory to look for a local .exe or nvidia-driver.torrent file.

.PARAMETER QbtExe
    Path to qbittorrent.exe (required for torrent download option).

.PARAMETER NonInteractive
    Skip all prompts; default to web download.
#>
param(
    [string]$TargetVersion  = '591.86',
    [string]$DriverUrl      = 'https://us.download.nvidia.com/Windows/591.86/591.86-desktop-win10-win11-64bit-international-dch-whql.exe',
    [string]$ScriptDir      = $PSScriptRoot,
    [string]$QbtExe         = '',
    [switch]$NonInteractive
)

$ErrorActionPreference = 'Continue'

# ── Detect installed driver version ──────────────────────────────────────────
$vc = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match 'NVIDIA' } |
      Select-Object -First 1

if (-not $vc) {
    Write-Host "No NVIDIA GPU detected; skipping driver install."
    exit 0
}

$installedVersion = $null
$dv = [string]$vc.DriverVersion
$last4 = ($dv -replace '[^0-9]', '')
if ($last4.Length -ge 4) {
    $last4 = $last4.Substring($last4.Length - 4)
    if ($last4 -match '^\d{4}$') {
        $major = 500 + [int]$last4.Substring(0, 2)
        $minor = [int]$last4.Substring(2, 2)
        $installedVersion = '{0}.{1:00}' -f $major, $minor
    }
}

if ($installedVersion) {
    Write-Host "Detected NVIDIA driver: $installedVersion"
    $iv = [version]$installedVersion
    $tv = [version]$TargetVersion
    if ($iv -ge $tv) {
        Write-Host "NVIDIA driver already up to date ($installedVersion >= $TargetVersion); skipping."
        exit 0
    }
} else {
    Write-Warning "Could not parse installed driver version; proceeding with install."
}

# ── Locate installer ──────────────────────────────────────────────────────────
$localExePattern = Join-Path $ScriptDir '*.exe'
$localExe = Get-Item $localExePattern -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '591' } |
            Select-Object -First 1 -ExpandProperty FullName

$torrentFile = Join-Path $ScriptDir 'nvidia-driver.torrent'
$hasTorrent  = Test-Path $torrentFile

$driverExe = if ($localExe) { $localExe } else { "$env:TEMP\nvidia-driver-$TargetVersion.exe" }

if (Test-Path $driverExe) {
    Write-Host "Using existing driver installer: $driverExe"
} else {
    Write-Host ""
    Write-Host "NVIDIA driver installer not found locally."
    Write-Host "Choose download method:"
    Write-Host "  1) Skip"
    Write-Host "  2) Download via web (Invoke-WebRequest)"
    if ($hasTorrent) {
        Write-Host "  3) Download via torrent: $torrentFile"
    } else {
        Write-Host "  3) Download via torrent: (no nvidia-driver.torrent found)"
    }

    $choice = '2'
    if (-not $NonInteractive) {
        Write-Host "(Auto-selecting default in 5 seconds...)"
        # Simple timed read
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $choice = $null
        while ($sw.Elapsed.TotalSeconds -lt 5 -and -not $choice) {
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.KeyChar -in '1','2','3') { $choice = $key.KeyChar }
            }
            Start-Sleep -Milliseconds 200
        }
        if (-not $choice) { $choice = '2' }
    }

    switch ($choice) {
        '1' {
            Write-Host "Skipping NVIDIA driver install."
            exit 0
        }
        '3' {
            if (-not $hasTorrent) {
                Write-Warning "No nvidia-driver.torrent found in $ScriptDir. Place the file there and retry."
                exit 1
            }
            if (-not $QbtExe -or -not (Test-Path $QbtExe)) {
                Write-Warning "qBittorrent not available; cannot use torrent download."
                exit 1
            }
            $dlDir = "$env:TEMP\nvidia-driver-$TargetVersion"
            if (-not (Test-Path $dlDir)) { New-Item -ItemType Directory $dlDir | Out-Null }
            Start-Process $QbtExe
            Start-Sleep 2
            Start-Process $QbtExe -ArgumentList "--skip-dialog=true --save-path=`"$dlDir`" `"$torrentFile`""
            Write-Host "Waiting for download to finish. Press Enter when done..."
            Read-Host | Out-Null
            $found = Get-ChildItem $dlDir -Recurse -Filter '*.exe' | Select-Object -First 1
            if (-not $found) {
                Write-Warning "No .exe found in $dlDir after torrent download."
                exit 1
            }
            $driverExe = $found.FullName
        }
        default {
            # Option 2: web download
            Write-Host "Downloading: $DriverUrl"
            Write-Host "Please wait, this can take several minutes..."
            $ProgressPreference = 'SilentlyContinue'
            try {
                Invoke-WebRequest -Uri $DriverUrl -OutFile $driverExe -UseBasicParsing
            } catch {
                Write-Warning "Download failed: $_"
                exit 1
            }
            if (-not (Test-Path $driverExe)) {
                Write-Warning "Driver file not found after download."
                exit 1
            }
        }
    }
}

# ── Run installer ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Launching NVIDIA driver installer..."
Write-Host "IMPORTANT: DO NOT REBOOT — lab machines reset on reboot."
Write-Host "If the installer asks to reboot, close it without rebooting."

$proc = Start-Process $driverExe -ArgumentList '-s' -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    Write-Warning "Quiet install returned $($proc.ExitCode). Launching interactive installer..."
    Start-Process $driverExe -Wait
}
exit 0
