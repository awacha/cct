import logging
import os

import numpy as np
from gi.repository import Gtk
from matplotlib.path import Path
from matplotlib.widgets import Cursor, EllipseSelector, RectangleSelector, LassoSelector
from scipy.io import loadmat, savemat

from ..core.exposureloader import ExposureLoader
from ..core.plotimage import PlotImageWidget
from ..core.toolwindow import ToolWindow

logger = logging.getLogger(__name__)
logger.setlevel(logging.INFO)


class MaskEditor(ToolWindow):
    def _init_gui(self, *args):
        self._el = ExposureLoader(self._instrument)
        self._builder.get_object('loadexposure_expander').add(self._el)
        self._el.connect('open', self.on_loadexposure)
        self._plot2d = PlotImageWidget()
        self._builder.get_object('plotbox').pack_start(self._plot2d._widget, True, True, 0)
        self._mask = None
        self._builder.get_object('toolbar').set_sensitive(False)
        self._undo_stack = []

    def on_loadexposure(self, exposureloader, im):
        if self._mask is None:
            self._mask = im._mask
        self._im = im
        self._plot2d.set_image(im.val)
        self._plot2d.set_mask(self._mask)
        self._builder.get_object('toolbar').set_sensitive(True)

    def on_new(self, button):
        self._mask = np.ones_like(self._mask)
        self._plot2d.set_mask(self._mask)

    def on_open(self, button):
        if not hasattr(self, '_filechooser'):
            self._filechooser = Gtk.FileChooserDialog('Open mask file...',
                                                      self._window,
                                                      Gtk.FileChooserAction.OPEN,
                                                      ['Open', 1, 'Cancel', 0])
            self._filechooser.set_do_overwrite_confirmation(True)
            self._filefilter = Gtk.FileFilter()
            self._filefilter.add_pattern('*.mat')
            self._filefilter.set_name('Mask files')
            self._filechooser.add_filter(self._filefilter)
        self._filechooser.set_action(Gtk.FileChooserAction.OPEN)
        self._filechooser.get_widget_for_response(1).set_label('Open')
        if self._filechooser.run():
            self._filename = self._filechooser.get_filename()
            mask = loadmat(self._filename)
            self._mask = mask[[k for k in mask.keys() if not k.startswith('__')][0]]
            self._plot2d.set_mask(self._mask)
        self._filechooser.hide()

    def on_save(self, button):
        if not hasattr(self, '_filename'):
            return self.on_saveas(button)
        maskname = os.path.splitext(os.path.split(self._filename)[1])[0]
        savemat(self._filename, {maskname: self._mask})

    def on_saveas(self, button):
        if not hasattr(self, '_filechooser'):
            self._filechooser = Gtk.FileChooserDialog('Save mask file...',
                                                      self._window,
                                                      Gtk.FileChooserAction.SAVE,
                                                      ['Save', 1, 'Cancel', 0])
            self._filechooser.set_do_overwrite_confirmation(True)
            self._filefilter = Gtk.FileFilter()
            self._filefilter.add_pattern('*.mat')
            self._filefilter.set_name('Mask files')
            self._filechooser.add_filter(self._filefilter)
        self._filechooser.set_action(Gtk.FileChooserAction.SAVE)
        self._filechooser.get_widget_for_response(1).set_label('Save')
        if self._filechooser.run() == 1:
            self._filename = self._filechooser.get_filename()
            self.on_save(button)
        self._filechooser.hide()

    def on_selectcircle_toggled(self, button):
        if button.get_active():
            self._make_insensitive('Ellipse selection not ready',
                                   ['new_button', 'save_button', 'saveas_button', 'open_button', 'undo_button',
                                    'selectrectangle_button', 'selectpolygon_button', 'pixelhunting_button',
                                    'loadexposure_expander', 'close_button'],
                                   [self._plot2d._toolbar, self._plot2d._settings_expander])
            while self._plot2d._toolbar.mode != '':
                # turn off zoom, pan, etc. modes.
                self._plot2d._toolbar.zoom()
            self._selector = EllipseSelector(self._plot2d._axis,
                                             self.on_ellipse_selected,
                                             rectprops={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.7,
                                                        'fill': True},
                                             button=[1, ],
                                             interactive=False, )
            self._selector.state.add('square')
            self._selector.state.add('center')
        else:
            try:
                del self._selector
                self._plot2d._replot()
            except AttributeError:
                pass
            self._make_sensitive()

    def on_ellipse_selected(self, pos1, pos2):
        # pos1 and pos2 are mouse button press and release events, with xdata and ydata carrying the two opposite corners of the
        # bounding box of the circle. These are NOT the exact button presses and releases!
        row = np.arange(self._mask.shape[0])[:, np.newaxis]
        column = np.arange(self._mask.shape[1])[np.newaxis, :]
        row0 = 0.5 * (pos1.ydata + pos2.ydata)
        col0 = 0.5 * (pos1.xdata + pos2.xdata)
        r2 = ((pos2.xdata - pos1.xdata) ** 2 + (pos2.ydata - pos1.ydata) ** 2) / 8
        tobemasked = (row - row0) ** 2 + (column - col0) ** 2 <= r2
        self._undo_stack.append(self._mask)
        if self._builder.get_object('mask_button').get_active():
            self._mask = self._mask & (~tobemasked)
        elif self._builder.get_object('unmask_button').get_active():
            self._mask = self._mask | (tobemasked)
        elif self._builder.get_object('invertmask_button').get_active():
            self._mask[tobemasked] = ~self._mask[tobemasked]
        else:
            pass
        self._builder.get_object('selectcircle_button').set_active(False)
        self._plot2d.set_mask(self._mask)

    def on_selectrectangle_toggled(self, button):
        if button.get_active():
            self._make_insensitive('Ellipse selection not ready',
                                   ['new_button', 'save_button', 'saveas_button', 'open_button', 'undo_button',
                                    'selectcircle_button', 'selectpolygon_button', 'pixelhunting_button',
                                    'loadexposure_expander', 'close_button'],
                                   [self._plot2d._toolbar, self._plot2d._settings_expander])
            while self._plot2d._toolbar.mode != '':
                # turn off zoom, pan, etc. modes.
                self._plot2d._toolbar.zoom()
            self._selector = RectangleSelector(self._plot2d._axis,
                                               self.on_rectangle_selected,
                                               rectprops={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.7,
                                                          'fill': True},
                                               button=[1, ],
                                               interactive=False, )
        else:
            try:
                del self._selector
                self._plot2d._replot()
            except AttributeError:
                pass
            self._make_sensitive()

    def on_rectangle_selected(self, pos1, pos2):
        # pos1 and pos2 are mouse button press and release events, with xdata and ydata carrying the two opposite corners of the
        # bounding box of the circle. These are NOT the exact button presses and releases!
        row = np.arange(self._mask.shape[0])[:, np.newaxis]
        column = np.arange(self._mask.shape[1])[np.newaxis, :]
        tobemasked = ((row >= min(pos1.ydata, pos2.ydata)) & (row <= max(pos1.ydata, pos2.ydata)) &
                      (column >= min(pos1.xdata, pos2.xdata)) & (column <= max(pos1.xdata, pos2.xdata)))
        self._undo_stack.append(self._mask)
        if self._builder.get_object('mask_button').get_active():
            self._mask = self._mask & (~tobemasked)
        elif self._builder.get_object('unmask_button').get_active():
            self._mask = self._mask | (tobemasked)
        elif self._builder.get_object('invertmask_button').get_active():
            self._mask[tobemasked] = ~self._mask[tobemasked]
        else:
            pass
        self._builder.get_object('selectrectangle_button').set_active(False)
        self._plot2d.set_mask(self._mask)

    def on_selectpolygon_toggled(self, button):
        if button.get_active():
            self._make_insensitive('Ellipse selection not ready',
                                   ['new_button', 'save_button', 'saveas_button', 'open_button', 'undo_button',
                                    'selectrectangle_button', 'selectcircle_button', 'pixelhunting_button',
                                    'loadexposure_expander', 'close_button'],
                                   [self._plot2d._toolbar, self._plot2d._settings_expander])
            while self._plot2d._toolbar.mode != '':
                # turn off zoom, pan, etc. modes.
                self._plot2d._toolbar.zoom()
            self._selector = LassoSelector(self._plot2d._axis,
                                           self.on_polygon_selected,
                                           lineprops={'color': 'white'},
                                           button=[1, ],
                                           )
        else:
            try:
                del self._selector
                self._plot2d._replot()
            except AttributeError:
                pass
            self._make_sensitive()

    def on_polygon_selected(self, vertices):
        path = Path(vertices)
        col, row = np.meshgrid(np.arange(self._mask.shape[1]),
                               np.arange(self._mask.shape[0]))
        points = np.vstack((col.flatten(), row.flatten())).T
        tobemasked = path.contains_points(points).reshape(self._mask.shape)
        self._undo_stack.append(self._mask)
        if self._builder.get_object('mask_button').get_active():
            self._mask = self._mask & (~tobemasked)
        elif self._builder.get_object('unmask_button').get_active():
            self._mask = self._mask | (tobemasked)
        elif self._builder.get_object('invertmask_button').get_active():
            self._mask[tobemasked] = ~self._mask[tobemasked]
        else:
            pass
        self._plot2d.set_mask(self._mask)
        self._builder.get_object('selectpolygon_button').set_active(False)

    def on_mask_toggled(self, button):
        pass

    def on_unmask_toggled(self, button):
        pass

    def on_invertmask_toggled(self, button):
        pass

    def on_pixelhunting_toggled(self, button):
        if button.get_active():
            self._cursor = Cursor(self._plot2d._axis, useblit=False, color='white', lw=1)
            self._cursor.connect_event('button_press_event', self.on_cursorclick)
            while self._plot2d._toolbar.mode != '':
                # turn off zoom, pan, etc. modes.
                self._plot2d._toolbar.zoom()
        else:
            self._cursor.disconnect_events()
            del self._cursor
            self._undo_stack.append(self._mask)
            self._plot2d._replot(keepzoom=True)

    def on_cursorclick(self, event):
        if (event.inaxes == self._plot2d._axis) and (self._plot2d._toolbar.mode == ''):
            self._mask[round(event.ydata), round(event.xdata)] ^= True
            self._cursor.disconnect_events()
            del self._cursor
            self._plot2d._replot(keepzoom=True)
            self.on_pixelhunting_toggled(self._builder.get_object('pixelhunting_button'))

    def on_unmap(self, window):
        ToolWindow.on_unmap(self, window)
        self._undo_stack = []

    def on_undo(self, button):
        try:
            self._mask = self._undo_stack.pop()
        except IndexError:
            return
        self._plot2d.set_mask(self._mask)
