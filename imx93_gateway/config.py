"""
Configuration file for i.MX93 EMS Gateway Backend.

This file contains all system-level configuration:
- Modbus RTU serial configuration for Chiller
- Modbus TCP configuration for PCS/Inverter
- Modbus TCP configuration for BMS/BCU
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
# Modbus TCP Configuration - BMS / BCU
# -------------------------------------------------
# Current MVP setup:
# PC / ModSim IP  = 192.168.10.1
# i.MX93 IP       = 192.168.10.2
#
# Use port 502 if ModSim allows it.
# Use port 1502 if port 502 is blocked or already used.

BMS_ENABLED = True

BMS_ASSET_ID = "bms_1"
BMS_PROTOCOL = "modbus_tcp"

BMS_MODBUS_HOST = "192.168.10.1"
BMS_MODBUS_PORT = 502
BMS_UNIT_ID = 1

BMS_MODBUS_TIMEOUT_SEC = 2.0
BMS_ADDRESS_OFFSET = 0

BMS_POLL_INTERVAL_SEC = 1.0
BMS_CORE_POLL_INTERVAL_SEC = 1.0
BMS_ALARM_POLL_INTERVAL_SEC = 2.0
BMS_STATUS_POLL_INTERVAL_SEC = 2.0

BMS_COMMUNICATION_LOST_AFTER_SEC = 5.0
BMS_COMMAND_VERIFY_DELAY_SEC = 0.3

BMS_ENABLE_STORAGE_LOGGING = True
BMS_TELEMETRY_LOG_INTERVAL_SEC = 5.0

BMS_TCP_COMMANDS = {
    "READ_BMS",
    "READ_BMS_ALL",
    "BMS_READ_ALL",
    "READ_BMS_ALARMS",
    "BMS_READ_ALARMS",
    "START_BMS_PRECHARGE",
    "STOP_BMS_PRECHARGE",
    "START_BMS_INSULATION_TEST",
    "START_INSULATION_TEST",
    "BMS_FAN_AUTO",
    "BMS_FAN_ON",
    "BMS_FAN_OFF",
    "RESET_BCU",
    "RESET_BMS",
}


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

# Existing chiller + PCS + BMS logging path.
# Keeping this unchanged to avoid breaking the current working log flow.
LOG_BASE_PATH = "/home/root/ems_logs_test"

# Later, when SD card comes, change only this path:
# LOG_BASE_PATH = "/mnt/ems_sdcard"

# Modbus polling can be fast, but storage logging should be slower
# to reduce unnecessary writes.
LOG_TELEMETRY_INTERVAL_SEC = 5.0

# Asset-specific logging intervals.
PCS_LOG_TELEMETRY_INTERVAL_SEC = 5.0
BMS_LOG_TELEMETRY_INTERVAL_SEC = 5.0


# -------------------------------------------------
# HTTP Log API Server Configuration
# -------------------------------------------------

ENABLE_LOG_HTTP_SERVER = True

# Listen on all i.MX93 interfaces so PC/Flutter can access it over Ethernet.
LOG_HTTP_HOST = "0.0.0.0"

# Browser/Flutter URL example:
# http://192.168.10.2:7000/api/storage/status?asset_id=bms_1
LOG_HTTP_PORT = 7000

# Maximum rows returned by one log API call.
LOG_API_MAX_ROWS = 500
