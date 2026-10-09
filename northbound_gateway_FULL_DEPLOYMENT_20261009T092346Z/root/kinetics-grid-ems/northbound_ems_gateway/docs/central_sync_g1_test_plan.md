# G1 Central Sync Core - Gateway Test Plan

This plan validates G1 without the IT backend and without changing any Modbus polling/control service.

## Test A - local loopback transport

Terminal 1 on i.MX93:

```bash
cd /root/kinetics-grid-ems/northbound_ems_gateway
PYTHONPATH=src python3 tools/central_sync_mock_server.py \
  --host 127.0.0.1 --port 8081 --state-db /tmp/central_sync_mock.db
```

Terminal 2:

```bash
cd /root/kinetics-grid-ems/northbound_ems_gateway
rm -f /mnt/ems-logs/northbound_ems_gateway/central_sync_g1_test.db*
rm -f /var/lib/nb-ems-central-sync/status_g1_test.json

PYTHONPATH=src python3 tools/central_sync_enqueue_test.py \
  --config configs/central_sync_g1_local_test.json --count 5

sleep 1

PYTHONPATH=src python3 -m nb_ems_gateway.central_sync.service \
  --config configs/central_sync_g1_local_test.json --once

cat /var/lib/nb-ems-central-sync/status_g1_test.json
curl -s http://127.0.0.1:8081/api/mock/status | python3 -m json.tool
```

Expected: 5 accepted, sendable_count=0, acked_count=5.

## Test B - offline retry and catch-up

1. Stop the mock backend.
2. Enqueue 3 new messages.
3. Start Central Sync in foreground with the local-test config.
4. Observe retry_count > 0 and increasing attempt_count.
5. Restart the mock backend.
6. Within the backoff window, all pending messages become acked without recreating them.

## Test C - persistence across Central Sync restart

1. Stop mock backend.
2. Enqueue messages.
3. Run Central Sync long enough for at least one failed attempt.
4. Stop Central Sync.
5. Confirm the SQLite outbox still contains the same message_ids/sequences.
6. Restart mock backend and Central Sync. Confirm the same messages are ACKed.

## Test D - priority

Enqueue P3 messages, then a P0 test message. Query the mock backend after upload and verify the P0 message appears in the first eligible transport batch/order before older P3 work.

## Test E - existing gateway regression

```bash
systemctl is-active ems-v3-gateway.service
systemctl is-active ems-v3-soc-controller.service
curl -s http://127.0.0.1:8000/api/health -H 'Authorization: Bearer <TOKEN>'
```

G1 must not change existing gateway polling/control behavior. `central-sync.service` is independent.
