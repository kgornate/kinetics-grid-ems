"""
Configuration file for i.MX93 EMS Gateway Backend.

This file contains all system-level configuration:
- Modbus RTU serial configuration
- Chiller slave ID
- TCP command server configuration
- UDP telemetry streaming configuration
- Polling intervals
- Storage logging configuration
- HTTP log API configuration
"""

# -------------------------------------------------
# Modbus RTU Configuration
# -------------------------------------------------

MODBUS_PORT = "/dev/ttyUSB0"
MODBUS_BAUDRATE = 9600
MODBUS_BYTESIZE = 8
MODBUS_PARITY = "N"
MODBUS_STOPBITS = 1
MODBUS_TIMEOUT_SEC = 2

CHILLER_SLAVE_ID = 1


# -------------------------------------------------
# Ethernet / Network Configuration
# -------------------------------------------------

TCP_COMMAND_HOST = "0.0.0.0"
TCP_COMMAND_PORT = 6000

# Change this as per your PC Ethernet/Wi-Fi IP.
# For direct PC <-> i.MX93 Ethernet, this is commonly 192.168.10.1.
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

# Current development target: i.MX93 eMMC/local filesystem
LOG_BASE_PATH = "/home/root/ems_logs_test"

# Later, when SD card comes, change only this path:
# LOG_BASE_PATH = "/mnt/ems_sdcard"

# Modbus polling can be 1 sec, but storage logging should be slower
# to reduce unnecessary writes.
LOG_TELEMETRY_INTERVAL_SEC = 5.0


# -------------------------------------------------
# HTTP Log API Server Configuration
# -------------------------------------------------

ENABLE_LOG_HTTP_SERVER = True

# Listen on all i.MX93 interfaces so PC/Flutter can access it over Ethernet.
LOG_HTTP_HOST = "0.0.0.0"

# Browser/Flutter URL example:
# http://192.168.10.2:7000/api/storage/status
LOG_HTTP_PORT = 7000

# Maximum rows returned by one log API call.
LOG_API_MAX_ROWS = 500