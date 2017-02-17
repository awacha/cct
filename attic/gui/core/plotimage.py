import logging
import traceback
from typing import Optional, Tuple

import matplotlib.axes
import matplotlib.cm
import matplotlib.colors
import numpy as np
import pkg_resources
from gi.repository import Gtk
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.figure import Figure

from .builderwidget import BuilderWidget
from .functions import savefiguretoclipboard
from ...core.utils.inhibitor import Inhibitor

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)



class PlotImageWidget(BuilderWidget):
    def __init__(self, image: Optional[np.ndarray] = None,
                 mask: Optional[np.ndarray] = None,
                 beampos: Optional[Tuple[float, float]] = None,
                 distance: Optional[float] = None,
                 pixelsize: Optional[float] = None,
                 wavelength: Optional[float] = None):
        super().__init__(pkg_resources.resource_filename('cct', 'resource/glade/core_plotimage.glade'), 'plotimage')
        self.inhibit_replot = Inhibitor(self.replot)
        self.replot_needed = False
        self._matrix = image
        self._mask = mask
        self._beampos = beampos
        self._distance = distance
        self._pixelsize = pixelsize
        self._wavelength = wavelength

        self.validate_parameters()
        self.fig = Figure(tight_layout=True)
        self.axis = self.fig.add_subplot(1, 1, 1)
        self.axis.set_axis_bgcolor('black')
        self.axis.set_anchor('C')
        self._image_handle = None
        self._mask_handle = None
        self._crosshair_handles = []
        self.colorbaraxis = None
        self.canvas = FigureCanvasGTK3Agg(self.fig)
        self.canvas.set_size_request(530, 350)
        self.toolbar = NavigationToolbar2GTK3(self.canvas, None)
        b = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('view-refresh', Gtk.IconSize.LARGE_TOOLBAR),
                           label='Redraw')
        b.set_tooltip_text('Redraw the image')
        self.toolbar.insert(b, 9)
        b.connect('clicked', lambda b_: self.replot(False))
        b = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('edit-copy', Gtk.IconSize.LARGE_TOOLBAR),
                           label='Copy')
        b.set_tooltip_text('Copy the image to the clipboard')
        b.connect('clicked', lambda b_, f=self.fig: savefiguretoclipboard(f))
        self.toolbar.insert(b, 9)
        palette_combo = self.builder.get_object('palette_combo')
        for i, cm in enumerate(sorted(matplotlib.cm.cmap_d)):
            palette_combo.append_text(cm)
            if cm == 'viridis':
                palette_combo.set_active(i)
        self.widget.pack_start(self.canvas, True, True, 0)
        self.widget.pack_start(self.toolbar, False, True, 0)
        self.settings_expander = self.builder.get_object('settings_expander')
        self.replot()
        self.widget.show_all()

    def on_settingschanged(self, widget):
        self.replot()

    def on_showmask_toggled(self, widget: Gtk.CheckButton):
        self.replot_mask()
        self.canvas.draw_idle()

    def on_showcrosshair_toggled(self, widget: Gtk.CheckButton):
        self.replot_crosshair()
        self.canvas.draw_idle()

    def on_showcolourscale_toggled(self, widget: Gtk.CheckButton):
        logger.debug('showcolourscale toggled.')
        self.replot_colorbar()
        self.canvas.draw_idle()

    def set_image(self, image: np.ndarray):
        assert isinstance(image, np.ndarray)
        if ((self._matrix is image) or
                (isinstance(image, np.ndarray) and
                     isinstance(self._matrix, np.ndarray) and
                     (self._matrix == image).all())):
            # do nothing if the matrix has not changed.
            return
        logger.debug('Set_image')
        self._matrix = image
        self.replot_image()
        self.canvas.draw_idle()

    def get_image(self) -> np.ndarray:
        return self._matrix

    def set_mask(self, mask: Optional[np.ndarray] = None):
        if (mask is self._mask) or (isinstance(mask, type(self._mask)) and (mask == self._mask).all()):
            # do nothing if the mask has not changed
            return
        logger.debug('Set_mask')
        self._mask = mask
        self.validate_parameters()
        self.replot_mask()
        self.canvas.draw_idle()

    def get_mask(self) -> Optional[np.ndarray]:
        return self._mask

    def set_beampos(self, beamx: float, beamy: float):
        if self._beampos != (beamx, beamy):
            logger.debug('set_beampos')
            self._beampos = (beamx, beamy)
            self.validate_parameters()
            self.replot_crosshair()
            self.canvas.draw_idle()

    def get_beampos(self):
        return self._beampos

    def set_pixelsize(self, pixelsize):
        if self._pixelsize != pixelsize:
            logger.debug('set_pixelsize')
            self._pixelsize = pixelsize
            self.validate_parameters()
            self.replot()

    def get_pixelsize(self):
        return self._pixelsize

    def set_palette(self, palette: str):
        if self.builder.get_object('palette_combo').get_active_text() == palette:
            return
        logger.debug('Set_palette')
        for i, cm in enumerate(self.builder.get_object('palette_combo').get_model()):
            if cm[0] == palette:
                self.builder.get_object('palette_combo').set_active(i)
                self.replot_image()
                self.canvas.draw_idle()
                return
        raise ValueError('Unknown palette', palette)

    def get_palette(self) -> str:
        return self.builder.get_object('palette_combo').get_active_text()

    def set_distance(self, distance: float):
        if self._distance != distance:
            logger.debug('set_distance')
            self._distance = distance
            self.validate_parameters()
            self.replot()

    def get_distance(self) -> float:
        return self._distance

    def set_wavelength(self, wavelength: float):
        if self._wavelength != wavelength:
            logger.debug('set_wavelength')
            self._wavelength = wavelength
            self.validate_parameters()
            self.replot()

    def get_wavelength(self) -> float:
        return self._wavelength

    def validate_parameters(self):
        ac = self.builder.get_object('axes_combo')
        previously_selected = ac.get_active_text()
        with self.inhibit_replot:
            ac.remove_all()
            ac.append_text('abs. pixel')
            for attr, scale in [('_beampos', 'rel. pixel'),
                                ('_pixelsize', 'detector radius'),
                                ('_distance', 'twotheta'),
                                ('_wavelength', 'q')]:
                if getattr(self, attr) is not None:
                    ac.append_text(scale)
                else:
                    break
            active_set = False
            lastidx = 0
            for i, scaling in enumerate(ac.get_model()):
                lastidx = i
                if scaling[0] == previously_selected:
                    ac.set_active(i)
                    active_set = True
                    break
            if not active_set:
                ac.set_active(lastidx)
            self.builder.get_object('showmask_checkbutton').set_sensitive(self._mask is not None)
            self.builder.get_object('showcrosshair_checkbutton').set_sensitive(self._beampos is not None)

    def replot_image(self):
        if self.inhibit_replot.inhibited:
            self.replot_needed = True
            return
        try:
            self._image_handle.remove()
        except (AttributeError, ValueError):
            pass
        self._image_handle = None
        scaling = self.builder.get_object('colourscale_combo').get_active_text()
        if self._matrix.max() <= 0:
            self.builder.get_object('colourscale_combo').set_active(0)
            return
        if scaling == 'linear':
            norm = matplotlib.colors.Normalize()
            matrix = self._matrix
        elif scaling == 'logarithmic':
            norm = matplotlib.colors.LogNorm()
            matrix = self._matrix.copy()
            matrix[matrix <= 0] = np.nan
        elif scaling == 'square root':
            norm = matplotlib.colors.PowerNorm(0.5)
            matrix = self._matrix.copy()
            matrix[matrix <= 0] = np.nan
        elif scaling == 'square':
            norm = matplotlib.colors.PowerNorm(2)
            matrix = self._matrix.copy()
            matrix[matrix <= 0] = np.nan
        else:
            raise ValueError(scaling)
        axesscale = self.builder.get_object('axes_combo').get_active_text()
        if axesscale == 'abs. pixel':
            extent = (0, self._matrix.shape[1] - 1, self._matrix.shape[0] - 1, 0)  # left, right, bottom, top
        elif axesscale == 'rel. pixel':
            extent = (0 - self._beampos[0], self._matrix.shape[1] - 1 - self._beampos[0],
                      self._matrix.shape[0] - 1 - self._beampos[1], 0 - self._beampos[1])
        elif axesscale == 'detector radius':
            extent = (
                (0 - self._beampos[0]) * self._pixelsize,
                (self._matrix.shape[1] - 1 - self._beampos[0]) * self._pixelsize,
                (self._matrix.shape[0] - 1 - self._beampos[1]) * self._pixelsize,
                (0 - self._beampos[1]) * self._pixelsize)
        elif axesscale == 'twotheta':
            extent = (np.arctan((0 - self._beampos[0]) * self._pixelsize / self._distance) * 180 / np.pi,
                      np.arctan((self._matrix.shape[1] - 1 - self._beampos[
                          0]) * self._pixelsize / self._distance) * 180 / np.pi,
                      np.arctan((self._matrix.shape[0] - 1 - self._beampos[
                          1]) * self._pixelsize / self._distance) * 180 / np.pi,
                      np.arctan((0 - self._beampos[1]) * self._pixelsize / self._distance) * 180 / np.pi)
        elif axesscale == 'q':
            extent = (4 * np.pi * np.sin(
                0.5 * np.arctan((0 - self._beampos[0]) * self._pixelsize / self._distance)) / self._wavelength,
                      4 * np.pi * np.sin(0.5 * np.arctan((self._matrix.shape[1] - 1 - self._beampos[
                          0]) * self._pixelsize / self._distance)) / self._wavelength,
                      4 * np.pi * np.sin(0.5 * np.arctan((self._matrix.shape[0] - 1 - self._beampos[
                          1]) * self._pixelsize / self._distance)) / self._wavelength,
                      4 * np.pi * np.sin(
                          0.5 * np.arctan(
                              (0 - self._beampos[1]) * self._pixelsize / self._distance)) / self._wavelength)
        else:
            raise ValueError(axesscale)
        extent = tuple([float(e) for e in extent])
        self._image_handle = self.axis.imshow(matrix, cmap=self.builder.get_object('palette_combo').get_active_text(),
                                              norm=norm, interpolation='nearest', aspect='equal', origin='upper',
                                              extent=extent, zorder=1)
        if axesscale == 'abs. pixel':
            self.axis.xaxis.set_label_text('Absolute column coordinate (pixel)')
            self.axis.yaxis.set_label_text('Absolute row coordinate (pixel)')
        elif axesscale == 'rel. pixel':
            self.axis.xaxis.set_label_text('Relative column coordinate (pixel)')
            self.axis.yaxis.set_label_text('Relative row coordinate (pixel)')
        elif axesscale == 'detector radius':
            self.axis.xaxis.set_label_text('Horizontal distance from the beam center (mm)')
            self.axis.yaxis.set_label_text('Vertical distance from the beam center (mm)')
        elif axesscale == 'twotheta':
            self.axis.xaxis.set_label_text('$2\\theta_x$ ($^\circ$)')
            self.axis.yaxis.set_label_text('$2\\theta_y$ ($^\circ$)')
        elif axesscale == 'q':
            self.axis.xaxis.set_label_text('$q_x$ (nm$^{-1}$)')
            self.axis.yaxis.set_label_text('$q_y$ (nm$^{-1}$)')

    def replot_mask(self):
        if self.inhibit_replot.inhibited:
            self.replot_needed = True
            return
        if self._image_handle is None:
            return
        try:
            self._mask_handle.remove()
        except (AttributeError, ValueError):
            pass
        self._mask_handle = None
        if not (self.builder.get_object('showmask_checkbutton').get_sensitive() and
                    self.builder.get_object('showmask_checkbutton').get_active()):
            return
        if self._mask is None:
            return
        mf = np.ones(self._mask.shape, np.float)  # in `mf`, masked pixels are 1.0, unmasked (valid) are 0.0
        mf[self._mask != 0] = np.nan  # now mf consists of 1.0 (masked) and NaN (valid) values.
        self._mask_handle = self.axis.imshow(mf, cmap=matplotlib.cm.gray_r, interpolation='nearest', aspect='equal',
                                             alpha=0.7,
                                             origin='upper', extent=self._image_handle.get_extent(), zorder=2)

    def replot_crosshair(self):
        if self.inhibit_replot.inhibited:
            self.replot_needed = True
            return
        if self._image_handle is None:
            return
        for h in self._crosshair_handles:
            try:
                h.remove()
            except (IndexError, TypeError, ValueError):
                pass
        self._crosshair_handles = []
        if not (self.builder.get_object('showcrosshair_checkbutton').get_sensitive() and
                    self.builder.get_object('showcrosshair_checkbutton').get_active()):
            return
        if self._beampos is None:
            return
        extent = self._image_handle.get_extent()
        if self.builder.get_object('axes_combo').get_active_text() == 'abs. pixel':
            self._crosshair_handles = self.axis.plot([extent[0], extent[1]],
                                                     [self._beampos[1], self._beampos[1]],
                                                     [self._beampos[0], self._beampos[0]],
                                                     [extent[2], extent[3]],
                                                     color='w', lw=1, scalex=False, scaley=False, zorder=3)
        else:
            self._crosshair_handles = self.axis.plot([extent[0], extent[1]], [0, 0],
                                                     [0, 0], [extent[2], extent[3]], color='w', lw=1,
                                                     scalex=False, scaley=False, zorder=3)

    def replot_colorbar(self):
        if self.inhibit_replot.inhibited:
            self.replot_needed = True
            return
        logger.debug('Replotting color bar')
        if self._image_handle is None:
            logger.debug('Image handle is None, skipping replot of colorbar')
            return
        if self.builder.get_object('showcolourscale_checkbutton').get_active():
            logger.debug('Replotting colorbar axis.')
            try:
                if self.colorbaraxis is None:
                    logger.debug('Creating new colorbar axis')
                    self.colorbaraxis = self.fig.colorbar(
                        self._image_handle, ax=self.axis, use_gridspec=True)
                else:
                    logger.debug('Using previous colorbar axis')
                    self.colorbaraxis = self.fig.colorbar(
                        self._image_handle, cax=self.colorbaraxis.ax, use_gridspec=True)
            except ValueError as ve:
                logger.error('Cannot draw colorbar:' + str(ve) + traceback.format_exc())
        else:
            logger.debug('Removing colorbar axis.')
            try:
                self.colorbaraxis.ax.remove()
            except (AttributeError, ValueError, KeyError):
                pass
            finally:
                self.colorbaraxis = None
            self.axis.set_anchor("C")

    def replot(self, keepzoom=True):
        if self.inhibit_replot.inhibited or (self._matrix is None):
            return
        if not keepzoom:
            self.toolbar.update()
            self.axis.clear()
            self._image_handle = None
            if self.colorbaraxis is not None:
                self.colorbaraxis.ax.remove()
                self.colorbaraxis = None
            self._crosshair_handles = []
            self._mask_handle = None
        self.replot_image()
        self.replot_mask()
        self.replot_crosshair()
        self.replot_colorbar()
        self.canvas.draw_idle()

class PlotImageWindow(PlotImageWidget):
    instancelist = []

    def __init__(self, **kwargs):
        PlotImageWidget.__init__(self, **kwargs)
        self.window = Gtk.Window()
        self.window.add(self.widget)
        self.window.connect('destroy', self.on_destroy)
        self.window.connect('focus-in-event', self.on_focus_in)
        self.window.show_all()
        PlotImageWindow.instancelist.append(self)

    def on_destroy(self, window):
        PlotImageWindow.instancelist.remove(self)
        self.widget.destroy()
        del self.window
        return False

    def on_focus_in(self, window, event):
        PlotImageWindow.instancelist.remove(self)
        PlotImageWindow.instancelist.append(self)

    @classmethod
    def get_latest_window(cls):
        if not cls.instancelist:
            return cls()
        else:
            return cls.instancelist[-1]

    def set_title(self, title: str):
        self.window.set_title(title)
