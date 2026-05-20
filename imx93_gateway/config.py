"""
Configuration file for i.MX93 EMS Gateway Backend.

This file contains all system-level configuration:
- Modbus RTU serial configuration
- Chiller slave ID
- TCP command server configuration
- UDP telemetry streaming configuration
- Polling intervals
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

# i.MX93 TCP server will listen on all available interfaces
TCP_COMMAND_HOST = "0.0.0.0"
TCP_COMMAND_PORT = 6000

# PC IP address where telemetry has to be sent
# Change this as per your PC Ethernet/Wi-Fi IP
PC_TELEMETRY_IP = "192.168.1.10"
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