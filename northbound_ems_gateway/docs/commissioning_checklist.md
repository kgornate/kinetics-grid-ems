# Commissioning Checklist

1. Confirm the existing EMS local IP address.
2. Confirm Modbus TCP server is enabled locally.
3. Confirm port 515 is reachable.
4. Confirm unit ID 1.
5. Confirm whether to read holding registers or input registers.
6. Confirm float byte/word order using a known value like SOC, grid frequency, or DC voltage.
7. Configure i.MX93 `eth1` in the same subnet as the EMS field network.
8. Confirm `eth0` application-side route for local dashboard or server upload.
9. Run `scripts/test_modbus_connection.py`.
10. Run `scripts/scan_float_order.py` on known value register.
11. Start gateway in real EMS mode.
12. Validate `/api/health`, `/api/assets`, `/api/alarms`, `/api/registers/map`.
