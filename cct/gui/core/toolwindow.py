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

    def set_sensitive(self, state: bool, reason: Optional[str] = None, additional_widgets: Optional[List] = None):
        if state:
            self.permit_close()
        elif reason is not None:
            self.inhibit_close(reason)
        return super().set_sensitive(state, reason, additional_widgets)

    def on_window_delete(self, window: Gtk.Window, event: Optional[Gdk.Event]):
        if not self.can_close():
            error_message(self.widget, 'Cannot close this window',
                          self._inhibit_close_reason)
            return True
        if self.destroy_on_close:
            # let the callback chain continue with the default handler, which
            # destroys the window.
            return False
        else:
            # hide the window and break the callback chain, thus the default
            # handler won't be executed and the window won't be deleted.
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
            interpreter.execute_command(commandclass, arguments)
        except Exception as exc:
            self.on_command_fail(interpreter, commandclass.name, exc, traceback.format_exc())
            self.on_command_return(interpreter, commandclass.name, None)
        else:
            if set_insensitive:
                self.set_sensitive(False, 'Command running', additional_widgets)
            else:
                self.inhibit_close('Command running')

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
