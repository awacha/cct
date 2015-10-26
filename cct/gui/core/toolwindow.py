from gi.repository import Gtk
import pkg_resources
import weakref
import logging
logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def error_message(parentwindow, message, reason=None):
    md=Gtk.MessageDialog(parent=parentwindow, flags=Gtk.DialogFlags.MODAL, type=Gtk.MessageType.INFO,
                         buttons=Gtk.ButtonsType.OK, message_format=message)
    if reason is not None:
        md.format_secondary_text('Reason: '+reason)
    result=md.run()
    md.destroy()
    return result

def question_message(parentwindow, question, detail=None):
    md=Gtk.MessageDialog(parent=parentwindow, flags=Gtk.DialogFlags.MODAL, type=Gtk.MessageType.QUESTION,
                         buttons=Gtk.ButtonsType.YES_NO, message_format=question)
    if detail is not None:
        md.format_secondary_text('Reason: '+detail)
    result=md.run()
    md.destroy()
    return result==Gtk.ResponseType.YES


class ToolWindow(object):
    def __init__(self, gladefile, toplevelname, instrument, application, *args):
        self._toplevelname=toplevelname
        self._hide_on_close=True
        self._application=application
        self._builder=Gtk.Builder.new_from_file(pkg_resources.resource_filename('cct','resource/glade/%s'%gladefile))
        self._builder.set_application(application)
        try:
            self._instrument=weakref.proxy(instrument)
        except TypeError:
            # instrument is already a weakref
            self._instrument=instrument
        self._inhibit_close_reason=None
        self._window=self._builder.get_object(toplevelname)
        self._window.connect('delete-event', self.on_window_delete)
        self._window.connect('map', self.on_map)
        self._window.connect('unmap', self.on_unmap)
        self._widgets_insensitive=[]
        self._init_gui(*args)
        self._builder.connect_signals(self)
        self._window.show_all()

    def on_window_delete(self, window, event):
        logger.debug('On_window_delete for %s'%self._toplevelname)
        if not self.can_close():
            error_message(self._window, 'Cannot close this window', self._inhibit_close_reason)
            return True
        if self._hide_on_close:
            logger.debug('Hiding %s toolwindow'%self._toplevelname)
            self._window.hide()
            return True
        else:
            logger.debug('Not hiding %s toolwindow: letting it be destroyed.'%self._toplevelname)
            return False

    def _init_gui(self, *args):
        """this can be used to do some fine-tuning on the gui before connecting signals"""
        pass

    def inhibit_close(self, reason):
        self._inhibit_close_reason=reason

    def permit_close(self):
        self._inhibit_close_reason=None

    def can_close(self):
        return self._inhibit_close_reason is None

    def on_close(self, widget, event=None):
        #callback for the close button
        if not self._hide_on_close:
            logger.debug('on_close called for toolwindow %s: requesting destroy'%self._toplevelname)
            self._window.destroy()
        return self.on_window_delete(self._window, event=None)

    def _make_insensitive(self, reason, widgets=[]):
        self.inhibit_close(reason)
        for w in widgets:
            self._builder.get_object(w).set_sensitive(False)
            self._widgets_insensitive.append(w)
        self._window.set_deletable(False)

    def _make_sensitive(self):
        self.permit_close()
        for w in self._widgets_insensitive:
            self._builder.get_object(w).set_sensitive(True)
        self._widgets_insensitive=[]
        self._window.set_deletable(True)

    def on_unmap(self, window):
        """This function should disconnect all the signal handlers from devices. Hidden windows do not need updating."""
        return False

    def on_map(self, window):
        """This function should connect all signal handlers to devices, as well as do an update to the GUI."""
        return True