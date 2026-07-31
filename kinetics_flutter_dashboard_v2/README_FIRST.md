# Kinetics Flutter Dashboard V3.0.0

This source is paired with Kinetics EMS Gateway V3.0.0.

Recommended Windows build:

```powershell
flutter clean
flutter pub get
flutter analyze
flutter test
flutter build windows --release
```

The Control screen uses cache-only multi-pair polling. `Refresh` performs one explicit live read for the selected pair. Automatic Start uses a controlled ramp; Set power directly sends the requested target after gateway safety prechecks.
