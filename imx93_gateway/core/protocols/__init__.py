"""Protocol descriptor/factory layer for EMS assets."""

from .base_transport import ProtocolDescriptor
from .factory import ProtocolFactory

__all__ = ["ProtocolDescriptor", "ProtocolFactory"]
