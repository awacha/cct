import logging
import time

from pyModbusTCP.client import ModbusClient

from .device import Device
from .exceptions import DeviceError, CommunicationError

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Device_ModbusTCP(Device):
    """Device with Modbus over TCP connection.
    """

    def _get_connected(self):
        """Check if we have a connection to the device. You should not call
        this directly."""
        return hasattr(self, '_modbusclient')

    def _establish_connection(self):
        host, port, modbus_timeout = self._connection_parameters
        logger.debug('Connecting to device: {}:{:d}'.format(host, port))
        self._modbusclient = ModbusClient(host, port, timeout=modbus_timeout)
        if not self._modbusclient.open():
            raise DeviceError(
                'Error initializing Modbus over TCP connection to device {}:{:d}'.format(host, port))
        logger.debug('Connected to device {}:{:d}'.format(host, port))

    def _breakdown_connection(self):
        try:
            logger.debug('Disconnecting from device {}:{:d}'.format(
                self._modbusclient.host(), self._modbusclient.port()))
            self._modbusclient.close()
            del self._modbusclient
        except AttributeError:
            pass

    def _read_integer(self, regno):
        self._lastsendtime=time.monotonic()
        self._count_outmessages+=1
        result = self._modbusclient.read_holding_registers(regno, 1)
        if result is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error reading integer from register #{:d}'.format(regno))
        self._lastrecvtime=time.monotonic()
        self._count_inmessages+=1
        return result[0]

    def _write_coil(self, coilno, val):
        self._lastsendtime=time.monotonic()
        self._count_outmessages+=1
        result = self._modbusclient.write_single_coil(coilno, val)
        if result is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error writing {} to coil #{:d}'.format(val, coilno))
        self._lastrecvtime=time.monotonic()
        self._count_inmessages += 1

    def _read_coils(self, coilstart, coilnum):
        self._lastsendtime=time.monotonic()
        self._count_outmessages+=1
        result = self._modbusclient.read_coils(coilstart, coilnum)
        if result is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error reading coils #{:d} - #{:d}'.format(coilstart, coilstart + coilnum))
        self._lastrecvtime=time.monotonic()
        self._count_inmessages += 1
        return result
