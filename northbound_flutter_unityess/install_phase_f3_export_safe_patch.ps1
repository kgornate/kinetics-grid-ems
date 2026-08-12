param(
  [string]$ProjectPath = "."
)

$ErrorActionPreference = "Stop"
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Copy-Item -Recurse -Force "$PatchRoot\lib\*" "$ProjectPath\lib\"
Copy-Item -Force "$PatchRoot\pubspec.yaml" "$ProjectPath\pubspec.yaml"
Copy-Item -Force "$PatchRoot\PHASE_F3_EXPORT_SAFE_NOTES.md" "$ProjectPath\PHASE_F3_EXPORT_SAFE_NOTES.md"

Write-Host "Phase F3 export safe patch applied to $ProjectPath"
Write-Host "Next: flutter clean; flutter pub get; flutter analyze; flutter run -d chrome"
