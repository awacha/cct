import logging
import traceback
from typing import List, Optional

from gi.repository import Gtk, Gdk

from .dialogs import error_message
from .toolframe import ToolFrame
from ...core.commands import Command
from ...core.services.interpreter import Interpreter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ToolWindow(ToolFrame):
    destroy_on_close = False

    def __init__(self, gladefile, toplevelname, instrument, windowtitle, *args, **kwargs):
        super().__init__(gladefile, toplevelname, instrument, *args, **kwargs)
        assert isinstance(self.widget, Gtk.Window)
        self._mainwidget_connections.append(self.widget.connect('delete-event', self.on_window_delete))
        self.widget.set_title(windowtitle)
        self._inhibit_close_reason = None
        self._interpreter_connections = []
        self.command_failed = False
        w = self.widget.get_child()
        self.widget.remove(w)
        self.__box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.widget.add(self.__box)
        self.infobar = Gtk.InfoBar()
        self.__box.pack_end(w, True, True, 0)
        self.__box.pack_end(self.infobar, False, False, 0)
        self.infobar.set_no_show_all(True)
        self.infobar.set_show_close_button(True)
        self.infolabel = Gtk.Label()
        self.infoimage = Gtk.Image()
        self.infobar.get_content_area().pack_start(self.infoimage, False, True, 0)
        self.infobar.get_content_area().pack_start(self.infolabel, True, True, 0)
        self.infolabel.set_halign(Gtk.Align.START)
        self.infolabel.set_hexpand(True)
        self.infolabel.set_hexpand_set(True)
        self._infobar_connection = self.infobar.connect('response', self.on_infobar_response)
        self.infobar.foreach(lambda w_: w_.show_all())
        # self.widget.set_has_resize_grip(True)

    def cleanup(self):
        if self._infobar_connection is not None:
            self.infobar.disconnect(self._infobar_connection)
        self._infobar_connection = None
        super().cleanup()

    def on_infobar_response(self, infobar: Gtk.InfoBar, response=Gtk.ResponseType):
        self.infolabel.set_label('')
        self.infoimage.set_from_icon_name('image-missing', Gtk.IconSize.DIALOG)
        infobar.hide()
        assert isinstance(self.widget, Gtk.Window)
        self.widget.resize(1, 1)  # shrink the window back.
        return False

    def error_message(self, message: str):
        return self.infobar_message(Gtk.MessageType.ERROR, message)

    def info_message(self, message: str):
        return self.infobar_message(Gtk.MessageType.INFO, message)

    def warning_message(self, message: str):
        return self.infobar_message(Gtk.MessageType.WARNING, message)

    def infobar_message(self, messagetype: Gtk.MessageType, message: str):
        if self.infobar.get_visible() and self.infobar.get_message_type() == messagetype:
            # if it is already visible and has the same message type, append the new message to the previous one
            self.infolabel.set_label(self.infolabel.get_label() + '\n' + message)
        else:
            self.infolabel.set_label(message)
            self.infobar.set_message_type(messagetype)
            if messagetype == Gtk.MessageType.ERROR:
                self.infoimage.set_from_icon_name('dialog-error', Gtk.IconSize.DIALOG)
            elif messagetype == Gtk.MessageType.WARNING:
                self.infoimage.set_from_icon_name('dialog-warning', Gtk.IconSize.DIALOG)
            elif messagetype == Gtk.MessageType.INFO:
                self.infoimage.set_from_icon_name('dialog-information', Gtk.IconSize.DIALOG)
            else:
                self.infoimage.set_from_icon_name('image-missing', Gtk.IconSize.DIALOG)
            # workaround bug https://bugzilla.gnome.org/show_bug.cgi?id=710888
            self.__box.remove(self.infobar)
            self.__box.pack_end(self.infobar, False, True, 0)

            self.infobar.show()

    def set_sensitive(self, state: bool, reason: Optional[str] = None, additional_widgets: Optional[List] = None):
        if state:
            self.permit_close()
        elif reason is not None:
            self.inhibit_close(reason)
        return super().set_sensitive(state, reason, additional_widgets)

    def on_mainwidget_unmap(self, widget: Gtk.Widget):
        self.on_infobar_response(self.infobar, Gtk.ResponseType.CLOSE)
        super().on_mainwidget_unmap(widget)

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            # something did not succeed.
            logger.warning('Error happened while mapping toolwindow ' + self.gladefile)
            self.widget.destroy()
            #            self.widget.get_toplevel().destroy()
            return True
        logger.debug('Successfully mapped ToolWindow ' + self.gladefile)
        return False

    def on_window_delete(self, window: Gtk.Window, event: Optional[Gdk.Event]):
        logger.debug('Deleting toolwindow ' + self.gladefile)
        if not self.can_close():
            self.error_message('Cannot close this window: ' + self._inhibit_close_reason)
            return True
        if self.destroy_on_close:
            # let the callback chain continue with the default handler, which
            # destroys the window.
            return False
        else:
            # hide the window and break the callback chain, thus the default
            # handler won't be executed and the window won't be deleted.
            logger.debug('Hiding toolwindow ' + self.gladefile)
            self.widget.hide()
            return True

    def inhibit_close(self, reason):
        self._inhibit_close_reason = reason
        self.widget.set_deletable(False)
        cb = self.builder.get_object('close_button')
        if cb is not None:
            cb.set_sensitive(False)

    def permit_close(self):
        self._inhibit_close_reason = None
        self.widget.set_deletable(True)
        cb = self.builder.get_object('close_button')
        if cb is not None:
            cb.set_sensitive(True)

    def can_close(self):
        return self._inhibit_close_reason is None

    def on_close(self, widget, event=None):
        # callback for the close button
        if self.destroy_on_close:
            super().on_close(widget, event)
        return self.on_window_delete(self.widget, event=None)

    def execute_command(self, commandclass, arguments, set_insensitive=True, additional_widgets=None):
        logger.debug('Executing command: {}'.format(str(commandclass)))
        assert issubclass(commandclass, Command)
        interpreter = self.instrument.services['interpreter']
        if interpreter.is_busy():
            raise RuntimeError('Interpreter is busy, cannot start command.')
        self._interpreter_connections = [interpreter.connect('cmd-return', self.on_command_return),
                                         interpreter.connect('cmd-fail', self.on_command_fail),
                                         interpreter.connect('cmd-detail', self.on_command_detail),
                                         interpreter.connect('pulse', self.on_command_pulse),
                                         interpreter.connect('progress', self.on_command_progress),
                                         interpreter.connect('cmd-message', self.on_command_message),
                                         interpreter.connect('flag', self.on_interpreter_flag),
                                         ]
        try:
            cmd = interpreter.execute_command(commandclass, arguments)
        except Exception as exc:
            self.error_message('Command {} failed: {}'.format(str(commandclass), traceback.format_exc()))
            self.on_command_fail(interpreter, commandclass.name, exc, traceback.format_exc())
            self.on_command_return(interpreter, commandclass.name, None)
            return None
        else:
            if set_insensitive:
                self.set_sensitive(False, 'Command running', additional_widgets)
            else:
                self.inhibit_close('Command running')
            return cmd

    def on_command_return(self, interpreter: Interpreter, commandname: str, returnvalue):
        for c in self._interpreter_connections:
            interpreter.disconnect(c)
        self._interpreter_connections = []
        self.set_sensitive(True)
        return False

    def on_command_fail(self, interpreter: Interpreter, commandname: str, exception, formatted_traceback):
        error_message(self.widget, 'Error executing command "{}"'.format(commandname), formatted_traceback)
        self.command_failed = True
        return False

    # noinspection PyMethodMayBeStatic
    def on_command_detail(self, interpreter: Interpreter, commandname: str, detail):
        return False

    def on_command_pulse(self, interpreter: Interpreter, commandname: str, message: str):
        return False

    def on_command_progress(self, interpreter: Interpreter, commandname: str, message: str, fraction: float):
        return False

    def on_command_message(self, interpreter: Interpreter, commandname: str, message: str):
        return False

    def on_interpreter_flag(self, interpreter: Interpreter, flag: str, state: bool):
        return False

    def on_copy_screenshot(self, button: Gtk.Button):
        pb = self.get_screenshot()
        cb = Gtk.Clipboard.get_default(Gdk.Display.get_default())
        assert isinstance(cb, Gtk.Clipboard)
        cb.set_image(pb)
        self.info_message('A hardcopy of this window has been put on the clipboard.')
        return False
