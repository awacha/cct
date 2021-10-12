# coding=utf-8
"""ModbusTCP communication"""
import struct
from typing import Optional, Tuple, Sequence


class ModbusTCP:
    """Mix-in class for modbus tcp communication"""
    _lastmodbustransactionid: int = 0

    def modbus_pack(self, functioncode: int, data: bytes) -> bytes:
        self._lastmodbustransactionid = (self._lastmodbustransactionid + 1) % 65536
        return struct.pack('>HHHBB',
                           self._lastmodbustransactionid,  # 2-byte transaction ID
                           0,  # 2-byte protocol mode, 0 for Modbus/TCP
                           len(data) + 2,  # 2-byte number of remaining bytes in this message
                           1,  # 1-byte unit ID
                           functioncode,  # 1-byte function code
                           ) + data

    def modbus_unpack(self, data: bytes, transactionid: Optional[int] = None) -> Tuple[int, bytes]:
        #        self.debug(f'Unpacking modbus message: {data}')
        # the data header is at least 7 bytes long
        if len(data) < 7:
            raise ValueError(f'Not enough bytes in Modbus/TCP message: needed 7, got {len(data)}')
        transactionid, protocolmode, datalength, unitid, functioncode = struct.unpack('>HHHBB', data[:8])
        if (transactionid is not None) and (transactionid != transactionid):
            raise ValueError(
                f'Transaction IDs do not match: expected {self._lastmodbustransactionid}, got {transactionid}')
        if protocolmode != 0:
            raise ValueError(f'Expected protocol mode 0, got {protocolmode}.')
        if unitid != 1:
            raise ValueError(f'Expected unit ID 1, got {unitid}.')
        if len(data) != datalength + 6:
            raise ValueError(f'Data length mismatch: expected {datalength + 6}, got {len(data)}')
        return functioncode, data[8:]

    def modbus_read_holding_registers(self, regno: int, nregs: int):
        self.enqueueHardwareMessage(self.modbus_pack(3, struct.pack('>HH', regno, nregs)), 1)

    def modbus_read_input_registers(self, regno: int, nregs: int):
        self.enqueueHardwareMessage(self.modbus_pack(4, struct.pack('>HH', regno, nregs)), 1)

    def modbus_read_coils(self, coilno: int, ncoils: int):
        self.enqueueHardwareMessage(self.modbus_pack(1, struct.pack('>HH', coilno, ncoils)), 1)

    def modbus_set_coil(self, coilno: int, value: bool):
        self.enqueueHardwareMessage(self.modbus_pack(5, struct.pack('>HBB', coilno, 0xff if value else 0, 0)))

    def modbus_write_register(self, regno: int, value: int):
        self.enqueueHardwareMessage(self.modbus_pack(6, struct.pack('>HH', regno, value)))

    def modbus_write_registers(self, regno: int, values: Sequence[int]):
        self.enqueueHardwareMessage(self.modbus_pack(16, struct.pack('>H' + 'H' * len(values), regno, *values)))
