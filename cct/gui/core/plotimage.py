import logging

from gi.repository import Gtk, Gio
import pkg_resources
import matplotlib.cm
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
from matplotlib.figure import Figure
import matplotlib.colors
import numpy as np

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class PlotImage(object):
    def __init__(self, **kwargs):
        self._builder=Gtk.Builder.new_from_file(pkg_resources.resource_filename('cct','resource/glade/core_plotimage.glade'))
        self._builder.set_application(Gio.Application.get_default())
        self._builder.connect_signals(self)
        self._window=self._builder.get_object('plotimage')
        self._inhibit_replot = False
        self._matrix=None
        self._mask=None
        self._beampos=None
        self._distance=None
        self._pixelsize=None
        self._fig=Figure()
        self._canvas=FigureCanvasGTK3Agg(self._fig)
        self._canvas.set_size_request(530, 350)
        self._toolbar=NavigationToolbar2GTK3(self._canvas, self._window)
        palette_combo=self._builder.get_object('palette_combo')
        for i,cm in enumerate(sorted(matplotlib.cm.cmap_d)):
            palette_combo.append_text(cm)
            if cm=='jet':
                palette_combo.set_active(i)
        box=self._builder.get_object('box1')
        box.pack_start(self._canvas,True,True,0)
        box.pack_start(self._toolbar,False, True, 0)
        if 'image' in kwargs:
            self._matrix = kwargs['image']
        if 'mask' in kwargs:
            self._mask = kwargs['mask']
        if 'beampos' in kwargs:
            self._beampos = kwargs['beampos']
        if 'distance' in kwargs:
            self._distance = kwargs['distance']
        if 'pixelsize' in kwargs:
            self._pixelsize = kwargs['pixelsize']
        if 'wavelength' in kwargs:
            self._wavelength = kwargs['wavelength']
        self._validate_parameters()
        self._replot()
        self._window.show_all()

    def on_settingschanged(self, widget):
        self._replot()

    def set_image(self, image):
        self._matrix = image
        self._validate_parameters()
        self._replot()

    def get_image(self):
        return self._matrix

    def set_mask(self, mask):
        self._mask = mask
        self._builder.get_object('showmask_checkbutton').set_active(True)
        self._replot()

    def get_mask(self):
        return self._mask

    def set_beampos(self, beamx, beamy):
        self._beampos=(beamx, beamy)
        self._builder.get_object('showcrosshair_checkbutton').set_active(True)
        self._validate_parameters()
        self._replot()

    def get_beampos(self):
        return self._beampos

    def set_pixelsize(self, pixelsize):
        self._pixelsize=pixelsize
        self._validate_parameters()

    def get_pixelsize(self):
        return self._pixelsize

    def set_palette(self, palette):
        for i,cm in enumerate(self._builder.get_object('palette_combo').get_model()):
            if cm[0]==palette:
                self._builder.get_object('palette_combo').set_active(i)
                break
        self._replot()
        raise KeyError('Unknown palette',palette)

    def get_palette(self):
        return self._builder.get_object('palette_combo').get_active_text()

    def set_distance(self, distance):
        self._distance=distance
        self._validate_parameters()
        self._replot()

    def get_distance(self):
        return self._distance

    def set_wavelength(self, wavelength):
        self._wavelength=wavelength
        self._validate_parameters()
        self._replot()

    def get_wavelength(self):
        return self._wavelength

    def _validate_parameters(self):
        ac=self._builder.get_object('axes_combo')
        previously_selected=ac.get_active_text()
        if previously_selected is None:
            previously_selected='abs. pixel'
        self._inhibit_replot = True
        try:
            ac.remove_all()
            ac.append_text('abs. pixel')
            if (self._beampos is not None):
                ac.append_text('rel. pixel')
                if (self._pixelsize is not None):
                    ac.append_text('detector radius')
                    if (self._distance is not None):
                        ac.append_text('twotheta')
                        if (self._wavelength is not None):
                            ac.append_text('q')
            active_set = False
            for i, scaling in enumerate(ac.get_model()):
                if scaling[0] == previously_selected:
                    ac.set_active(i)
                    active_set = True
                    break
            if not active_set:
                ac.set_active(0)
            self._builder.get_object('showmask_checkbutton').set_sensitive(self._mask is not None)
            self._builder.get_object('showcrosshair_checkbutton').set_sensitive(self._beampos is not None)
        finally:
            self._inhibit_replot = False

    def _replot(self):
        if self._inhibit_replot:
            return
        if self._matrix is None:
            return
        self._fig.clear()
        self._axis=self._fig.add_subplot(1,1,1)
        scaling=self._builder.get_object('colourscale_combo').get_active_text()
        if scaling=='linear':
            norm=matplotlib.colors.Normalize()
        elif scaling=='logarithmic':
            norm=matplotlib.colors.LogNorm()
        elif scaling=='square root':
            norm=matplotlib.colors.PowerNorm(0.5)
        elif scaling=='square':
            norm=matplotlib.colors.PowerNorm(2)
        else:
            raise NotImplementedError(scaling)
        axes=self._builder.get_object('axes_combo').get_active_text()
        if axes=='abs. pixel':
            extent = (0, self._matrix.shape[1] - 1, self._matrix.shape[0] - 1, 0)  # left, right, bottom, top
        elif axes=='rel. pixel':
            extent=(0- self._beampos[1], self._matrix.shape[1]-1-self._beampos[1],
                    self._matrix.shape[0] - 1 - self._beampos[0], 0 - self._beampos[0])
        elif axes=='detector radius':
            extent=((0- self._beampos[1])*self._pixelsize, (self._matrix.shape[1]-1-self._beampos[1])*self._pixelsize,
                    (self._matrix.shape[0] - 1 - self._beampos[0]) * self._pixelsize,
                    (0 - self._beampos[0]) * self._pixelsize)
        elif axes=='twotheta':
            extent = (np.arctan((0 - self._beampos[1]) * self._pixelsize / self._distance) * 180 / np.pi,
                      np.arctan((self._matrix.shape[1] - 1 - self._beampos[
                          1]) * self._pixelsize / self._distance) * 180 / np.pi,
                      np.arctan((self._matrix.shape[0] - 1 - self._beampos[
                          0]) * self._pixelsize / self._distance) * 180 / np.pi,
                      np.arctan((0 - self._beampos[0]) * self._pixelsize / self._distance) * 180 / np.pi)
        elif axes=='q':
            extent=(4*np.pi*np.sin(0.5*np.arctan((0- self._beampos[1])*self._pixelsize/self._distance))/self._wavelength,
                    4*np.pi*np.sin(0.5*np.arctan((self._matrix.shape[1]-1-self._beampos[1])*self._pixelsize/self._distance))/self._wavelength,
                    4 * np.pi * np.sin(0.5 * np.arctan((self._matrix.shape[0] - 1 - self._beampos[
                        0]) * self._pixelsize / self._distance)) / self._wavelength,
                    4 * np.pi * np.sin(
                        0.5 * np.arctan((0 - self._beampos[0]) * self._pixelsize / self._distance)) / self._wavelength)
        img=self._axis.imshow(self._matrix, cmap=self._builder.get_object('palette_combo').get_active_text(),
                              norm=norm, interpolation='nearest', aspect='equal', origin='upper', extent=extent)
        if (self._builder.get_object('showmask_checkbutton').get_sensitive() and
                self._builder.get_object('showmask_checkbutton').get_active()):
            mf=self._mask.astype(float)
            mf[~self._mask]=np.nan
            self._axis.imshow(mf, cmap=matplotlib.cm.gray_r, interpolation='nearest', aspect='equal', alpha=0.7,
                              origin='upper', extent=extent)
        if (self._builder.get_object('showcrosshair_checkbutton').get_sensitive() and
                self._builder.get_object('showcrosshair_checkbutton').get_active()):
            lims=self._axis.axis()
            if axes == 'abs. pixel':
                self._axis.plot([extent[0], extent[1]], [self._beampos[0], self._beampos[0]], 'w-', lw=1)
                self._axis.plot([self._beampos[1], self._beampos[1]], [extent[2], extent[3]], 'w-', lw=1)
            else:
                self._axis.plot([extent[0], extent[1]], [0, 0], 'w-', lw=1)
                self._axis.plot([0, 0], [extent[2], extent[3]], 'w-', lw=1)
            self._axis.axis(lims)
        if self._builder.get_object('showcolourscale_checkbutton').get_active():
            self._colorbaraxis=self._fig.colorbar(img, ax=self._axis).ax
        if axes == 'abs. pixel':
            self._axis.xaxis.set_label_text('Absolute column coordinate (pixel)')
            self._axis.yaxis.set_label_text('Absolute row coordinate (pixel)')
        elif axes == 'rel. pixel':
            self._axis.xaxis.set_label_text('Relative column coordinate (pixel)')
            self._axis.yaxis.set_label_text('Relative row coordinate (pixel)')
        elif axes == 'detector radius':
            self._axis.xaxis.set_label_text('Horizontal distance from the beam center (mm)')
            self._axis.yaxis.set_label_text('Vertical distance from the beam center (mm)')
        elif axes == 'twotheta':
            self._axis.xaxis.set_label_text('$2\\theta_x$ ($^\circ$)')
            self._axis.yaxis.set_label_text('$2\\theta_y$ ($^\circ$)')
        elif axes == 'q':
            self._axis.xaxis.set_label_text('q_x$ (nm$^{-1}$)')
            self._axis.yaxis.set_label_text('q_y$ (nm$^{-1}$)')
        self._fig.tight_layout()
        self._canvas.draw_idle()
        #ToDo: plot mask


    def on_close(self, widget, event=None):
        self._fig.clear()
        del self._mask
        del self._matrix
        self._window.destroy()
        return True

