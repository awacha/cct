from gi.repository import Gtk
from ..core.toolwindow import ToolWindow, info_message

class SampleList(ToolWindow):
    def _init_gui(self):
        pass

    def on_new(self, button):
        pass

    def on_duplicate(self, button):
        pass

    def on_edit(self, button):
        pass

    def on_remove(self, button):
        pass

    def _repopulate_list(self):
        model=self._builder.get_object('samplestore')
        for s in self._instrument.samplestore:
            model.append((s.title,))

