#!/bin/sh
set -eu
TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "Usage: sh install_phase_f2_patch.sh /path/to/northbound_flutter_unityess"
  exit 1
fi
if [ ! -d "$TARGET/lib" ]; then
  echo "Target does not look like a Flutter project: $TARGET"
  exit 1
fi
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="$TARGET/../northbound_flutter_before_phase_f2_$STAMP"
echo "Creating backup: $BACKUP"
mkdir -p "$BACKUP"
cp -a "$TARGET/lib" "$BACKUP/"
for f in \
  lib/core/api/northbound_api_client.dart \
  lib/features/dashboard/widgets/dashboard_nav_actions.dart \
  lib/features/dashboard/screens/dashboard_shell_screen.dart \
  lib/features/dashboard/screens/fast_bess_historian_screen.dart \
  lib/features/dashboard/screens/home_dashboard_screen.dart \
  lib/features/dashboard/screens/topology_screen.dart \
  lib/features/dashboard/screens/bms_screen.dart \
  lib/features/dashboard/screens/pcs_screen.dart \
  lib/features/dashboard/screens/dehumidifier_screen.dart \
  lib/features/dashboard/screens/liquid_cooling_screen.dart \
  lib/features/dashboard/screens/fire_screen.dart \
  lib/features/dashboard/screens/utility_meter_screen.dart \
  lib/features/dashboard/screens/ems_system_screen.dart \
  lib/features/dashboard/screens/strategy_command_screen.dart
  do
    mkdir -p "$TARGET/$(dirname "$f")"
    cp "$f" "$TARGET/$f"
  done
cp PHASE_F2_HISTORIAN_NOTES.md "$TARGET/PHASE_F2_HISTORIAN_NOTES.md"
echo "Phase F2 patch installed. Backup: $BACKUP"
echo "Now run: flutter analyze"
