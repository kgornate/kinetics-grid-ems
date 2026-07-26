$ErrorActionPreference = "Stop"

Write-Host "Preparing Kinetics Gateway Flutter Dashboard..."
flutter clean
flutter pub get
flutter test
flutter run -d windows
