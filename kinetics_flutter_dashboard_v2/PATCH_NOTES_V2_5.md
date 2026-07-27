# Kinetics Flutter Dashboard V2.5

## Four-PCS Modbus RTU support

This release updates the PCS UI for the deployed RS485 topology:

- PCS 1: Modbus RTU slave ID 1
- PCS 2: Modbus RTU slave ID 2
- PCS 3: Modbus RTU slave ID 3
- PCS 4: Modbus RTU slave ID 4

The app now reads both the legacy `pcs` field and the multi-device `pcs_devices` map returned by the gateway.

## New PCS system page

- Four independent PCS cards
- Online/offline state for every slave ID
- Total active and reactive power
- Average grid voltage and frequency
- Highest PCS temperature
- Active PCS alarm count
- RS485 topology summary

## New PCS detail page

Each PCS has dedicated tabs:

- Overview
- DC side
- AC / Grid
- Thermal
- Operating status
- Alarms & faults
- Settings
- All signals

## Protocol-aware presentation

- PCS operating-state bit mask decoding
- Product-mode decoding
- PQ-mode decoding
- Remote/local and authorization status
- DC-breaker status
- Friendly names for core measurements, status words, fault words, and 0x1400 settings
- Correct unit formatting for kVar/kVA and temperature

The dashboard remains read-only. No PCS write controls are exposed.
