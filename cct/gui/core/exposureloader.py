import logging
import weakref

import pkg_resources
from gi.repository import GObject, GLib, Gtk

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ExposureLoader():  # Gtk.Box):
    __gsignals__ = {'open': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'map': 'override',
                    'unmap': 'override'}

    def __init__(self, instrument):
        super().__init__()
        if not isinstance(instrument, weakref.ProxyTypes):
            instrument = weakref.proxy(instrument)
        self.instrument = instrument
        self.builder = Gtk.Builder.new_from_file(
            pkg_resources.resource_filename('cct', 'resource/glade/core_exposureloader.glade'))
        assert isinstance(self.builder, Gtk.Builder)
        self.widget = self.builder.get_object('box')
        self.pack_start(self.widget, True, True, 0)
        self.builder.connect_signals(self)
        self.on_override_mask_changed(self.builder.get_object('maskoverride_check'))
        self.on_prefix_changed(self.builder.get_object('prefix_selector'))
        self.show_all()

    def on_override_mask_changed(self, checkbutton: Gtk.CheckButton):
        self.builder.get_object('mask_chooser').set_sensitive(checkbutton.get_active())
        return True

    def on_prefix_changed(self, prefixselector: Gtk.ComboBoxText):
        try:
            self.builder.get_object('fsn_adjustment').set_upper(
                self.instrument.services['filesequence'].get_lastfsn(prefixselector.get_active_text()))
        except KeyError:
            pass

    def do_map(self):
        Gtk.Box.do_map(self)
        ps = self.builder.get_object('prefix_selector')
        previous_active = ps.get_active_text()
        ps.remove_all()
        for i, p in enumerate(sorted(self.instrument.services['filesequence'].get_prefixes())):
            ps.append_text(p)
            if p == previous_active:
                ps.set_active(i)
        if ps.get_active_text() is None:
            ps.set_active(0)
        self.cleanup()
        self._lastfsnchangedconnection = self.instrument.services['filesequence'].connect('lastfsn-changed',
                                                                                          self.on_lastfsn_changed)
        return True

    def cleanup(self):
        try:
            self.instrument.services['filesequence'].disconnect(self._lastfsnchangedconnection)
            del self._lastfsnchangedconnection
        except AttributeError:
            pass

    def do_unmap(self):
        Gtk.Box.do_unmap(self)
        self.cleanup()
        return True

    def on_lastfsn_changed(self, filesequence, prefix, lastfsn):
        if prefix == self.builder.get_object('prefix_selector').get_active_text():
            self.builder.get_object('fsn_adjustment').set_upper(lastfsn)
        return False

    def on_load(self, button: Gtk.Button):
        GLib.idle_add(self._do_load)

    def _do_load(self):
        prefix = self.builder.get_object('prefix_selector').get_active_text()
        fsn = self.builder.get_object('fsn_spin').get_value_as_int()
        im = self.instrument.services['filesequence'].load_exposure(prefix, fsn)
        if self.builder.get_object('maskoverride_check').get_active():
            im.mask = self.instrument.services['filesequence'].get_mask(
                self.builder.get_object('mask_chooser').get_filename())
        self.emit('open', im)
        return False # inhibit calling us once again as an idle function
