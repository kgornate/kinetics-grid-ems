$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
flutter create --platforms=windows --project-name kalpa_gateway_setup .
if ($LASTEXITCODE -ne 0) { throw 'Flutter project generation failed' }
# This source starter provides its own app; remove the generated counter-demo test.
if (Test-Path test/widget_test.dart) { Remove-Item test/widget_test.dart }
flutter pub get
if ($LASTEXITCODE -ne 0) { throw 'Dependency resolution failed' }
flutter analyze
if ($LASTEXITCODE -ne 0) { throw 'Flutter analysis failed' }
flutter run -d windows
