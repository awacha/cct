"""Exceptions raised by low-level devices"""

class DeviceError(Exception):
    """General device error parent class"""
    pass

class WatchdogTimeout(DeviceError):
    """Raised on watchdog timeout."""
    pass

class InvalidValue(DeviceError):
    """Raised when an invalid value is tried to be written to a device variable """
    pass

class ReadOnlyVariable(DeviceError):
    """Raised on an attempted write to a read-only device variable"""
    pass

class CommunicationError(DeviceError):
    """Raised when a fatal communication error occurs. The connection to the device must immediately be shut down and possibly reinitialized"""
    pass
