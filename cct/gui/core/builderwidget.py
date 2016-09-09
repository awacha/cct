import logging

from gi.repository import Gtk, Gdk, GdkPixbuf

from ...core.utils.callback import Callbacks, SignalFlags

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class BuilderWidget(Callbacks):
    __signals__ = {'destroy': (SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, gladefile: str, mainwidget: str):
        super().__init__()
        self.gladefile = gladefile
        self.builder = Gtk.Builder.new_from_file(gladefile)
        assert isinstance(self.builder, Gtk.Builder)
        self.builder.set_application(Gtk.Application.get_default())
        self.widget = self.builder.get_object(mainwidget)
        assert isinstance(self.widget, Gtk.Widget)
        self.builder.connect_signals(self)
        self._mainwidget_connections = [self.widget.connect('map', self.on_mainwidget_map),
                                        self.widget.connect('unmap', self.on_mainwidget_unmap),
                                        self.widget.connect('destroy', self.on_mainwidget_destroy)]

    def on_mainwidget_destroy(self, widget: Gtk.Widget):
        logger.debug('Destroying main widget: ' + self.gladefile)
        self.emit('destroy')
        logger.debug('Destroy signal emitted for BuilderWidget ' + self.gladefile)
        self.cleanup()
        return False

    def on_mainwidget_map(self, widget: Gtk.Widget):
        logger.debug('Mapping mainwidget for BuilderWidget ' + self.gladefile)
        self.widget.foreach(lambda x: x.show_all())
        return False

    # noinspection PyMethodMayBeStatic
    def on_mainwidget_unmap(self, widget: Gtk.Widget):
        logger.debug('Unmapping mainwidget for BuilderWidget ' + self.gladefile)
        return False

    def cleanup(self):
        for c in self._mainwidget_connections:
            self.widget.disconnect(c)
        self._mainwidget_connections = []
        try:
            self.widget = None
            self.builder = None
        except AttributeError:
            pass
        self.cleanup_callback_handlers()

    def __del__(self):
        logger.debug('Deleting a BuilderWidget.')

    def on_close(self, widget, event=None):
        self.widget.destroy()

    def get_screenshot(self) -> GdkPixbuf.Pixbuf:
        assert isinstance(self.widget, Gtk.Widget)
        gdkwin = self.widget.get_window()
        assert isinstance(gdkwin, Gdk.Window)
        return Gdk.pixbuf_get_from_window(gdkwin, 0, 0, gdkwin.get_width(), gdkwin.get_height())
