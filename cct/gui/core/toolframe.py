import weakref

import pkg_resources
from gi.repository import Gtk, GObject


class ToolFrame(GObject.GObject):
    def __init__(self, gladefile, widgetname, instrument, application, *args):
        GObject.GObject.__init__(self)
        self._widgetname = widgetname
        self._application = application
        self._builder = Gtk.Builder.new_from_file(
            pkg_resources.resource_filename('cct', 'resource/glade/%s' % gladefile))
        self._builder.set_application(application)
        try:
            self._instrument = weakref.proxy(instrument)
        except TypeError:
            # instrument is already a weakref
            self._instrument = instrument
        self._inhibit_close_reason = None
        self._widget = self._builder.get_object(widgetname)
        self._widget.connect('map', self.on_map)
        self._widget.connect('unmap', self.on_unmap)
        self._init_gui(*args)
        self._builder.connect_signals(self)
        self._widget.show_all()

    def on_map(self, widget):
        pass

    def on_unmap(self, widget):
        pass

    def _init_gui(self, *args):
        pass
