from pyModbusTCP.client import ModbusClient

from .device import Device
from .exceptions import DeviceError, CommunicationError


class Device_ModbusTCP(Device):
    """Device with Modbus over TCP connection.
    """

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)

    def _get_connected(self):
        """Check if we have a connection to the device. You should not call
        this directly."""
        return hasattr(self, '_modbusclient')

    def connect_device(self, host, port, modbus_timeout):
        self._logger.debug('Connecting to device: %s:%d' % (host, port))
        if self._get_connected():
            raise DeviceError('Already connected')
        self._connection_parameters = (host, port, modbus_timeout)
        self._modbusclient = ModbusClient(host, port, timeout=modbus_timeout)
        if not self._modbusclient.open():
            raise DeviceError(
                'Error initializing Modbus over TCP connection to device %s:%d' % (host, port))
        try:
            self._initialize_after_connect()
            try:
                self._start_background_process()
            except Exception as exc:
                self._finalize_after_disconnect()
                raise exc
        except Exception as exc:
            self._modbusclient.close()
            del self._modbusclient
            raise exc
        self._logger.debug('Connected to device %s:%d' % (host, port))

    def disconnect_device(self, because_of_failure=False):
        if not self._get_connected():
            raise DeviceError('Not connected')
        self._logger.debug('Disconnecting from device %s:%d%s' % (
            self._modbusclient.host(), self._modbusclient.port(), ['', ' because of a failure'][because_of_failure]))
        try:
            self._stop_background_process()
            self._logger.debug('Stopped background process')
            self._finalize_after_disconnect()
            self._logger.debug('Finalized')
            self._modbusclient.close()
            self._logger.debug('Closed socket')
        finally:
            del self._modbusclient
            self.emit('disconnect', because_of_failure)

    def reconnect_device(self):
        self.connect_device(*self._connection_parameters)

    def _read_integer(self, regno):
        result = self._modbusclient.read_holding_registers(regno, 1)
        if result is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error reading integer from register #%d' % regno)
        return result[0]


    def _write_coil(self, coilno, val):
        if self._modbusclient.write_single_coil(coilno, val) is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error writing %s to coil #%d' % (val, coilno))

    def _read_coils(self, coilstart, coilnum):
        result = self._modbusclient.read_coils(coilstart, coilnum)
        if result is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error reading coils #%d - #%d' % (coilstart, coilstart + coilnum))
        return result
