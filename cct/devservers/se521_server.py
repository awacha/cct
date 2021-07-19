from typing import Optional, List, Final
import gc
import struct
import logging

import usb.core, usb.util
import time
import asyncio

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SE521DevServer:
    port: int
    server: asyncio.AbstractServer
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    dev: Optional[usb.core.Device] = None
    interface: Optional[usb.core.Interface] = None
    ep_in: Optional[usb.core.Endpoint] = None
    ep_out: Optional[usb.core.Endpoint] = None
    known_cmds: Final[List[bytes]] = [b'A', b'B', b'C', b'M', b'N', b'K']
    lastcommandtime: float = 0
    commanddelay: float = 0
    cmdindex: int = 0

    def __init__(self, port: int=2000):
        self.port = port
        logger.info('Initialized a SE521 device server')

    def _initialize_usb(self):
        logger.info('Initializing USB device')
        self.dev = usb.core.find(idVendor=0x04d9, idProduct=0xe000)
        if self.dev.is_kernel_driver_active(0):
            self.dev.detach_kernel_driver(0)
        self.dev.set_configuration()
        config = self.dev.get_active_configuration()
        self.interface = config[(0,0)]

        self.ep_out = usb.util.find_descriptor(
            self.interface,
            custom_match=lambda ep: usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        self.ep_in = usb.util.find_descriptor(
            self.interface,
            custom_match=lambda ep: usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN)
        self.cmdindex=0

    def _close_usb(self):
        logger.info('Closing USB device')
        usb.util.release_interface(self.dev, self.interface.index)
        self.dev.reset()
        self.ep_in = None
        self.ep_out = None
        self.interface = None
        self.dev = None
        gc.collect()

    def _ctrl(self, data: bytes):
        for i in range(10):
            try:
                self.dev.ctrl_transfer(0x21, 0x09, 0x0300, 0, data)
                break
            except usb.core.USBError as usbe:
                logger.debug(usbe)
#                self.dev.clear_halt(self.ep_in)
#                self.dev.clear_halt(self.ep_out)
                logger.debug(f'Retry #{i}')
                time.sleep(0.1)
                continue

    def _ctrl_before_command(self):
        logger.debug('ctrl before command')
        self._ctrl(b'\x43\x01\x07\x00\x00\x00\x00\x00')

    def _ctrl_after_command_A(self):
        logger.debug('ctrl after command A')
        self._ctrl(b'C\x04@\x00\x00\x00\x00\x00')

    def _ctrl_after_command_K(self):
        logger.debug('ctrl after command k')
        self._ctrl(b'C\x04 \x00\x00\x00\x00\x00')

    def _sendCommand(self, cmd: bytes):
        time.sleep(max(0, self.lastcommandtime + self.commanddelay - time.monotonic()))
#        self._initialize_usb()
        if cmd not in self.known_cmds:
            raise ValueError(f'Unknown command: {cmd}')
        self._ctrl_before_command()
        logger.debug(f'Sending command {cmd}')
        self.ep_out.write(b'\x07\x02'+cmd+struct.pack('>L', self.cmdindex) + b'\x03')
        self.cmdindex = (self.cmdindex + 1) % (1 << 32)
        if cmd in [b'A']:
            self._ctrl_after_command_A()
        else:
            self._ctrl_after_command_K()
        recv = bytes(self.ep_in.read(96 if cmd in [b'A'] else 64))
        logger.debug(f'Got reply to command {cmd}')
        self.lastcommandtime = time.monotonic()
#        self._close_usb()
        return recv

    async def listen(self):
        self.server = await asyncio.start_server(self.acceptConnection, port=self.port)
        async with self.server:
            logger.info(f'Serving on port {self.port}')
            await self.server.serve_forever()

    async def acceptConnection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        if (self.reader is not None) or (self.writer is not None):
            # already connected
            logger.error('Another connection to the device is already active')
            writer.write(b'ERROR: Another connection to the device is already active.***')
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        logger.info(f'Accepted connection from {writer.transport.get_extra_info("peername")}')
        self.reader = reader
        self.writer = writer
        try:
            self._initialize_usb()
        except Exception as usbe:
            logger.error(f'Error while initializing the USB device: {usbe}')
            self.writer.write(f'ERROR: Error while initializing USB device: {usbe}***'.encode('utf-8'))
            await self.writer.drain()
            self.writer.close()
            await self.writer.wait_closed()
            return
        messageremainder = b''
        try:
            while True:
                logger.debug('Waiting for message')
                result = await self.reader.read(1024)
                logger.debug(f'Got message: {result}')
                if self.reader.at_eof():
                    logger.debug('At EOF: connection broken.')
                    logger.debug('Breaking.')
                    break
                logger.debug(f'Message remainder: {messageremainder}')
                messages = (messageremainder + result).split(b'\r\n')
                messageremainder = messages[-1]
                logger.debug(f'Message remainder after processing messages: {messageremainder}')
                for message in messages[:-1]:
                    await self.processMessage(message)
        finally:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
            self.reader = None
            try:
                self._close_usb()
            except usb.USBError as usbe:
                logger.warning(f'Error while closing the USB device: {usbe}')
            logger.info('Closed connection to client.')

    async def processMessage(self, message: bytes):
        logger.debug(f'Processing message {message=}')
        try:
            self.writer.write(b'OK['+message+b']: '+self._sendCommand(message)+b'***')
            await self.writer.drain()
        except Exception as exc:
            logger.error(f'{exc}')
            self.writer.write(f'ERROR: {exc}'.encode('utf-8')+b'***')
            await self.writer.drain()
            raise

    @classmethod
    def main(cls, port: int, verbose: bool):
        if verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        tcpcomm = cls(port)
        asyncio.run(tcpcomm.listen())
