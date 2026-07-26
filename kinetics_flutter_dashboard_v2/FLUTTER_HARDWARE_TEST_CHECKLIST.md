# Flutter + Gateway Hardware Test Checklist

## Connection

- [ ] PC Ethernet address is `192.168.10.10/24`.
- [ ] FRDM eth0 responds at `192.168.10.2`.
- [ ] `Test-NetConnection 192.168.10.2 -Port 8000` succeeds.
- [ ] Flutter login succeeds with the internal account.
- [ ] REST status is connected.
- [ ] Live WebSocket status is connected.

## BMS extraction

- [ ] BAU appears online.
- [ ] Rack 1, Rack 2, Rack 3, and Rack 4 appear online.
- [ ] HVAC appears online.
- [ ] Liquid cooling appears online.
- [ ] Energy meter appears online.
- [ ] Dehumidifier 1 and 2 appear online.
- [ ] Safety/fire I/O appears online.
- [ ] Complete extraction finishes without an API error.
- [ ] Rack detail pages contain bulk cell and temperature arrays.

## Data validation

- [ ] Bank voltage matches the BAU/HMI.
- [ ] Bank current sign and scale match the BAU/HMI.
- [ ] SOC and SOH match the BAU/HMI.
- [ ] Rack voltage/current/SOC values match each rack HMI.
- [ ] Highest and lowest cell values match the BMS display.
- [ ] Cooling and environmental values match their local controllers.
- [ ] Active alarms match the physical BMS state.

## Scheduler and storage

- [ ] Fast counter increments approximately every 1 second.
- [ ] Normal counter increments approximately every 5 seconds.
- [ ] Bulk counter increments approximately every 30 seconds.
- [ ] Slow counter increments approximately every 60 seconds.
- [ ] SQLite telemetry record count increases.
- [ ] Storage path reports the SD-card location.
- [ ] No unexpected polling errors appear.
