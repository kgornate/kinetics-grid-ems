param(
  [string]$ProjectPath = "."
)

$ErrorActionPreference = "Stop"
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectPath = Resolve-Path $ProjectPath

Write-Host "Applying Phase F3.1 Historian export final patch to: $ProjectPath"

$backup = Join-Path $ProjectPath ("backup_before_phase_f3_1_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $backup | Out-Null

$files = @(
  "pubspec.yaml",
  "lib\core\api\northbound_api_client.dart",
  "lib\core\download\download_result.dart",
  "lib\core\download\file_download.dart",
  "lib\core\download\file_download_io.dart",
  "lib\core\download\file_download_stub.dart",
  "lib\core\download\file_download_web.dart",
  "lib\core\export\fast_bess_history_exporter.dart",
  "lib\features\dashboard\screens\dashboard_shell_screen.dart",
  "lib\features\dashboard\screens\fast_bess_historian_screen.dart",
  "lib\features\dashboard\widgets\dashboard_nav_actions.dart",
  "PHASE_F3_1_EXPORT_FINAL_NOTES.md"
)

foreach ($rel in $files) {
  $src = Join-Path $PatchRoot $rel
  $dst = Join-Path $ProjectPath $rel
  if (!(Test-Path $src)) { throw "Patch file missing: $src" }
  if (Test-Path $dst) {
    $backupDst = Join-Path $backup $rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backupDst) | Out-Null
    Copy-Item -Force $dst $backupDst
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
  Copy-Item -Force $src $dst
}

$hist = Join-Path $ProjectPath "lib\features\dashboard\screens\fast_bess_historian_screen.dart"
$content = Get-Content $hist -Raw

if ($content -notmatch "Download CSV") { throw "Verification failed: Download CSV not found in historian screen." }
if ($content -notmatch "Download Excel") { throw "Verification failed: Download Excel not found in historian screen." }
if ($content -match "Download/export will be added in Phase F3") { throw "Verification failed: old Phase F2 text still present." }
if ($content -match "ExpansionTile") { throw "Verification failed: old ExpansionTile selector still present." }
if ($content -match "FilterChip") { throw "Verification failed: old FilterChip selector still present." }

Write-Host "Patch applied and verified. Backup saved at: $backup"
Write-Host "Next commands:"
Write-Host "  flutter clean"
Write-Host "  flutter pub get"
Write-Host "  flutter analyze"
Write-Host "  flutter run -d chrome"
Write-Host "  flutter run -d windows"
