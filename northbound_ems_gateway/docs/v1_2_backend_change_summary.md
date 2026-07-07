# v1.2 Backend Change Summary

Implemented backend-only update for two independent Chinese EMS/BESS sources.

## Completed phases

1. New Unity261PV Excel register map integrated.
2. Multi-source config model added for `external_ems_1` and `external_ems_2`.
3. Multi-reader Modbus TCP support added.
4. Polling scheduler updated to poll the same base map for each source.
5. Asset and telemetry namespace model added so EMS1/EMS2 signals do not overwrite each other.
6. Source APIs added.
7. Raw EMS command APIs made source-aware.
8. High-level control service and APIs added.
9. Voltage stabilization logic added using registers `346`, `348`, and `350`.

## Tests

`pytest -q` passes with 10 tests.
