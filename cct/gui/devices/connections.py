import logging

from gi.repository import Gtk

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from ..core.toolwindow import ToolWindow
from ...core.instrument.privileges import PRIV_DEVICECONFIG, PRIV_CONNECTDEVICES


class DeviceConnections(ToolWindow):
    def _init_gui(self, *args):
        self._privlevel = PRIV_CONNECTDEVICES
        print('Initializing gui')
        logger.debug('Initializing gui')
        dg = self._builder.get_object('devices_grid')
        assert (isinstance(self._builder, Gtk.Builder))
        assert (isinstance(dg, Gtk.Grid))
        for i, d in enumerate(sorted(self._instrument.devices)):
            l = Gtk.Label(d)
            dg.attach(l, 0, i + 1, 1, 1)
            l.set_hexpand_set(True)
            l.set_hexpand(False)
            l.set_vexpand_set(True)
            l.set_vexpand(False)
            if self._instrument.devices[d].get_variable('_status') == 'Disconnected':
                label = 'Connect'
            else:
                label = 'Disconnect'
            self._builder.expose_object('connectbutton_' + d, Gtk.Button(label=label))
            self._builder.get_object('connectbutton_' + d).connect('clicked', self.on_connectbutton_clicked, d)
            dg.attach(self._builder.get_object('connectbutton_' + d), 1, i + 1, 1, 1)
            self._builder.expose_object('editbutton_' + d,
                                        Gtk.Button.new_from_icon_name('preferences-system', Gtk.IconSize.BUTTON))
            self._builder.get_object('editbutton_' + d).set_label('Preferences')
            self._builder.get_object('editbutton_' + d).connect('clicked', self.on_editbutton_clicked, d)
            self._builder.get_object('editbutton_' + d).set_sensitive(False)
            dg.attach(self._builder.get_object('editbutton_' + d), 2, i + 1, 1, 1)
            self._instrument.devices[d].connect('disconnect', self.on_device_disconnect, d)
            self._instrument.devices[d].connect('variable-change', self.on_device_varchange, d)
            self._instrument.devices[d].connect('startupdone', self.on_device_startupdone, d)
            self._builder.get_object('editbutton_' + d).set_sensitive(
                self._instrument.accounting.get_privilegelevel() >= PRIV_DEVICECONFIG)
            logger.debug('Added device ' + d)
        logger.debug('Added all devices')

    def on_connectbutton_clicked(self, connectbutton, devicename):
        if connectbutton.get_label() == 'Connect':
            connectbutton.set_sensitive(False)
            self._instrument.devices[devicename].reconnect_device()
        elif connectbutton.get_label() == 'Disconnect':
            connectbutton.set_sensitive(False)
            self._instrument.devices[devicename].disconnect_device()
        else:
            raise ValueError(connectbutton.get_label())
        return False

    def on_editbutton_clicked(self, editbutton, devicename):
        pass

    def on_device_disconnect(self, device, abnormal_disconnect, devicename):
        self._builder.get_object('connectbutton_' + devicename).set_label('Connect')
        self._builder.get_object('connectbutton_' + devicename).set_sensitive(True)
        return False

    def on_device_startupdone(self, device, devicename):
        self._builder.get_object('connectbutton_' + devicename).set_label('Disconnect')
        self._builder.get_object('connectbutton_' + devicename).set_sensitive(True)
        return False

    def on_device_varchange(self, device, varname, varvalue, devicename):
        if varname != '_status':
            return False
        if varvalue == 'Disconnected':
            self._builder.get_object('connectbutton_' + devicename).set_label('Connect')
            self._builder.get_object('connectbutton_' + devicename).set_sensitive(True)
        else:
            self._builder.get_object('connectbutton_' + devicename).set_label('Disconnect')
        return False

    def on_privlevel_changed(self, accounting, newprivlevel):
        for d in self._instrument.devices:
            self._builder.get_object('editbutton_' + d).set_sensitive(newprivlevel >= PRIV_DEVICECONFIG)
        return super().on_privlevel_changed(accounting, newprivlevel)
