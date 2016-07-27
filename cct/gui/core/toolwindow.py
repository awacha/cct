import logging
from typing import List, Optional

from gi.repository import Gtk

from .dialogs import error_message
from .toolframe import ToolFrame

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ToolWindow(ToolFrame):
    destroy_on_close = False

    def __init__(self, gladefile, toplevelname, instrument, windowtitle, *args, **kwargs):
        super().__init__(gladefile, toplevelname, instrument, *args, **kwargs)
        assert isinstance(self.widget, Gtk.Window)
        self._mainwidget_connections.append(self.widget.connect('delete-event', self.on_window_delete))
        self.widget.set_title(windowtitle)
        self._inhibit_close_reason=None

    def set_sensitive(self, state: bool, reason: Optional[str] = None, additional_widgets: Optional[List] = None):
        if state:
            self.permit_close()
        elif reason is not None:
            self.inhibit_close(reason)
        return super().set_sensitive(state, reason, additional_widgets)

    def on_window_delete(self, window, event):
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
        self._inhibit_close_reason=reason
        self.widget.set_deletable(False)

    def permit_close(self):
        self._inhibit_close_reason=None
        self.widget.set_deletable(True)

    def can_close(self):
        return self._inhibit_close_reason is None

    def on_close(self, widget, event=None):
        #callback for the close button
        if self.destroy_on_close:
            super().on_close(widget, event)
        return self.on_window_delete(self.widget, event=None)
