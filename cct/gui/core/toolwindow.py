import logging
import weakref

import pkg_resources
from gi.repository import Gtk, GObject

from ...core.instrument.privileges import PRIV_LAYMAN

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def error_message(parentwindow, message, reason=None):
    md=Gtk.MessageDialog(parent=parentwindow, flags=Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT|Gtk.DialogFlags.USE_HEADER_BAR, type=Gtk.MessageType.INFO,
                         buttons=Gtk.ButtonsType.OK, message_format=message)
    if reason is not None:
        md.format_secondary_text('Reason: '+reason)
    result=md.run()
    md.destroy()
    return result

def question_message(parentwindow, question, detail=None):
    md=Gtk.MessageDialog(parent=parentwindow, flags=Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT|Gtk.DialogFlags.USE_HEADER_BAR, type=Gtk.MessageType.QUESTION,
                         buttons=Gtk.ButtonsType.YES_NO, message_format=question)
    if detail is not None:
        md.format_secondary_text(detail)
    result=md.run()
    md.destroy()
    return result==Gtk.ResponseType.YES

def info_message(parentwindow, info, detail=None):
    md=Gtk.MessageDialog(parent=parentwindow, flags=Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT|Gtk.DialogFlags.USE_HEADER_BAR, type=Gtk.MessageType.INFO,
                         buttons=Gtk.ButtonsType.OK, message_format=info)
    if detail is not None:
        md.format_secondary_text(detail)
    result=md.run()
    md.destroy()
    return result


class ToolWindow(GObject.GObject):
    def __init__(self, gladefile, toplevelname, instrument, application, windowtitle, *args):
        GObject.GObject.__init__(self)
        self._toplevelname=toplevelname
        self._hide_on_close=True
        self._privlevel = PRIV_LAYMAN
        self._application=application
        self._builder = Gtk.Builder.new_from_file(pkg_resources.resource_filename('cct', 'resource/glade/' + gladefile))
        assert (self._builder, Gtk.Builder)
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
        self._window.set_title(windowtitle)
        self._widgets_insensitive=[]
        try:
            self._init_gui(*args)
        except Exception as exc:
            error_message(self._window, 'Cannot initialize window ' + windowtitle, str(exc))
            raise
        self._builder.connect_signals(self)
        self._window.foreach(lambda x: x.show_all())
        self._instrument.accounting.connect('privlevel-changed', self.on_privlevel_changed)

    def on_privlevel_changed(self, accounting, newprivlevel):
        if not self._instrument.accounting.has_privilege(self._privlevel):
            if self._inhibit_close_reason is not None:
                # we cannot close, make us insensitive then
                self._window.set_sensitive(False)
            else:
                self.on_window_delete(self._window, None)
        else:
            if not self._window.get_sensitive():
                self._window.set_sensitive(True)

    def on_window_delete(self, window, event):
        logger.debug('On_window_delete for ' + self._toplevelname)
        if not self.can_close():
            error_message(self._window, 'Cannot close this window', self._inhibit_close_reason)
            return True
        if self._hide_on_close:
            logger.debug('Hiding {} toolwindow'.format(self._toplevelname))
            self._window.hide()
            return True
        else:
            logger.debug('Not hiding {} toolwindow: letting it be destroyed.'.format(self._toplevelname))
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
            logger.debug('on_close called for toolwindow {}: requesting destroy'.format(self._toplevelname))
            self._window.destroy()
        return self.on_window_delete(self._window, event=None)

    def _make_insensitive(self, reason, widgets=[], otherwidgets=[]):
        self.inhibit_close(reason)
        for w in widgets:
            widget = self._builder.get_object(w)
            widget.set_sensitive(False)
            self._widgets_insensitive.append(widget)
        for w in otherwidgets:
            w.set_sensitive(False)
            self._widgets_insensitive.append(w)
        self._window.set_deletable(False)

    def _make_sensitive(self):
        self.permit_close()
        for w in self._widgets_insensitive:
            w.set_sensitive(True)
        self._widgets_insensitive=[]
        self._window.set_deletable(True)

    def on_unmap(self, window):
        """This function should disconnect all the signal handlers from devices. Hidden windows do not need updating."""
        return False

    def on_map(self, window):
        """This function should connect all signal handlers to devices, as well as do an update to the GUI."""
        if not self._instrument.accounting.has_privilege(self._privlevel):
            error_message(self._window, 'Insufficient privilege level to open this tool')
            self._window.hide()
            return True
        else:
            return False
