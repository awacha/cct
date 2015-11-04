'''
Created on Oct 15, 2015

@author: labuser
'''
import weakref

from gi.repository import GLib

from .command import Command, CommandError


class Shutter(Command):
    """Open or close the shutter.

    Invocation: shutter(<state>)

    Arguments:
        <state>: 'close', 'open', True, False or a numeric boolean value

    Remarks: None
    """

    name = 'shutter'

    timeout = 2

    def execute(self, interpreter, arglist, instrument, namespace):
        self._check_for_variable = 'shutter'
        if arglist[0] == 'close':
            self._check_for_value = False
        elif arglist[0] == 'open':
            self._check_for_value = True
        elif isinstance(arglist[0], int) or isinstance(arglist[0], bool) or isinstance(arglist[0], float):
            self._check_for_value = (arglist[0] != 0)
        else:
            raise NotImplementedError(arglist[0], type(arglist[0]))
        self._require_device(instrument, instrument.xray_source._instancename)
        self._install_timeout_handler(self.timeout)
        instrument.xray_source.shutter(self._check_for_value)
        instrument.xray_source.refresh_variable('shutter')


class Xrays(Command):
    """Enable or disable X-ray generation

    Invocation: xrays(<state>)

    Arguments:
        <state>: 'on', 'off', True, False or a numeric boolean value

    Remarks: None
    """

    name = 'xrays'

    timeout = 2

    def execute(self, interpreter, arglist, instrument, namespace):
        self._check_for_variable = 'xrays'
        if arglist[0] == 'off':
            self._check_for_value = False
        elif arglist[0] == 'on':
            self._check_for_value = True
        elif isinstance(arglist[0], int) or isinstance(arglist[0], bool) or isinstance(arglist[0], float):
            self._check_for_value = bool(arglist)
        self._require_device(instrument, instrument.xray_source._instancename)
        self._install_timeout_handler(self.timeout)
        instrument.xray_source.execute_command('xrays', self._check_for_value)
        instrument.xray_source.refresh_variable('xrays')


class XrayFaultsReset(Command):
    """Reset faults in GeniX

    Invocation: xray_reset_faults()

    Arguments:
        <state>: 'on', 'off', True, False or a numeric boolean value

    Remarks: None
    """

    name = 'xray_reset_faults'

    timeout = 2

    def execute(self, interpreter, arglist, instrument, namespace):
        self._check_for_variable = 'faults'
        self._check_for_value = False
        self._require_device(instrument, instrument.xray_source._instancename)
        self._install_timeout_handler(self.timeout)
        instrument.xray_source.execute_command(
            'reset_faults')


class Xray_Power(Command):
    """Set the power of the X-ray source

    Invocation: xray_power(<state>)

    Arguments:
        <state>: 
            'down', 'off', 0, '0', '0W': turn the power off
            'standby', 'low', 9, '9', '9W': standby (low-power mode)
            'full', 'high', 30, '30', '30W': full-power mode

    Remarks: None
    """

    name = 'xray_power'

    def execute(self, interpreter, arglist, instrument, namespace):
        xray_source = instrument.xray_source
        self._check_for_variable = '_status'
        self._require_device(instrument, xray_source._instancename)
        if arglist[0] in ['down', 'off', 0, '0', '0W']:
            self._check_for_value = 'Power off'
            if xray_source.get_variable('_status') == 'Power off':
                GLib.idle_add(lambda xrs=xray_source, val=self._check_for_value: self.on_variable_change(xrs, '_status',
                                                                                                         val) and False)
            self._install_pulse_handler('Powering off', 1)
            xray_source.execute_command('poweroff')
        elif arglist[0] in ['standby', 'low', 9, '9', '9W']:
            self._check_for_value = 'Low power'
            if xray_source.get_variable('_status') == 'Low power':
                GLib.idle_add(lambda xrs=xray_source, val=self._check_for_value: self.on_variable_change(xrs, '_status',
                                                                                                         val) and False)
            self._install_pulse_handler('Going to low power', 1)
            xray_source.execute_command('standby')
        elif arglist[0] in ['full', 'high', 30, '30', '30W']:
            self._check_for_value = 'Full power'
            if xray_source.get_variable('_status') == 'Full power':
                GLib.idle_add(lambda xrs=xray_source, val=self._check_for_value: self.on_variable_change(xrs, '_status',
                                                                                                         val) and False)
            self._install_pulse_handler('Going to full power', 1)
            xray_source.execute_command('full_power')
        xray_source.refresh_variable('_status')


class Warmup(Command):
    """Start the warming-up procedure of the X-ray source

    Invocation: xray_warmup()

    Arguments: None

    Remarks: None
    """
    name = 'xray_warmup'

    def execute(self, interpreter, arglist, instrument, namespace):
        self.xray_source = weakref.proxy(instrument.xray_source)
        self._check_for_variable = '_status'
        self._require_device(instrument, self.xray_source._instancename)
        self._check_for_value = 'Power off'
        if self.xray_source.get_variable('_status') == 'Warming up':
            raise CommandError('Warm-up already running')
        if self.xray_source.get_variable('_status') != 'Power off':
            raise CommandError('Warm-up can only be started from power off mode')
        self._install_pulse_handler('Warming up', 1)
        self.xray_source.execute_command('start_warmup')
        self.xray_source.refresh_variable('_status')

    def kill(self):
        self.xray_source.execute_command('stop_warmup')
        self.xray_source.execute_command('poweroff')
