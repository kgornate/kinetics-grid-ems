$ErrorActionPreference = "Stop"

Write-Host "Building Kinetics Gateway Windows release..."
flutter clean
flutter pub get
flutter test
flutter build windows --release
Write-Host "Release bundle: build\windows\x64\runner\Release"
