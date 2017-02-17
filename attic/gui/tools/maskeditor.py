import datetime
import logging
import os

import numpy as np
from matplotlib.path import Path
from matplotlib.widgets import Cursor, EllipseSelector, LassoSelector, RectangleSelector
from sastool.io.credo_cct import Exposure
from scipy.io import loadmat, savemat

from ..core.exposureloader import ExposureLoader
from ..core.filechooser import DoubleFileChooserDialog
from ..core.plotimage import PlotImageWidget
from ..core.toolwindow import ToolWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MaskEditor(ToolWindow, DoubleFileChooserDialog):
    def __init__(self, *args, **kwargs):
        self.mask = None
        self._undo_stack = []
        self._im = None
        self._selector = None
        self._cursor = None
        self.exposureloader = None
        self.plot2d = None
        ToolWindow.__init__(self, *args, **kwargs)
        DoubleFileChooserDialog.__init__(
            self, self.widget, 'Open mask file...', 'Save mask file...', [('Mask files', '*.mat'), ('All files', '*')],
            self.instrument.config['path']['directories']['mask'],
            os.path.abspath(self.instrument.config['path']['directories']['mask']),
        )

    def init_gui(self, *args, **kwargs):
        self.exposureloader = ExposureLoader(self.instrument)
        self.builder.get_object('loadexposure_expander').add(self.exposureloader)
        self.exposureloader.connect('open', self.on_loadexposure)
        self.plot2d = PlotImageWidget()
        self.builder.get_object('plotbox').pack_start(self.plot2d.widget, True, True, 0)
        self.builder.get_object('toolbar').set_sensitive(False)

    def on_loadexposure(self, exposureloader: ExposureLoader, im: Exposure):
        if self.mask is None:
            self.mask = im.mask
        self._im = im
        self.plot2d.set_image(im.intensity)
        self.plot2d.set_mask(self.mask)
        self.builder.get_object('toolbar').set_sensitive(True)

    def on_new(self, button):
        if self._im is None or self.mask is None:
            return False
        self.mask = np.ones_like(self.mask)
        self.plot2d.set_mask(self.mask)
        self.set_last_filename(None)

    def on_open(self, button):
        filename = self.get_open_filename()
        if filename is not None:
            mask = loadmat(filename)
            self.mask = mask[[k for k in mask.keys() if not k.startswith('__')][0]]
            self.plot2d.set_mask(self.mask)

    def on_save(self, button):
        filename = self.get_last_filename()
        if filename is None:
            return self.on_saveas(button)
        maskname = os.path.splitext(os.path.split(filename)[1])[0]
        savemat(filename, {maskname: self.mask})

    def on_saveas(self, button):
        filename = self.get_save_filename(None)
        if filename is not None:
            self.on_save(button)

    def suggest_filename(self):
        return 'mask_dist_{0.year:d}{0.month:02d}{0.day:02d}.mat'.format(datetime.date.today())

    def on_selectcircle_toggled(self, button):
        if button.get_active():
            self.set_sensitive(False, 'Ellipse selection not ready',
                               ['new_button', 'save_button', 'saveas_button', 'open_button', 'undo_button',
                                'selectrectangle_button', 'selectpolygon_button', 'pixelhunting_button',
                                'loadexposure_expander', 'close_button', self.plot2d.toolbar,
                                self.plot2d.settings_expander])
            while self.plot2d.toolbar.mode != '':
                # turn off zoom, pan, etc. modes.
                self.plot2d.toolbar.zoom()
            self._selector = EllipseSelector(self.plot2d.axis,
                                             self.on_ellipse_selected,
                                             rectprops={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.7,
                                                        'fill': True, 'zorder': 10},
                                             button=[1, ],
                                             interactive=False, lineprops={'zorder': 10})
            self._selector.state.add('square')
            self._selector.state.add('center')
        else:
            assert isinstance(self._selector, EllipseSelector)
            self._selector.set_active(False)
            self._selector.set_visible(False)
            self._selector = None
            self.plot2d.replot(keepzoom=False)
            self.set_sensitive(True)

    def on_ellipse_selected(self, pos1, pos2):
        # pos1 and pos2 are mouse button press and release events, with xdata and ydata carrying
        # the two opposite corners of the bounding box of the circle. These are NOT the exact
        # button presses and releases!
        row = np.arange(self.mask.shape[0])[:, np.newaxis]
        column = np.arange(self.mask.shape[1])[np.newaxis, :]
        row0 = 0.5 * (pos1.ydata + pos2.ydata)
        col0 = 0.5 * (pos1.xdata + pos2.xdata)
        r2 = ((pos2.xdata - pos1.xdata) ** 2 + (pos2.ydata - pos1.ydata) ** 2) / 8
        tobemasked = (row - row0) ** 2 + (column - col0) ** 2 <= r2
        self._undo_stack.append(self.mask)
        if self.builder.get_object('mask_button').get_active():
            self.mask &= ~tobemasked
        elif self.builder.get_object('unmask_button').get_active():
            self.mask |= tobemasked
        elif self.builder.get_object('invertmask_button').get_active():
            self.mask[tobemasked] = ~self.mask[tobemasked]
        else:
            pass
        self.builder.get_object('selectcircle_button').set_active(False)
        self.plot2d.set_mask(self.mask)

    def on_selectrectangle_toggled(self, button):
        if button.get_active():
            self.set_sensitive(False, 'Rectangle selection not ready',
                               ['new_button', 'save_button', 'saveas_button', 'open_button', 'undo_button',
                                'selectcircle_button', 'selectpolygon_button', 'pixelhunting_button',
                                'loadexposure_expander', 'close_button', self.plot2d.toolbar,
                                self.plot2d.settings_expander])
            while self.plot2d.toolbar.mode != '':
                # turn off zoom, pan, etc. modes.
                self.plot2d.toolbar.zoom()
            self._selector = RectangleSelector(self.plot2d.axis,
                                               self.on_rectangle_selected,
                                               rectprops={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.7,
                                                          'fill': True, 'zorder': 10},
                                               button=[1, ],
                                               interactive=False, lineprops={'zorder': 10})
        else:
            self._selector.set_active(False)
            self._selector.set_visible(False)
            self._selector = None
            self.plot2d.replot(keepzoom=False)
            self.set_sensitive(True)

    def on_rectangle_selected(self, pos1, pos2):
        # pos1 and pos2 are mouse button press and release events, with xdata and ydata
        # carrying the two opposite corners of the bounding box of the rectangle. These
        # are NOT the exact button presses and releases!
        row = np.arange(self.mask.shape[0])[:, np.newaxis]
        column = np.arange(self.mask.shape[1])[np.newaxis, :]
        tobemasked = ((row >= min(pos1.ydata, pos2.ydata)) & (row <= max(pos1.ydata, pos2.ydata)) &
                      (column >= min(pos1.xdata, pos2.xdata)) & (column <= max(pos1.xdata, pos2.xdata)))
        self._undo_stack.append(self.mask)
        if self.builder.get_object('mask_button').get_active():
            self.mask = self.mask & (~tobemasked)
        elif self.builder.get_object('unmask_button').get_active():
            self.mask = self.mask | tobemasked
        elif self.builder.get_object('invertmask_button').get_active():
            self.mask[tobemasked] = ~self.mask[tobemasked]
        else:
            pass
        self.builder.get_object('selectrectangle_button').set_active(False)
        self.plot2d.set_mask(self.mask)

    def on_selectpolygon_toggled(self, button):
        if button.get_active():
            self.set_sensitive(False, 'Polygon selection not ready',
                               ['new_button', 'save_button', 'saveas_button', 'open_button', 'undo_button',
                                'selectrectangle_button', 'selectcircle_button', 'pixelhunting_button',
                                'loadexposure_expander', 'close_button', self.plot2d.toolbar,
                                self.plot2d.settings_expander])
            while self.plot2d.toolbar.mode != '':
                # turn off zoom, pan, etc. modes.
                self.plot2d.toolbar.zoom()
            self._selector = LassoSelector(self.plot2d.axis,
                                           self.on_polygon_selected,
                                           lineprops={'color': 'white', 'zorder': 10},
                                           button=[1, ],
                                           )
        else:
            self._selector.set_active(False)
            self._selector.set_visible(False)
            self._selector = None
            self.plot2d.replot(keepzoom=False)
            self.set_sensitive(True)

    def on_polygon_selected(self, vertices):
        path = Path(vertices)
        col, row = np.meshgrid(np.arange(self.mask.shape[1]),
                               np.arange(self.mask.shape[0]))
        points = np.vstack((col.flatten(), row.flatten())).T
        tobemasked = path.contains_points(points).reshape(self.mask.shape)
        self._undo_stack.append(self.mask)
        if self.builder.get_object('mask_button').get_active():
            self.mask = self.mask & (~tobemasked)
        elif self.builder.get_object('unmask_button').get_active():
            self.mask = self.mask | tobemasked
        elif self.builder.get_object('invertmask_button').get_active():
            self.mask[tobemasked] = ~self.mask[tobemasked]
        else:
            pass
        self.plot2d.set_mask(self.mask)
        self.builder.get_object('selectpolygon_button').set_active(False)

    def on_mask_toggled(self, button):
        pass

    def on_unmask_toggled(self, button):
        pass

    def on_invertmask_toggled(self, button):
        pass

    def on_pixelhunting_toggled(self, button):
        if button.get_active():
            self._cursor = Cursor(self.plot2d.axis, useblit=False, color='white', lw=1)
            self._cursor.connect_event('button_press_event', self.on_cursorclick)
            while self.plot2d.toolbar.mode != '':
                # turn off zoom, pan, etc. modes.
                self.plot2d.toolbar.zoom()
        else:
            self._cursor.disconnect_events()
            self._cursor = None
            self._undo_stack.append(self.mask)
            self.plot2d.replot(keepzoom=False)

    def on_cursorclick(self, event):
        if (event.inaxes == self.plot2d.axis) and (self.plot2d.toolbar.mode == ''):
            self.mask[round(event.ydata), round(event.xdata)] ^= True
            self._cursor.disconnect_events()
            self._cursor = None
            self.plot2d.replot(keepzoom=True)
            self.on_pixelhunting_toggled(self.builder.get_object('pixelhunting_button'))

    def cleanup(self):
        super().cleanup()
        self._undo_stack = []

    def on_undo(self, button):
        try:
            self.mask = self._undo_stack.pop()
        except IndexError:
            return
        self.plot2d.set_mask(self.mask)
