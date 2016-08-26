import logging
import time

from pyModbusTCP.client import ModbusClient

from .backend import DeviceBackend
from .exceptions import DeviceError, CommunicationError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# noinspection PyPep8Naming
class DeviceBackend_ModbusTCP(DeviceBackend):
    """Device with Modbus over TCP connection.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._modbusclient = None

    def get_connected(self) -> bool:
        """Check if the device is connected.
        """
        if self._modbusclient is None:
            return False
        elif self._modbusclient.is_open():
            return True
        else:
            raise ConnectionError('Modbusclient is not open')

    def establish_connection(self):
        """Establish a connection to the device.

        Raises a DeviceError if the connection cannot be established.

        Connection and communication parameters are found in
        self.deviceconnectionparameters
        """
        host, port, modbus_timeout = self.deviceconnectionparameters
        self.logger.debug('Connecting to ModbusTCP device: {}:{:d}'.format(host, port))
        self._modbusclient = ModbusClient(host, port, timeout=modbus_timeout)
        if not self._modbusclient.open():
            self._modbusclient = None
            raise DeviceError(
                'Error initializing Modbus over TCP connection to device {}:{:d}'.format(host, port))
        self.logger.debug('Connected to device {}:{:d}'.format(host, port))

    def breakdown_connection(self):
        """Break down the connection to the device.

        Abstract method: override this in subclasses.

        Should not raise an exception.

        This method can safely assume that a connection exists to the
        device.
        """
        try:
            self.logger.debug('Disconnecting from device {}:{:d}'.format(
                self._modbusclient.host(), self._modbusclient.port()))
            self._modbusclient.close()
            self._modbusclient = None
        except AttributeError:
            self._modbusclient = None

    def read_integer(self, regno):
        self.lasttimes['send'] = time.monotonic()
        self.counters['outmessages'] += 1
        result = self._modbusclient.read_holding_registers(regno, 1)
        if result is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error reading integer from register #{:d}'.format(regno))
        self.lasttimes['recv'] = time.monotonic()
        self.counters['inmessages'] += 1
        return result[0]

    def write_coil(self, coilno, val):
        self.lasttimes['send'] = time.monotonic()
        self.counters['outmessages'] += 1
        result = self._modbusclient.write_single_coil(coilno, val)
        if result is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error writing {} to coil #{:d}'.format(val, coilno))
        self.lasttimes['recv'] = time.monotonic()
        self.counters['inmessages'] += 1

    def read_coils(self, coilstart, coilnum):
        self.lasttimes['send'] = time.monotonic()
        self.counters['outmessages'] += 1
        result = self._modbusclient.read_coils(coilstart, coilnum)
        if result is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error reading coils #{:d} - #{:d}'.format(coilstart, coilstart + coilnum))
        self.lasttimes['recv'] = time.monotonic()
        self.counters['inmessages'] += 1
        return result
