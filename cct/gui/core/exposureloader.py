import logging

import pkg_resources
from gi.repository import GObject
from gi.repository import Gtk

from ...core.utils.pathutils import find_in_subfolders
from ...core.utils.sasimage import SASImage

logger = logging.getLogger(__name__)
logger.setlevel(logging.INFO)


class ExposureLoader(Gtk.Box):
    __gsignals__ = {'open': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'map': 'override',
                    'unmap': 'override'}

    def __init__(self, instrument):
        Gtk.Box.__init__(self)
        self._instrument = instrument
        self._builder = Gtk.Builder.new_from_file(
            pkg_resources.resource_filename('cct', 'resource/glade/core_exposureloader.glade'))
        self._widget = self._builder.get_object('box')
        self.pack_start(self._widget, True, True, 0)
        self._builder.connect_signals(self)
        prefixselector = self._builder.get_object('prefix_selector')
        prefixselector.remove_all()
        for prefix in sorted(self._instrument.filesequence.get_prefixes()):
            prefixselector.append_text(prefix)
        prefixselector.set_active(0)
        self.on_override_mask_changed(self._builder.get_object('maskoverride_check'))
        self.on_prefix_changed(self._builder.get_object('prefix_selector'))
        self.show_all()

    def on_override_mask_changed(self, checkbutton):
        self._builder.get_object('mask_chooser').set_sensitive(checkbutton.get_active())
        return True

    def on_prefix_changed(self, prefixselector):
        try:
            self._builder.get_object('fsn_adjustment').set_upper(
                self._instrument.filesequence.get_lastfsn(prefixselector.get_active_text()))
        except KeyError:
            pass

    def do_map(self):
        Gtk.Box.do_map(self)
        ps = self._builder.get_object('prefix_selector')
        previous_active = ps.get_active_text()
        ps.remove_all()
        for i, p in enumerate(sorted(self._instrument.filesequence.get_prefixes())):
            ps.append_text(p)
            if p == previous_active:
                ps.set_active(i)
        if ps.get_active_text() is None:
            ps.set_active(0)
        self._cleanup_instrumentconnections()
        self._lastfsnchangedconnection = self._instrument.filesequence.connect('lastfsn-changed',
                                                                               self.on_lastfsn_changed)
        return True

    def _cleanup_instrumentconnections(self):
        try:
            self._instrument.filesequence.disconnect(self._lastfsnchangedconnection)
            del self._lastfsnchangedconnection
        except AttributeError:
            pass

    def do_unmap(self):
        Gtk.Box.do_unmap(self)
        self._cleanup_instrumentconnections()
        return True

    def on_lastfsn_changed(self, filesequence, prefix, lastfsn):
        if prefix == self._builder.get_object('prefix_selector').get_active_text():
            self._builder.get_object('fsn_adjustment').set_upper(lastfsn)
        return False

    def on_load(self, button):
        prefix = self._builder.get_object('prefix_selector').get_active_text()
        fsn = self._builder.get_object('fsn_spin').get_value_as_int()
        fsndigits = self._instrument.config['path']['fsndigits']
        imgdir = self._instrument.config['path']['directories']['images']
        pickledir = self._instrument.config['path']['directories']['param']
        basename = prefix + '_' + '%%0%dd' % fsndigits % fsn
        twodname = find_in_subfolders(imgdir, basename + '.cbf')
        picklename = find_in_subfolders(pickledir, basename + '.pickle')
        im = SASImage.new_from_file(twodname, picklename)
        if self._builder.get_object('maskoverride_check').get_active():
            im._mask = self._instrument.filesequence.get_mask(self._builder.get_object('mask_chooser').get_filename())
        self.emit('open', im)
