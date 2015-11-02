from gi.repository import Gtk
import pkg_resources
cssprovider=Gtk.CssProvider()
cssprovider.load_from_path(pkg_resources.resource_filename('cct','resource/css/indicatorcolors.css'))

class IndicatorState:
    OK='ok'
    WARNING='warning'
    ERROR='error'
    NEUTRAL='neutral'
    UNKNOWN='unknown'

class Indicator(Gtk.Box):
    def __init__(self, label, value, state, *args, **kwargs):
        Gtk.Box.__init__(self, *args, **kwargs)
        if 'orientation' not in kwargs:
            self.set_orientation(Gtk.Orientation.VERTICAL)
        self._label=Gtk.Label(label=label)
        self.pack_start(self._label, True, True, 0)
        self._eventbox=Gtk.EventBox()
        self.pack_start(self._eventbox, True, True, 0)
        self._valuelabel=Gtk.Label(label=str(value))
        self._value=value
        self._eventbox.add(self._valuelabel)
        self._eventbox.set_border_width(5)
        self._eventbox.set_name('indicator_'+state)
        self._eventbox.get_style_context().add_provider(cssprovider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.set_hexpand(True)
        self.set_hexpand_set(True)
#        self._eventbox.queue_draw()

    def set_label(self, text):
        return self._label.set_text(text)

    def get_label(self):
        return self._label.get_text()

    def set_value(self, value, state=None):
        self._value=value
        res= self._valuelabel.set_text(str(value))
        if state is not None:
            self.set_state(state)
        return res

    def get_value(self):
        return self._value

    def set_state(self, state):
        res=self._eventbox.set_name('indicator_'+state)
        self._eventbox.queue_draw()
        return res

    def get_state(self):
        return self._eventbox.get_name().split('_',1)[-1]
