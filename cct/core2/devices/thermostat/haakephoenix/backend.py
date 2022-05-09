import datetime
from math import inf
from typing import Sequence, Any, Tuple, List
import time

from ...device.backend import DeviceBackend, VariableType


class HaakePhoenixBackend(DeviceBackend):
    class Status(DeviceBackend.Status):
        Running = 'running'
        Stopped = 'stopped'

    varinfo = [
        DeviceBackend.VariableInfo(name='firmwareversion', dependsfrom=[], urgent=True, timeout=inf, vartype=VariableType.STR),
        DeviceBackend.VariableInfo(name='faultstatus', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.BYTES),
        DeviceBackend.VariableInfo(name='external_pt100_error', dependsfrom=['faultstatus'], urgent=False, timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='internal_pt100_error', dependsfrom=['faultstatus'], urgent=False, timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='cooling_error', dependsfrom=['faultstatus'], urgent=False, timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='liquid_level_low_error', dependsfrom=['faultstatus'], urgent=False,
                                   timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='external_alarm_error', dependsfrom=['faultstatus'], urgent=False, timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='pump_overload_error', dependsfrom=['faultstatus'], urgent=False, timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='liquid_level_alarm_error', dependsfrom=['faultstatus'], urgent=False,
                                   timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='overtemperature_error', dependsfrom=['faultstatus'], urgent=False,
                                   timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='main_relay_missing_error', dependsfrom=['faultstatus'], urgent=False,
                                   timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='control_external', dependsfrom=['faultstatus'], urgent=False,
                                   timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='temperature_control', dependsfrom=['faultstatus'], urgent=False,
                                   timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='fuzzycontrol', dependsfrom=[], urgent=False, timeout=inf, vartype=VariableType.STR),
        DeviceBackend.VariableInfo(name='fuzzystatus', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.UNKNOWN),
        DeviceBackend.VariableInfo(name='temperature_internal', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.FLOAT),
        DeviceBackend.VariableInfo(name='temperature_external', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.FLOAT),
        DeviceBackend.VariableInfo(name='temperature', dependsfrom=[], urgent=False, timeout=None, vartype=VariableType.FLOAT),
        DeviceBackend.VariableInfo(name='setpoint', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.FLOAT),
        DeviceBackend.VariableInfo(name='highlimit', dependsfrom=[], urgent=False, timeout=10, vartype=VariableType.FLOAT),
        DeviceBackend.VariableInfo(name='lowlimit', dependsfrom=[], urgent=False, timeout=10, vartype=VariableType.FLOAT),
        DeviceBackend.VariableInfo(name='diffcontrol_on', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='autostart', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='fuzzyid', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.UNKNOWN),
        DeviceBackend.VariableInfo(name='beep', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='time', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.TIME),
        DeviceBackend.VariableInfo(name='date', dependsfrom=[], urgent=False, timeout=5, vartype=VariableType.DATE),
        DeviceBackend.VariableInfo(name='watchdog_on', dependsfrom=[], urgent=False, timeout=inf, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='watchdog_setpoint', dependsfrom=[], urgent=False, timeout=inf, vartype=VariableType.FLOAT),
        DeviceBackend.VariableInfo(name='cooling_on', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='pump_power', dependsfrom=[], urgent=False, timeout=1.0, vartype=VariableType.FLOAT),
    ]
    outstandingqueryfailtimeout = 10.0
    delaybetweensends = 0.5


    def _query(self, variablename: str):
        if variablename == 'firmwareversion':
            self.enqueueHardwareMessage(b'R V1\r')
        elif variablename == 'faultstatus':
            self.enqueueHardwareMessage(b'R BS\r')
        elif variablename == 'fuzzycontrol':
            try:
                if self['firmwareversion'].startswith('2P/H'):
                    self.enqueueHardwareMessage(b'R FB\r')
                else:
                    self.updateVariable('fuzzycontrol', 'not supported')
            except KeyError:
                self.getVariable('fuzzycontrol').lastquery = None
        elif variablename == 'fuzzystatus':
            try:
                if self['firmwareversion'].startswith('2P/H'):
                    self.enqueueHardwareMessage(b'R FE\r')
                else:
                    self.updateVariable('fuzzystatus', False)
            except KeyError:
                self.getVariable('fuzzystatus').lastquery = None
        elif variablename == 'temperature_internal':
            self.enqueueHardwareMessage(b'R T1\r')
        elif variablename == 'temperature_external':
            self.enqueueHardwareMessage(b'R T3\r')
        elif variablename == 'setpoint':
            self.enqueueHardwareMessage(b'R SW\r')
        elif variablename == 'highlimit':
            self.enqueueHardwareMessage(b'R HL\r')
        elif variablename == 'lowlimit':
            self.enqueueHardwareMessage(b'R LL\r')
        elif variablename == 'diffcontrol_on':
            self.enqueueHardwareMessage(b'R FR\r')
        elif variablename == 'autostart':
            self.enqueueHardwareMessage(b'R ZA\r')
        elif variablename == 'fuzzyid':
            self.enqueueHardwareMessage(b'R ZI\r')
        elif variablename == 'beep':
            self.enqueueHardwareMessage(b'R ZB\r')
        elif variablename == 'time':
            self.enqueueHardwareMessage(b'R XT\r')
        elif variablename == 'date':
            self.enqueueHardwareMessage(b'R XD\r')
        elif variablename == 'watchdog_on':
            self.enqueueHardwareMessage(b'R WD\r')
        elif variablename == 'watchdog_setpoint':
            self.enqueueHardwareMessage(b'R WS\r')
        elif variablename == 'cooling_on':
            self.enqueueHardwareMessage(b'R CC\r')
        elif variablename == 'pump_power':
            self.enqueueHardwareMessage(b'R PF\r')
        else:
            self.error(f'Unknown variable: {variablename}')

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        msgs = message.split(b'\r')
        return msgs[:-1], msgs[-1]

    def interpretMessage(self, message: bytes, sentmessage: bytes):
        self.debug(f'Interpreting message: {message.decode("ascii")} (sent: {sentmessage.decode("ascii")[:-1]})')
        if message.startswith(b'F001'):
            self.error(f'Unknown command reported by the circulator. Last command: {sentmessage}')
        elif message.startswith(b'F123'):
            self.error(f'Range error reported by the circulator. Last command: {sentmessage}')
#        elif message.startswith(b'FE00'):
#            self.error(f'Received FE00 from the circulator. Last command: {sentmessage}')
        elif sentmessage == b'R V1\r':
            self.updateVariable('firmwareversion', message.decode('ascii'))
        elif message.startswith(b'BS'):  # reply to "R BS"
            if len(message) != 15:  # b'BS<12 0/1 characters>$'
                self.error(f'Invalid message: {message}')
            self.updateVariable('temperature_control', message[2] == b'1'[0])
            if self.updateVariable('control_external', message[3] == b'1'[0]):
                if message[3] == b'1'[0]:
                    try:
                        self.updateVariable('temperature', self['temperature_external'])
                    except KeyError:
                        pass
                else:
                    try:
                        self.updateVariable('temperature', self['temperature_internal'])
                    except KeyError:
                        pass
            self.updateVariable('main_relay_missing_error', message[4] == b'1'[0])
            self.updateVariable('overtemperature_error', message[5] == b'1'[0])
            self.updateVariable('liquid_level_alarm_error', message[6] == b'1'[0])
            self.updateVariable('pump_overload_error', message[7] == b'1'[0])
            self.updateVariable('external_alarm_error', message[8] == b'1'[0])
            self.updateVariable('cooling_error', message[9] == b'1'[0])
            self.updateVariable('liquid_level_low_error', message[11] == b'1'[0])
            self.updateVariable('internal_pt100_error', message[12] == b'1'[0])
            self.updateVariable('external_pt100_error', message[13] == b'1'[0])
            self.updateVariable('faultstatus', message[2:-1])
        elif message.startswith(b'FB'):
            self.updateVariable('fuzzycontrol', message[2:-1].decode('ascii'))
        elif message.startswith(b'FE'):
            self.updateVariable('fuzzystatus', int(message[2:-1]))
        elif message.startswith(b'T1'):
            self.updateVariable('temperature_internal', float(message[2:-1]))
            try:
                if not self['control_external']:
                    if self.updateVariable('temperature', float(message[2:-1])):
                        self.updateVariable('__auxstatus__', f'{float(message[2:-1]):.2f}°C')
            except KeyError:
                pass
        elif message.startswith(b'T3'):
            self.updateVariable('temperature_external', float(message[2:-1]))
            try:
                if self['control_external']:
                    if self.updateVariable('temperature', float(message[2:-1])):
                        self.updateVariable('__auxstatus__', f'{float(message[2:-1]):.2f}°C')
            except KeyError:
                pass
        elif message.startswith(b'SW'):
            self.updateVariable('setpoint', float(message[2:-1]))
        elif message.startswith(b'HL'):
            self.updateVariable('highlimit', float(message[2:-1]))
        elif message.startswith(b'LL'):
            self.updateVariable('lowlimit', float(message[2:-1]))
        elif message.startswith(b'FR'):
            self.updateVariable('diffcontrol_on', bool(int(message[2:3])))
        elif message.startswith(b'ZA'):
            self.updateVariable('autostart', bool(int(message[2:3])))
        elif message.startswith(b'ZI'):
            self.updateVariable('fuzzyid', bool(int(message[2:3])))
        elif message.startswith(b'ZB'):
            self.updateVariable('beep', bool(int(message[2:3])))
        elif message.startswith(b'XT'):
            h, m, s = [int(x) for x in message[2:-1].split(b':')]
            try:
                self.updateVariable('time', datetime.time(h, m, s))
            except ValueError:
                # RTC can glitch out sometimes, e.g. when the CMOS battery died.
                self.updateVariable('time', datetime.time(0, 0, 0))
        elif message.startswith(b'XD'):
            d, m, y = [int(x) for x in message[2:-1].split(b'.')]
            try:
                self.updateVariable('date', datetime.date(y + 2000, m, d))
            except ValueError:
                self.updateVariable('date', datetime.date(1900, 1, 1))
            pass
        elif message.startswith(b'WD'):
            self.updateVariable('watchdog_on', bool(int(message[2:3])))
        elif message.startswith(b'WS'):
            self.updateVariable('watchdog_setpoint', float(message[2:-1]))
        elif message.startswith(b'PF'):
            if self.updateVariable('pump_power', float(message[2:-1])):
                if (self['__status__'] == self.Status.Running) and (self['pump_power'] <= 0) and (
                        self.panicking == self.PanicState.Panicking):
                    super().doPanic()
                self.updateVariable('__status__',
                                    self.Status.Running if self['pump_power'] > 0 else self.Status.Stopped)
        elif message.startswith(b'CC'):
            self.updateVariable('cooling_on', bool(int(message[2:3])))
        elif message == b'$':
            if sentmessage == b'W TS 1\r':
                self.updateVariable('__status__', self.Status.Running)
            elif sentmessage == b'W TS 0\r':
                self.updateVariable('__status__', self.Status.Stopped)
                if self.panicking == self.PanicState.Panicking:
                    super().doPanic()
        else:
            self.error(f'Cannot interpret message: {message}. Sent message was: {sentmessage}')

    def issueCommand(self, name: str, args: Sequence[Any]):
        if name == 'start':
            self.enqueueHardwareMessage(b'W TS 1\r')
            self.queryVariable('cooling_on')
            self.queryVariable('pump_power')
            self.commandFinished(name, 'Starting circulation')
        elif name == 'stop':
            self.enqueueHardwareMessage(b'W TS 0\r')
            self.queryVariable('cooling_on')
            self.queryVariable('pump_power')
            self.commandFinished(name, 'Stopping circulation')
        elif name == 'alarm':
            self.enqueueHardwareMessage(b'W AL\r')
            self.commandError(name, 'Raising alarm')
        elif name == 'alarm_confirm':
            self.enqueueHardwareMessage(b'W EG\r')
            self.commandFinished(name, 'Resetting alarm')
        elif name == 'setpoint':
            value = args[0]
            if value < self['lowlimit'] or value > self['highlimit']:
                self.commandError(name, 'Desired set point out of bounds.')
            else:
                self.enqueueHardwareMessage(f'W SW {value:.2f}\r'.encode('ascii'))
                self.commandFinished(name, f'Setting set point to {value:.2f}°C')
            self.queryVariable('setpoint')
        elif name == 'highlimit':
            value = args[0]
            self.enqueueHardwareMessage(f'W HL {value:.2f}\r'.encode('ascii'))
            self.commandFinished(name, f'Setting high limit to {value:.2f}°C')
            self.queryVariable('highlimit')
        elif name == 'lowlimit':
            value = args[0]
            self.enqueueHardwareMessage(f'W LL {value:.2f}\r'.encode('ascii'))
            self.commandFinished(name, f'Setting low limit to {value:.2f}°C')
            self.queryVariable('lowlimit')
        elif name == 'external_control':
            self.enqueueHardwareMessage(b'OUT MODE 2 1\r' if args[0] else b'OUT MODE 2 0\r')
            self.commandFinished(name, f'Switching to {"external" if args[0] else "internal"} control')
        elif name == 'diffcontrol':
            self.enqueueHardwareMessage(b'W FR 1\r' if args[0] else b'W FR 0\r')
            self.commandFinished(name, f'Switching differential control to {"on" if args[0] else "off"}')
        elif name == 'autostart':
            self.enqueueHardwareMessage(b'W ZA 1\r' if args[0] else b'W ZA 0\r')
            self.commandFinished(name, f'Switching autostart to {"on" if args[0] else "off"}')
        elif name == 'fuzzyid':
            self.enqueueHardwareMessage(b'W ZI 1\r' if args[0] else b'W ZI 0\r')
            self.commandFinished(name, f'Switching fuzzyid to {"on" if args[0] else "off"}')
        elif name == 'beep':
            self.enqueueHardwareMessage(b'W ZB 1\r' if args[0] else b'W ZB 0\r')
            self.commandFinished(name, f'Switching beeper to {"on" if args[0] else "off"}')
        elif name == 'setdate':
            try:
                date = args[0] if args[0] is not None else datetime.datetime.now()
            except IndexError:
                date = datetime.datetime.now()
            if not isinstance(date, (datetime.date, datetime.datetime)):
                self.commandError(name, 'Invalid date')
            else:
                self.enqueueHardwareMessage(
                    f'W XD {date.day:02d}.{date.month:02d}.{int(date.year) % 100:02d}\r'.encode('ascii'))
                self.commandFinished(name, f'Setting date to {date}')
        elif name == 'settime':
            try:
                tm = args[0] if args[0] is not None else datetime.datetime.now()
            except IndexError:
                tm = datetime.datetime.now()
            if not isinstance(tm, (datetime.time, datetime.datetime)):
                self.commandError(name, 'Invalid time')
            else:
                self.enqueueHardwareMessage(
                    f'W XT {tm.hour:02d}:{tm.minute:02d}:{tm.second:02d}\r'.encode('ascii')
                )
                self.commandFinished(name, f'Setting time to {tm}')
        elif name == 'watchdog_on':
            self.enqueueHardwareMessage(b'W WD 1\r' if args[0] else b'W WD 0\r')
            self.commandFinished(name, f'Switching watchdog {"on" if args[0] else "off"}')
        elif name == 'watchdog_setpoint':
            self.enqueueHardwareMessage(f'W WS {args[0]:6.2f}\r'.encode('ascii'))
            self.commandFinished(name, f'Setting watchdog setpoint to {args[0]:6.2f}°C')
        elif name == 'cooling_on':
            self.enqueueHardwareMessage(b'W CC 1\r' if args[0] else b'W CC 0\r')
            self.commandFinished(name, f'Switching cooler {"on" if args[0] else "off"}')
        elif name == 'pump_power':
            value = args[0]
            if (value < 5) or (value > 100):
                self.commandError(name, f'Pump power {value}% is out of bounds.')
            else:
                self.enqueueHardwareMessage(f'W PF {value:5.2f}\r'.encode('ascii'))
                self.commandFinished(name, f'Setting pump power to {value}%')
        else:
            self.commandFinished(name, 'Unknown command')

    def doPanic(self):
        self.panicking = self.PanicState.Panicking
        if self['__status__'] == self.Status.Running:
            self.enqueueHardwareMessage(b'W TS 0\r')
        else:
            super().doPanic()

    async def _dosend(self, message: bytes, nreplies: int):
        self.debug(f'Sending message *{message}* to Haake Phoenix hardware, expecting {nreplies} replies.')
        await super()._dosend(message, nreplies)