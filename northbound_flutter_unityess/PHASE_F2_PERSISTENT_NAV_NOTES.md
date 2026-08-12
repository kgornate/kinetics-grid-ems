# Phase F2.1 Persistent Navigation Patch

## Purpose

This small patch is meant to be applied after Phase F2 Historian UI. It fixes the navigation behavior where switching from one menu to another disposes the old screen and reloads it from zero when the user returns.

## What changed

Only this file is changed:

```text
lib/features/dashboard/screens/dashboard_shell_screen.dart
```

The dashboard shell now uses a lazy cached `IndexedStack`:

- The current page is created when opened for the first time.
- Once a page has been opened, it is kept alive in memory.
- Returning to PCS, BMS, Historian, or any other page does not rebuild the screen from zero.
- Unvisited pages are not created at startup, so the first dashboard load is still lighter than the original eager IndexedStack behavior.

## Tradeoff

Pages that are kept alive may continue their own internal timers if the screen implementation has a `Timer.periodic`. This is intentionally accepted in this patch because the immediate requirement is to avoid full reload on menu switching. A later Phase F2.2/F4 can add active-page-aware polling so hidden pages stay alive but pause API refresh.

## Apply

From the Flutter project folder:

```powershell
tar -xzf ..\northbound_flutter_phase_f2_persistent_nav_patch_20260810.tar.gz -C ..
Copy-Item -Recurse -Force ..\flutter_phase_f2_persistent_nav_patch\lib\* .\lib\
Copy-Item -Force ..\flutter_phase_f2_persistent_nav_patch\PHASE_F2_PERSISTENT_NAV_NOTES.md .\
flutter clean
flutter pub get
flutter analyze
flutter run -d chrome
```

Then validate:

1. Open PCS page once.
2. Switch to BMS.
3. Switch back to PCS.
4. PCS should show immediately without full initial reload.
5. Open Historian once.
6. Switch away and return.
7. Historian filters/table state should remain.
