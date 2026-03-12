<#
.SYNOPSIS
    Configures qBittorrent (NoSubfolder layout) and opens .torrent files
    from the installer repo directory with the ComfyUI data folder as save path.

.PARAMETER TorrentDir
    Directory to scan for *.torrent files (should be the installer repo dir).

.PARAMETER SavePath
    Where qBittorrent should save downloaded content (e.g. %COMFY_DATA%).

.PARAMETER QbtExe
    Full path to qbittorrent.exe.

.PARAMETER ExcludePattern
    Torrent file names to skip (default: nvidia-driver.torrent).
#>
param(
    [Parameter(Mandatory)][string]$TorrentDir,
    [Parameter(Mandatory)][string]$SavePath,
    [Parameter(Mandatory)][string]$QbtExe,
    [string]$ExcludePattern = 'nvidia-driver.torrent'
)

$ErrorActionPreference = 'Continue'

# -- Find torrents --
$torrents = Get-ChildItem -Path $TorrentDir -Filter '*.torrent' -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notlike $ExcludePattern }

if (-not $torrents) {
    Write-Host "No .torrent files found in: $TorrentDir"
    Write-Host "Skipping torrent step."
    exit 0
}

if (-not (Test-Path $QbtExe)) {
    Write-Warning "qBittorrent not found at: $QbtExe"
    exit 1
}

# -- qBittorrent ini path --
$qbtIni  = Join-Path $env:AppData 'qBittorrent\qBittorrent.ini'
$qbtDir  = Split-Path $qbtIni
if (-not (Test-Path $qbtDir)) { New-Item -ItemType Directory $qbtDir -Force | Out-Null }

function Test-ConfigPatched {
    if (-not (Test-Path $qbtIni)) { return $false }
    $content = Get-Content $qbtIni -Raw -ErrorAction SilentlyContinue
    return $content -match 'Session\\TorrentContentLayout\s*=\s*NoSubfolder'
}

function Write-ConfigPatch {
    Add-Content -Path $qbtIni -Value ""
    Add-Content -Path $qbtIni -Value "[BitTorrent]"
    Add-Content -Path $qbtIni -Value "Session\TorrentContentLayout=NoSubfolder"
    Write-Host "qBittorrent configured: NoSubfolder."
}

# -- Wait for qBittorrent to exit if running with stale config --
$isRunning  = (Get-Process qbittorrent -ErrorAction SilentlyContinue) -ne $null
$isPatched  = Test-ConfigPatched

if ($isRunning -and $isPatched) {
    Write-Host "qBittorrent is running and already configured (NoSubfolder)."
    Write-Host "Assuming existing downloads are correct; skipping torrent import."
    exit 0
}

if ($isRunning -and -not $isPatched) {
    Write-Host "qBittorrent is running but config is not patched."
    Write-Host "Please CLOSE qBittorrent completely, then press Enter to continue..."
    Read-Host | Out-Null
    while (Get-Process qbittorrent -ErrorAction SilentlyContinue) {
        Write-Host "Still running - press Enter again when closed..."
        Read-Host | Out-Null
    }
    $isRunning = $false
}

# -- Patch config --
if (-not (Test-ConfigPatched)) {
    if (-not (Test-Path $qbtIni)) {
        Set-Content -Path $qbtIni -Value ""
    }
    Write-ConfigPatch
} else {
    Write-Host "qBittorrent already configured (NoSubfolder); skipping patch."
}

# -- Launch qBittorrent and open torrents --
Write-Host "Starting qBittorrent..."
Start-Process $QbtExe
Start-Sleep 2

Write-Host "Opening models folder: $SavePath"
Start-Process explorer $SavePath

foreach ($t in $torrents) {
    Write-Host "Opening torrent: $($t.Name) -> $SavePath"
    Start-Process $QbtExe -ArgumentList "--skip-dialog=true --save-path=`"$SavePath`" `"$($t.FullName)`""
}

Write-Host ""
Write-Host "NOTE: Torrents should contain a 'models' folder."
Write-Host "      Saving into $SavePath merges into $SavePath\models."
exit 0