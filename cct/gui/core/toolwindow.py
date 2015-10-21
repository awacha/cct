from gi.repository import Gtk
import pkg_resources
import weakref

class ToolWindow(object):
    def __init__(self, gladefile, toplevelname, instrument, application):
        self._builder=Gtk.Builder.new_from_file(pkg_resources.resource_filename('cct','resource/glade/%s'%gladefile))
        self._builder.set_application(application)
        try:
            self._instrument=weakref.proxy(instrument)
        except TypeError:
            # instrument is already a weakref
            self._instrument=instrument
        self._inhibit_close_reason=None
        self._init_gui()
        self._builder.connect_signals(self)
        self._window=self._builder.get_object(toplevelname)
        self._window.connect('delete-event', self.on_window_delete)
        self._window.show_all()

    def on_window_delete(self, window):
        if not self.can_close():
            md=Gtk.MessageDialog(parent=self._window, flags=Gtk.DialogFlags.MODAL, type=Gtk.MessageType.INFO,
                                 buttons=Gtk.ButtonsType.OK, message_format='Cannot close this window')
            md.format_secondary_text('Reason: '+self._inhibit_close_reason)
            md.run()
            return True
        self._window.hide()
        return True

    def _init_gui(self):
        """this can be used to do some fine-tuning on the gui before connecting signals"""
        pass

    def inhibit_close(self, reason):
        self._inhibit_close_reason=reason

    def permit_close(self):
        self._inhibit_close_reason=None

    def can_close(self):
        return self._inhibit_close_reason is None

    def on_close(self, widget):
        return self.on_window_delete(self._window)
