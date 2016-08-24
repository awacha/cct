import logging

from gi.repository import Gtk

from ..core.toolwindow import ToolWindow
from ...core.devices import Device
from ...core.instrument.privileges import PRIV_DEVICECONFIG, PRIV_CONNECTDEVICES

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class DeviceConnections(ToolWindow):
    privlevel = PRIV_CONNECTDEVICES

    def __init__(self, *args, **kwargs):
        self._device_connections = {}
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        dg = self.builder.get_object('devices_grid')
        assert (isinstance(dg, Gtk.Grid))
        for i, d in enumerate(sorted(self.instrument.devices)):
            l = Gtk.Label(d)
            dg.attach(l, 0, i + 1, 1, 1)
            l.set_hexpand_set(True)
            l.set_hexpand(False)
            l.set_vexpand_set(True)
            l.set_vexpand(False)
            self.builder.expose_object('connectbutton_' + d, Gtk.Button(label='N/A'))
            self.builder.get_object('connectbutton_' + d).connect('clicked', self.on_connectbutton_clicked, d)
            dg.attach(self.builder.get_object('connectbutton_' + d), 1, i + 1, 1, 1)
            self.builder.expose_object('editbutton_' + d,
                                       Gtk.Button.new_from_icon_name('preferences-system', Gtk.IconSize.BUTTON))
            self.builder.get_object('editbutton_' + d).set_label('Preferences')
            self.builder.get_object('editbutton_' + d).connect('clicked', self.on_editbutton_clicked, d)
            self.builder.get_object('editbutton_' + d).set_sensitive(False)
            dg.attach(self.builder.get_object('editbutton_' + d), 2, i + 1, 1, 1)
            self.builder.get_object('editbutton_' + d).set_sensitive(
                self.instrument.services['accounting'].get_privilegelevel() >= PRIV_DEVICECONFIG)
            logger.debug('Added device ' + d)
        logger.debug('Added all devices')

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self._device_connections = {}
        for d in self.instrument.devices:
            dev = self.instrument.get_device(d)
            if dev.get_variable('_status') == 'Disconnected':
                self.builder.get_object('connectbutton_' + d).set_label('Connect')
            else:
                self.builder.get_object('connectbutton_' + d).set_label('Disconnect')
            self._device_connections[d] = [dev.connect('disconnect', self.on_device_disconnect),
                                           dev.connect('variable-change', self.on_device_varchange),
                                           dev.connect('startupdone', self.on_device_startupdone)]
        return False

    def cleanup(self):
        for d in self._device_connections:
            dev = self.instrument.get_device(d)
            assert isinstance(dev, Device)
            for c in self._device_connections[d]:
                dev.disconnect(c)
        self._device_connections = {}
        super().cleanup()

    def on_connectbutton_clicked(self, connectbutton, devicename):
        if connectbutton.get_label() == 'Connect':
            connectbutton.set_sensitive(False)
            self.instrument.get_device(devicename).reconnect_device()
        elif connectbutton.get_label() == 'Disconnect':
            connectbutton.set_sensitive(False)
            self.instrument.get_device(devicename).disconnect_device()
        else:
            raise ValueError(connectbutton.get_label())
        return False

    def on_editbutton_clicked(self, editbutton, devicename):
        pass

    def on_device_disconnect(self, device: Device, abnormal_disconnect: bool):
        self.builder.get_object('connectbutton_' + device.name).set_label('Connect')
        self.builder.get_object('connectbutton_' + device.name).set_sensitive(True)
        return False

    def on_device_startupdone(self, device: Device):
        self.builder.get_object('connectbutton_' + device.name).set_label('Disconnect')
        self.builder.get_object('connectbutton_' + device.name).set_sensitive(True)
        return False

    def on_device_varchange(self, device: Device, varname: str, varvalue: object, ):
        if varname != '_status':
            return False
        if varvalue == 'Disconnected':
            self.builder.get_object('connectbutton_' + device.name).set_label('Connect')
            self.builder.get_object('connectbutton_' + device.name).set_sensitive(True)
        else:
            self.builder.get_object('connectbutton_' + device.name).set_label('Disconnect')
        return False

    def on_privlevel_changed(self, accounting, newprivlevel):
        for d in self.instrument.devices:
            self.builder.get_object('editbutton_' + d).set_sensitive(newprivlevel >= PRIV_DEVICECONFIG)
        return super().on_privlevel_changed(accounting, newprivlevel)
