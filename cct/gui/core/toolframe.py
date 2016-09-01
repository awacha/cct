import logging
import os
import traceback
import weakref
from typing import Optional, List, Union

import pkg_resources

from .builderwidget import BuilderWidget
from .dialogs import error_message
from ...core.devices import Device, Motor
from ...core.instrument.instrument import Instrument
from ...core.instrument.privileges import PRIV_LAYMAN

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ToolFrameException(Exception):
    pass


class ToolFrameDeviceRequirementException(ToolFrameException):
    pass


class ToolFrame(BuilderWidget):
    widgets_to_make_insensitive = []
    privlevel = PRIV_LAYMAN
    required_devices = []

    class TFException(Exception):
        pass

    class DeviceException(TFException):
        pass

    class PrivilegeException(TFException):
        pass

    def __init__(self, gladefile: str, mainwidgetname: str, instrument: Instrument, *args, **kwargs):
        super().__init__(pkg_resources.resource_filename(
            'cct', os.path.join('resource/glade', gladefile)), mainwidgetname)
        if not isinstance(instrument, weakref.ProxyTypes):
            instrument = weakref.proxy(instrument)
        self.instrument = instrument
        self._sensitive = True
        self._device_connections = {}
        self._widgets_insensitive = []
        # check if all required devices are available
        for d in self.required_devices:
            try:
                self.instrument.get_device(d)
            except KeyError as exc:
                self.widget.set_sensitive(False)
                # error_message(self.widget, 'Device error', 'Required device {} not present.'.format(d))
                logger.error('Required device ' + d + ' not present while mapping toolframe ' + self.gladefile)
                raise self.DeviceException(d)
        try:
            self.init_gui(*args, **kwargs)
        except Exception as exc:
            error_message(self.widget, 'Cannot initialize toolframe ' + mainwidgetname, traceback.format_exc())
            raise
        self.builder.connect_signals(self)
        # show all subwidgets but not ourselves.
        self.widget.foreach(lambda x: x.show_all())
        self._accounting_connections = [
            self.instrument.services['accounting'].connect('privlevel-changed', self.on_privlevel_changed)]

    def on_privlevel_changed(self, accounting, newprivlevel):
        if not self.instrument.services['accounting'].has_privilege(self.privlevel):
            self.widget.set_sensitive(False)
        else:
            if not self.widget.get_sensitive():
                self.widget.set_sensitive(True)
                self.on_mainwidget_map(self.widget)

    def init_gui(self, *args, **kwargs):
        pass

    def set_sensitive(self, state: bool, reason: Optional[str] = None, additional_widgets: Optional[List] = None):
        if state:
            for w in self._widgets_insensitive:
                w.set_sensitive(True)
            self._widgets_insensitive = []
            self._sensitive = True
        else:
            if additional_widgets is None:
                additional_widgets = []
            additional_widgets = ([aw for aw in additional_widgets if not isinstance(aw, str)] +
                                  [self.builder.get_object(aw) for aw in additional_widgets if isinstance(aw, str)])
            for w in [self.builder.get_object(w_) for w_ in self.widgets_to_make_insensitive] + additional_widgets:
                w.set_sensitive(False)
                self._widgets_insensitive.append(w)
            self._sensitive = False

    def get_sensitive(self):
        return self._sensitive

    def on_mainwidget_map(self, window):
        """This function should connect all signal handlers to devices, as
        well as do an update to the GUI.

        In subclasses, you typically need to invoke the inherited method first,
        and if it returns True, you must refrain from further operations,
        because the window cannot be mapped. If it returns False, you are free
        to continue the realization of the window (connecting signal handlers,
        etc.). Please do the same: return True if the window cannot be realized
        and False if everything is OK.
        """
        logger.debug('Mapping main widget for ToolFrame ' + self.gladefile)
        super().on_mainwidget_map(window)
        if not self.instrument.services['accounting'].has_privilege(self.privlevel):
            self.widget.set_sensitive(False)
            error_message(self.widget, 'Privilege error',
                          'Insufficient privileges to open {}.'.format(self.widget.get_title()))
            logger.warning('Privilege error while mapping toolframe ' + self.gladefile)
            return True
        # connect to various signals of devices
        self._disconnect_device_connections()
        for d in self.required_devices:
            dev = self.instrument.get_device(d)
            self._device_connections[d] = [
                dev.connect('variable-change', self.on_device_variable_change),
                dev.connect('error', self.on_device_error),
                dev.connect('disconnect', self.on_device_disconnect)
            ]
            if isinstance(dev, Motor):
                self._device_connections[d].extend([
                    dev.connect('position-change', self.on_motor_position_change),
                    dev.connect('stop', self.on_motor_stop),
                ])
        logger.debug('Successfully mapped main widget for ToolFrame ' + self.gladefile)
        return False

    def _disconnect_device_connections(self):
        for d in self._device_connections:
            logger.debug('Cleaning up {:d} connections to device {}'.format(len(self._device_connections[d]), d))
            dev = self.instrument.get_device(d)
            for c in self._device_connections[d]:
                dev.disconnect(c)
            logger.debug('Cleaned up {:d} connections to device {}'.format(len(self._device_connections[d]), d))
        self._device_connections = {}

    def on_device_variable_change(self, device: Union[Device, Motor], variablename: str, newvalue: object):
        return False

    def on_device_error(self, device: Union[Device, Motor], variablename: str, exception: Exception,
                        traceback_str: str):
        return False

    def on_device_disconnect(self, device: Union[Device, Motor], abnormal_disconnect: bool):
        return False

    def on_motor_position_change(self, motor: Motor, newposition: float):
        return False

    def on_motor_stop(self, motor: Motor, targetreached: bool):
        return False

    def cleanup(self):
        logger.debug('Cleaning up toolframe ' + self.gladefile)
        self._disconnect_device_connections()
        for c in self._accounting_connections:
            self.instrument.services['accounting'].disconnect(c)
        self._accounting_connections = []
        super().cleanup()

    def show_all(self):
        self.widget.show_all()
        self.widget.foreach(lambda x: x.show_all())

    @classmethod
    def requirements_met(cls, instrument: Instrument) -> bool:
        """Check if all the required devices are working in the instrument.

        Note that this is implemented as a class method, thus the requirements can be
        checked before the class is instantiated.
        """
        for rd in cls.required_devices:
            try:
                dev = instrument.get_device(rd)
            except KeyError:
                return False
            assert isinstance(dev, (Device, Motor))
            if not dev.get_connected():
                return False
        return True
