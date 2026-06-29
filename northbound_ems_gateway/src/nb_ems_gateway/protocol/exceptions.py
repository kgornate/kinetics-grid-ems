class ModbusGatewayError(Exception):
    """Base exception for read-only Modbus gateway errors."""


class ModbusConnectionError(ModbusGatewayError):
    """Raised when the EMS Modbus TCP server cannot be reached."""


class ModbusReadError(ModbusGatewayError):
    """Raised when a read request fails."""


class ModbusWriteBlockedError(ModbusGatewayError):
    """Raised if any code path tries to write in read-only mode."""
