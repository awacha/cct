import time

import pyModbusTCP.client

from .backend import DeviceBackend
from .exceptions import CommunicationError, DeviceError


class ModbusClient(pyModbusTCP.client.ModbusClient):
    def __init__(self, logger, host=None, port=None, unit_id=None,
                 timeout=None, debug=None, auto_open=None, auto_close=None):
        super().__init__(host, port, unit_id, timeout, debug, auto_open, auto_close)
        self.logger = logger

    def __debug_msg(self, msg):
        if self.__last_error == pyModbusTCP.constants.MB_NO_ERR:
            self.logger.debug(msg)
        else:
            self.logger.error(msg)

    def _pretty_dump(self, label, data):
        return None

    def reset_errors(self):
        self.__last_error = pyModbusTCP.constants.MB_NO_ERR
        self.__last_except = pyModbusTCP.constants.EXP_NONE


# noinspection PyPep8Naming,PyAbstractClass
class DeviceBackend_ModbusTCP(DeviceBackend):
    """Device with Modbus over TCP connection.
    """

    modbus_send_retries = 3

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
        self._modbusclient = ModbusClient(self.logger, host, port, timeout=modbus_timeout, debug=True)
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
        result = None
        reconnect_failed = False
        for i in range(self.modbus_send_retries):
            if i > 0:
                self.logger.warning(
                    'Retrying read_integer({:d}) operation in ModbusTCP device {}'.format(
                        regno, self.name))
            self.lasttimes['send'] = time.monotonic()
            self.counters['outmessages'] += 1
            result = self._modbusclient.read_holding_registers(regno, 1)
            if result is not None:
                break
            elif (not self._modbusclient.is_open()) and (not self._modbusclient.open()):
                reconnect_failed = True
        if result is None:
            raise CommunicationError(
                'Error reading integer from register #{:d}. Error no: {:d}. Reconnect failed: {}'.format(
                    regno, self._modbusclient.last_error(), reconnect_failed))
        self.lasttimes['recv'] = time.monotonic()
        self.counters['inmessages'] += 1
        return result[0]

    def write_coil(self, coilno, val):
        result = None
        reconnect_failed = False
        for i in range(self.modbus_send_retries):
            if i > 0:
                self.logger.warning(
                    'Retrying write_coil({:d}, {}) operation in ModbusTCP device {}'.format(
                        coilno, val, self.name))
            self.lasttimes['send'] = time.monotonic()
            self.counters['outmessages'] += 1
            result = self._modbusclient.write_single_coil(coilno, val)
            if result is not None:
                break
            elif (not self._modbusclient.is_open()) and (not self._modbusclient.open()):
                reconnect_failed = True
        if result is None:
            raise CommunicationError(
                'Error writing {} to coil #{:d}. Error no: {:d}. Reconnect failed: {}'.format(
                    val, coilno, self._modbusclient.last_error(), reconnect_failed))
        self.lasttimes['recv'] = time.monotonic()
        self.counters['inmessages'] += 1

    def read_coils(self, coilstart, coilnum):
        result = None
        reconnect_failed = False
        for i in range(self.modbus_send_retries):
            if i > 0:
                self.logger.warning(
                    'Retrying read_coils({:d}, {:d}) operation in ModbusTCP device {}'.format(
                        coilstart, coilnum, self.name))
            self.lasttimes['send'] = time.monotonic()
            self.counters['outmessages'] += 1
            result = self._modbusclient.read_coils(coilstart, coilnum)
            if result is not None:
                break
            elif (not self._modbusclient.is_open()) and (not self._modbusclient.open()):
                reconnect_failed = True
        if result is None:
            raise CommunicationError(
                'Error reading coils #{:d} - #{:d}. Error no: {:d}. Reconnect failed: {}'.format(
                    coilstart, coilstart + coilnum, self._modbusclient.last_error(), reconnect_failed))
        self.lasttimes['recv'] = time.monotonic()
        self.counters['inmessages'] += 1
        return result
