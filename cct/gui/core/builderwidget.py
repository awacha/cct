from gi.repository import Gtk

from ...core.utils.callback import Callbacks


class BuilderWidget(Callbacks):
    def __init__(self, gladefile: str, mainwidget: str):
        super().__init__()
        self.builder = Gtk.Builder.new_from_file(gladefile)
        assert isinstance(self.builder, Gtk.Builder)
        self.builder.set_application(Gtk.Application.get_default())
        self.widget = self.builder.get_object(mainwidget)
        assert isinstance(self.widget, Gtk.Widget)
        self.builder.connect_signals(self)
        self._mainwidget_connections = [self.widget.connect('map', self.on_mainwidget_map),
                                        self.widget.connect('unmap', self.on_mainwidget_unmap)]

    def on_mainwidget_map(self, widget: Gtk.Widget):
        self.widget.foreach(lambda x: x.show_all())
        return False

    # noinspection PyMethodMayBeStatic
    def on_mainwidget_unmap(self, widget: Gtk.Widget):
        return False

    def cleanup(self):
        for c in self._mainwidget_connections:
            self.widget.disconnect(c)
        self._mainwidget_connections = []
        try:
            self.widget.destroy()
            self.widget = None
            self.builder = None
        except AttributeError:
            pass

    def __del__(self):
        self.cleanup()

    def on_close(self, widget, event=None):
        self.cleanup()
        self.widget.destroy()
