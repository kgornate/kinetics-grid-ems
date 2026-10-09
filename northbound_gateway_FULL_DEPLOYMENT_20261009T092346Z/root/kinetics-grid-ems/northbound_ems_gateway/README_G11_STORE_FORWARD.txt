G11 Central Sync Store-and-Forward Recovery

Purpose:
- pause/resume backend transport without stopping S1-S8 producers
- keep live SQLite/overflow persistence active during backend outage or maintenance
- automatically replay only central_sync_overflow_*.db after recovery
- preserve one-request-at-a-time backend transport with shared lock
- keep legacy historical backlog replay OFF
- retain drained overflow archive DBs with replay markers

IMPORTANT:
After G11, use tools/central_sync_transport_control.sh pause/resume instead of
systemctl stop central-sync.service when only backend upload must be stopped.

Installer does NOT restart central-sync.service.
