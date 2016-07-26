from enum import Enum
from typing import Optional

import pkg_resources
from gi.repository import Gtk
from gi.repository import Pango

cssprovider=Gtk.CssProvider()
cssprovider.load_from_path(pkg_resources.resource_filename('cct','resource/css/indicatorcolors.css'))


class IndicatorState(Enum):
    OK='ok'
    WARNING='warning'
    ERROR='error'
    NEUTRAL='neutral'
    UNKNOWN='unknown'

class Indicator(Gtk.Box):
    def __init__(self, label: str, value: object, state: IndicatorState, *args, **kwargs):
        Gtk.Box.__init__(self, *args, **kwargs)
        if 'orientation' not in kwargs:
            self.set_orientation(Gtk.Orientation.VERTICAL)
        self._label=Gtk.Label(label=label)
        #        self._label.set_hexpand(True)
        #        self._label.set_hexpand_set(True)
        self.pack_start(self._label, True, True, 0)
        self._eventbox=Gtk.EventBox()
        self.pack_start(self._eventbox, True, True, 0)
        self._valuelabel=Gtk.Label(label=str(value))
        #      self._valuelabel.set_hexpand(False)
        #      self._valuelabel.set_hexpand_set(False)
        self._valuelabel.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self._valuelabel.set_max_width_chars(1)
        self._value=value
        self._eventbox.add(self._valuelabel)
        self._eventbox.set_border_width(5)
        self._eventbox.set_name('indicator_' + str(state))
        self._eventbox.get_style_context().add_provider(cssprovider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.set_hexpand(True)
        self.set_hexpand_set(True)
        self._eventbox.queue_draw()
        #       self.set_size_request(self._label.get_size_request()[0],-1)

    def set_label(self, text: str):
        return self._label.set_text(text)

    def get_label(self) -> str:
        return self._label.get_text()

    def set_value(self, value: object, state: Optional[IndicatorState] = None):
        self._value=value
        res= self._valuelabel.set_text(str(value))
        self._eventbox.set_tooltip_text(self._label.get_text() + ': ' + value)
        self._valuelabel.set_tooltip_text(self._label.get_text() + ': ' + value)
        if state is not None:
            self.set_state(state)
        return res

    def get_value(self):
        return self._value

    def set_state(self, state):
        res=self._eventbox.set_name('indicator_'+state)
        self._valuelabel.set_name('indicator_'+state)
        self._eventbox.queue_draw()
        self._valuelabel.queue_draw()
        return res

    def get_state(self):
        return IndicatorState(self._eventbox.get_name().split('_', 1)[-1])
