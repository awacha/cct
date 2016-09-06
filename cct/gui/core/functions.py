import logging
from typing import List

import pkg_resources
from gi.repository import Gtk, Notify, GdkPixbuf, Gdk
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def update_comboboxtext_choices(cb: Gtk.ComboBoxText, choices: List[str], default=None, set_to=None):
    """Update the choices of the combo box while keeping the current selection,
    if possible."""
    logger.debug('Updating comboboxtext choices.')
    prevselected = cb.get_active_text()
    logger.debug('Previously selected: {}'.format(prevselected))
    if set_to is not None:
        logger.debug('Set_to is not None, but {}'.format(set_to))
        prevselected = set_to
    cb.remove_all()
    defaultindex = None
    logger.debug('Adding choices:')
    active_index = None
    for i, k in enumerate(choices):
        cb.append_text(k)
        if k == prevselected:
            active_index = i
        if k == default:
            defaultindex = i
        logger.debug(
            '  #{:d}: '.format(i) + k + ['', ' (active) '][active_index == i] + ['', ' (default) '][defaultindex == i])
    if defaultindex is None:
        defaultindex = 0
    if active_index is None:
        logger.debug('Setting to default, cannot activate original.')
        active_index = defaultindex
    cb.set_active(active_index)
    logger.debug('Activated index {:d}: {}'.format(active_index, cb.get_active_text()))


def notify(summary: str, body: str):
    """Issue a desktop notification"""
    n = Notify.Notification(summary=summary,
                            body=body)
    n.set_image_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(
        pkg_resources.resource_filename('cct', 'resource/icons/scalable/cctlogo.svg'), 256, 256))
    n.show()


def savefiguretoclipboard(figure: Figure):
    r = figure.canvas.get_renderer()
    width, height = r.get_canvas_width_height()
    data = r.buffer_rgba()
    pb = GdkPixbuf.Pixbuf.new_from_data(data, GdkPixbuf.Colorspace.RGB, True, 8,
                                        width, height, 4 * width, None, None)
    cb = Gtk.Clipboard.get_default(Gdk.Display.get_default())
    assert isinstance(cb, Gtk.Clipboard)
    cb.set_image(pb)
