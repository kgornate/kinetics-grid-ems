# EMS Gateway Current Implementation Plan

## Objective

This update converts the gateway package into a cleaner current-codebase structure. The main executable is now only a small entry point. Application orchestration, CLI parsing, mock service behavior, asset adapters, telemetry collection, command dispatching, runtime configuration, and protocol/profile descriptors live in dedicated modules.

The refactor is compatibility-first. It does not intentionally change the Flutter UDP packet shape, TCP command format, web dashboard API endpoints, log API behavior, CSV logging format, PCS/BMS/chiller service logic, or existing Modbus read/write behavior.

## Main result

`main.py` has been reduced from roughly 1800 lines to about 45 lines.

The entry point now only:

```text
1. Parses CLI arguments.
2. Creates EMSGatewayApplication.
3. Prints merged runtime config when requested.
4. Registers shutdown handlers.
5. Starts and stops the gateway application.
```

## New / updated structure

```text
imx93_gateway/
  main.py

  core/
    cli.py
    app/
      __init__.py
      gateway_application.py

    asset_registry.py
    command_dispatcher.py
    command_router.py
    telemetry_composer.py
    telemetry_pipeline.py
    runtime_config.py
    response_utils.py

    assets/
      base_asset.py
      chiller_asset.py
      pcs_asset.py
      bms_asset.py
      asset_profile.py
      asset_factory.py

    protocols/
      base_transport.py
      factory.py
      modbus_tcp_transport.py
      modbus_rtu_transport.py
      can_transport.py

  services/
    mock_gateway_service.py
    chiller_gateway_service.py
    pcs_gateway_service.py
    bms_gateway_service.py
    storage_logger.py
    log_query_service.py
```

## What moved out of main.py

### CLI parsing

Moved to:

```text
core/cli.py
```

This keeps all existing CLI flags intact:

```text
--config-file
--print-runtime-config
--mock
--pc-ip
--pcs-host / --pcs-port / --pcs-unit / --pcs-vendor
--bms-host / --bms-port / --bms-unit
--no-chiller / --no-pcs / --no-bms
--no-udp / --no-tcp / --no-log-http / --no-web-api
--web-api-port
--log-http-port
```

### Gateway orchestration

Moved to:

```text
core/app/gateway_application.py
```

This module now owns:

```text
Runtime config loading
Asset list/profile config loading
Chiller/PCS/BMS service startup
UDP/TCP/log/web API server startup
Telemetry pipeline integration
Command dispatcher integration
Gateway status response generation
Graceful shutdown
```

### Mock gateway service

Moved to:

```text
services/mock_gateway_service.py
```

Mock mode behavior remains the same. It still supports the same mock chiller telemetry and mock chiller command responses.

## Clean naming update

The package has been cleaned so code comments, docs, config filenames, and test filenames are no longer tied to refactor sequence labels.

Renamed config profiles:

```text
configs/actual_network_assets.json
configs/lab_pc_simulators.json
configs/mock_local.json
configs/future_asset_protocol_examples.json
```

Renamed test files:

```text
test_legacy_compatibility.py
test_asset_adapters.py
test_command_dispatcher.py
test_telemetry_pipeline.py
test_runtime_config.py
test_asset_protocol_config.py
```

## Current asset/protocol scalability status

### Config-only changes supported now

```text
PCS IP / port / unit change
BMS IP / port / unit change
PC IP change for Flutter UDP telemetry
PCS and BMS simulators on one PC using different Modbus TCP ports
PCS vendor switch between existing NJOY and Inpower/Empower profiles
Chiller serial port, baudrate, and slave ID updates
```

### Supported active runtime paths

```text
Chiller  -> Modbus RTU over RS485
PCS      -> Modbus TCP with existing PCS vendor profiles
BMS      -> Modbus TCP with current BMS register map/profile path
```

### Prepared but not yet active for real hardware

```text
BMS over CAN
PCS over CAN
BMS over Modbus RTU
PCS over Modbus RTU
New asset types over new protocols
```

The config/profile/protocol descriptor layer can represent these future assets cleanly, but actual working service/driver integration is still needed when those assets are introduced.

## Compatibility expectations

No Flutter or web dashboard code change should be required.

Preserved external behavior:

```text
UDP telemetry to Flutter on port 5005
TCP command server on port 6000
HTTP log API on port 7000
Web REST/SSE API on port 8000
Existing command names and response shapes
Existing telemetry packet shape
Existing log API filters and CSV logs
Existing PCS/BMS/chiller service behavior
```

## Recommended test command

For actual network testing:

```bash
python3 -u main.py \
  --config-file configs/actual_network_assets.json \
  2>&1 | tee gateway_run.log
```

If chiller is not connected:

```bash
python3 -u main.py \
  --config-file configs/actual_network_assets.json \
  --no-chiller \
  2>&1 | tee gateway_run.log
```

For PC-only simulators:

```bash
python3 -u main.py \
  --config-file configs/lab_pc_simulators.json \
  2>&1 | tee gateway_simulator_run.log
```

## Acceptance checklist

The update is acceptable when:

```text
1. Python syntax check passes.
2. All compatibility tests pass.
3. Runtime config prints expected values.
4. Gateway starts on i.MX93.
5. Flutter receives UDP telemetry.
6. Flutter TCP commands work.
7. Web dashboard works through Wi-Fi IP.
8. Log API and filters work.
9. Real PCS read/write works.
10. BMS simulator read/write works.
11. No frontend code changes are needed.
```
