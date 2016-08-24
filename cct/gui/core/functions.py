from typing import List

import pkg_resources
from gi.repository import Gtk, Notify, GdkPixbuf


def update_comboboxtext_choices(cb: Gtk.ComboBoxText, choices: List[str], default=None, set_to=None):
    """Update the choices of the combo box while keeping the current selection,
    if possible."""
    prevselected = cb.get_active_text()
    if set_to is not None:
        prevselected = set_to
    cb.remove_all()
    defaultindex = None
    for i, k in enumerate(choices):
        cb.append_text(k)
        if k == prevselected:
            cb.set_active(i)
        if k == default:
            defaultindex = i
    if defaultindex is None:
        defaultindex = 0
    if cb.get_active_text() is None:
        cb.set_active(defaultindex)


def notify(summary: str, body: str):
    """Issue a desktop notification"""
    n = Notify.Notification(summary=summary,
                            body=body)
    n.set_image_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(
        pkg_resources.resource_filename('cct', 'resource/icons/scalable/cctlogo.svg'), 256, 256))
    n.show()
