"""
Configuration file for i.MX93 EMS Gateway Backend.

This file contains all system-level configuration:
- Modbus RTU serial configuration for Chiller
- Modbus TCP configuration for PCS/Inverter
- TCP command server configuration
- UDP telemetry streaming configuration
- Polling intervals
- Storage logging configuration
- HTTP log API configuration
"""

# -------------------------------------------------
# Modbus RTU Configuration - Chiller
# -------------------------------------------------

CHILLER_ENABLED = True

MODBUS_PORT = "/dev/ttyUSB0"
MODBUS_BAUDRATE = 9600
MODBUS_BYTESIZE = 8
MODBUS_PARITY = "N"
MODBUS_STOPBITS = 1
MODBUS_TIMEOUT_SEC = 2

CHILLER_SLAVE_ID = 1


# -------------------------------------------------
# Modbus TCP Configuration - PCS / Inverter
# -------------------------------------------------
# Current MVP setup:
# PC / ModSim IP  = 192.168.10.1
# i.MX93 IP       = 192.168.10.2
#
# Later field setup:
# PCS_HOST can be changed to actual inverter IP, for example 192.168.1.200.

PCS_ENABLED = True

PCS_VENDOR = "njoy"
PCS_ASSET_ID = "pcs_1"

PCS_HOST = "192.168.10.1"
PCS_PORT = 502
PCS_UNIT_ID = 1

PCS_TIMEOUT_SEC = 3.0
PCS_RETRIES = 2
PCS_POLL_INTERVAL_SEC = 5.0


# -------------------------------------------------
# Ethernet / Network Configuration
# -------------------------------------------------

TCP_COMMAND_HOST = "0.0.0.0"
TCP_COMMAND_PORT = 6000

# PC running Flutter dashboard / UDP listener.
PC_TELEMETRY_IP = "192.168.10.1"
UDP_TELEMETRY_PORT = 5005


# -------------------------------------------------
# Gateway Runtime Configuration
# -------------------------------------------------

CHILLER_POLL_INTERVAL_SEC = 1.0
UDP_TELEMETRY_INTERVAL_SEC = 1.0


# -------------------------------------------------
# Asset Information
# -------------------------------------------------

ASSET_ID = "chiller_1"
GATEWAY_ID = "imx93_gateway_1"


# -------------------------------------------------
# Storage / eMMC / SD Card Logging Configuration
# -------------------------------------------------

ENABLE_STORAGE_LOGGING = True

# Existing chiller + PCS logging path.
# Keeping this unchanged to avoid breaking the current working log flow.
LOG_BASE_PATH = "/home/root/ems_logs_test"

# Later, when SD card comes, change only this path:
# LOG_BASE_PATH = "/mnt/ems_sdcard"

# Modbus polling can be fast, but storage logging should be slower
# to reduce unnecessary writes.
LOG_TELEMETRY_INTERVAL_SEC = 5.0

# PCS can use the same logging interval or a separate interval.
PCS_LOG_TELEMETRY_INTERVAL_SEC = 5.0


# -------------------------------------------------
# HTTP Log API Server Configuration
# -------------------------------------------------

ENABLE_LOG_HTTP_SERVER = True

# Listen on all i.MX93 interfaces so PC/Flutter can access it over Ethernet.
LOG_HTTP_HOST = "0.0.0.0"

# Browser/Flutter URL example:
# http://192.168.10.2:7000/api/storage/status?asset_id=pcs_1
LOG_HTTP_PORT = 7000

# Maximum rows returned by one log API call.
LOG_API_MAX_ROWS = 500
