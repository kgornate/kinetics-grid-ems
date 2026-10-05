# Phase 4 Read-Only Commissioning Runbook

## Important

Phase 4 is deliberately read-only. Do not enable BMS writes, PCS writes, or the control sequence during this phase.

## 1. Install complete codebase

Copy/extract the complete Phase-4 package to the target gateway, or use:

```sh
sh deployment/install_phase4_readonly_on_imx93.sh
```

The installer deliberately does **not** start the service automatically.

## 2. Edit the site configuration

Edit:

```text
/etc/ornate-ems-gateway/config.json
```

At minimum replace:

- Lineage BMS host/IP.
- BAMS/system port and Unit ID.
- Rack 1..4 ports and Unit IDs.
- Elecod PCS 1..4 IP/port/Unit-ID routes.
- Gateway network CIDRs if different from the template.

Keep:

```json
"mode": "read_only"
```

and verify:

```json
"bms": { "write_enabled": false },
"pcs": { "write_enabled": false },
"control_sequence": { "enabled": false }
```

## 3. Basic network checks

From the gateway, validate each configured IP and Modbus TCP port with the Linux tools available on the image, for example `ip` and `nc`.

## 4. Run the safe direct probe first

```sh
cd /opt/ornate-ems-gateway/backend
ORNATE_EMS_CONFIG=/etc/ornate-ems-gateway/config.json \
  /opt/ornate-ems-gateway/venv/bin/python tools/phase4_readonly_commission.py \
  --config /etc/ornate-ems-gateway/config.json \
  --include-normal \
  --output /tmp/phase4_readonly_report.json
```

This tool refuses to run unless the configuration is read-only and every write/control gate is disabled.

## 5. Validate Lineage decoding

Compare live HMI/BMS values against:

- System voltage.
- System SOC.
- Rack 1..4 voltage.
- Rack 1..4 SOC.
- Maximum charge/discharge power.

If FLOAT values are impossible, do not change application logic. First test the configured `word_order` and confirm the Modbus address offset.

## 6. Validate Elecod decoding

Compare PCS HMI against:

- Grid voltage.
- Grid frequency.
- Total active power.
- DC voltage.
- DC current.
- Status word/run state.

Phase 4 does not test active-power write direction.

## 7. Start gateway service

Only after direct reads are credible:

```sh
systemctl start ornate-ems-gateway.service
systemctl --no-pager status ornate-ems-gateway.service
```

## 8. Validate APIs

Check:

```text
GET /api/health
GET /api/assets
GET /api/telemetry/snapshot
GET /api/normalized/snapshot
GET /api/normalized/pairs
GET /api/bms/bank
GET /api/bms/racks
GET /api/pcs/all
GET /api/alarms
GET /api/diagnostics/polling
GET /api/commissioning/read-only   (internal role)
```

## 9. Only after Phase-4 sign-off

Proceed to Phase 5 for guarded startup/stop/charge/discharge integration. Do not manually enable writes in the Phase-4 build as a shortcut.
