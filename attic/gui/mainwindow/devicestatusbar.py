from gi.repository import Gtk


class DeviceStatusBar(Gtk.Box):
    def __init__(self, instrument):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self._instrument = instrument
        self._statuslabels = {}
        self._connections = {}
        self._status = {}
        self._auxstatus = {}
        for device in sorted(self._instrument.devices):
            dev = self._instrument.get_device(device)
            frame = Gtk.Frame(label=device)
            self._status[dev] = dev.get_variable('_status')
            try:
                self._auxstatus[dev] = dev.get_variable('_auxstatus')
            except KeyError:
                self._auxstatus[dev] = None
            self._statuslabels[device] = Gtk.Label(label=self.get_labeltext(dev))
            frame.add(self._statuslabels[device])
            self.pack_start(frame, True, True, 0)
            self._connections[dev] = dev.connect('variable-change', self.on_variable_change, device)

    def get_labeltext(self, device):
        if (device not in self._auxstatus) or (self._auxstatus[device] is None):
            return str(self._status[device])
        else:
            return '{} ({})'.format(self._status[device], self._auxstatus[device])

    def do_destroy(self):
        try:
            for d in self._connections:
                d.disconnect(self._connections[d])
        finally:
            self._connections = {}

    def on_variable_change(self, device, variablename, newvalue, devicename):
        if variablename == '_status':
            self._status[device] = newvalue
            self._statuslabels[devicename].set_text(self.get_labeltext(device))
        elif variablename == '_auxstatus':
            self._auxstatus[device] = newvalue
            self._statuslabels[devicename].set_text(self.get_labeltext(device))
        return False
