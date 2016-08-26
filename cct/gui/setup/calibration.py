import logging
import traceback
from typing import Union, Tuple

import numpy as np
from gi.repository import Gtk
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.figure import Figure
from matplotlib.widgets import Cursor
from sastool.classes2 import Curve
from sastool.io.credo_cct import Exposure
from sastool.misc.basicfit import findpeak_single
from sastool.misc.easylsq import nonlinear_odr
from sastool.misc.errorvalue import ErrorValue
from sastool.utils2d.centering import findbeam_radialpeak, findbeam_powerlaw

from ..core.exposureloader import ExposureLoader
from ..core.functions import update_comboboxtext_choices
from ..core.plotcurve import PlotCurveWidget
from ..core.plotimage import PlotImageWidget
from ..core.toolwindow import ToolWindow, error_message

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def qfrompix(pix, pixelsize, beampos, alpha, wavelength, dist):
    pixsizedivdist = pixelsize / dist
    catethus_near = 1 + pixsizedivdist * (pix - beampos) * np.cos(alpha)
    catethus_opposite = pixsizedivdist * (pix - beampos) * np.sin(alpha)
    twotheta = np.arctan2(catethus_opposite, catethus_near)
    return 4 * np.pi * np.sin(0.5 * twotheta) / wavelength


class Calibration(ToolWindow):
    def __init__(self, *args, **kwargs):
        self._cursor = None
        self._exposure = None
        self._curve = None
        self._manualpickingconnection = None
        self.plot2d = None
        self.plot1d = None
        self.figpairs = None
        self.figpairscanvas = None
        self.figpairstoolbox = None
        self.figpairsaxes = None
        self.exposureloader = None
        self._dist = None
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        self.plot2d = PlotImageWidget()
        self.builder.get_object('figbox_2d').pack_start(self.plot2d.widget, True, True, 0)
        self.plot1d = PlotCurveWidget()
        self.builder.get_object('figbox_1d').pack_start(self.plot1d.widget, True, True, 0)
        self.figpairs = Figure(tight_layout=True)
        self.figpairscanvas = FigureCanvasGTK3Agg(self.figpairs)
        self.builder.get_object('figbox_distcalib').pack_start(self.figpairscanvas, True, True, 0)
        self.figpairstoolbox = NavigationToolbar2GTK3(self.figpairscanvas, self.widget)
        self.builder.get_object('figbox_distcalib').pack_start(self.figpairstoolbox, False, True, 0)
        self.figpairsaxes = self.figpairs.add_subplot(1, 1, 1)
        logger.debug('Initializing EL')
        self.exposureloader = ExposureLoader(self.instrument)
        logger.debug('EL ready. Packing.')
        self.builder.get_object('loadfile_expander').add(self.exposureloader)
        logger.debug('EL packed. Connecting.')
        self.exposureloader.connect('open', self.on_loadexposure)
        self.exposureloader.connect('error', self.on_loadexposure_error)
        logger.debug('Connected.')
        tv = self.builder.get_object('pairview')
        tc = Gtk.TreeViewColumn('Uncalibrated', Gtk.CellRendererText(), text=0)
        tv.append_column(tc)
        tc = Gtk.TreeViewColumn('Calibrated', Gtk.CellRendererText(), text=1)
        tv.append_column(tc)
        csel = self.builder.get_object('calibrant_selector')
        csel.remove_all()
        for calibrant in sorted(self.instrument.config['calibrants']):
            csel.append_text(calibrant)
        csel.set_active(0)
        self.on_calibrant_selector_changed(csel)

    def on_calibrant_selector_changed(self, csel: Gtk.ComboBoxText):
        update_comboboxtext_choices(
            self.builder.get_object('peak_selector'),
            sorted(self.instrument.config['calibrants'][csel.get_active_text()]))

    def on_peak_selector_changed(self, psel: Gtk.ComboBoxText):
        calibrant = self.builder.get_object('calibrant_selector').get_active_text()
        if calibrant is None:
            return
        peak = psel.get_active_text()
        if peak is None:
            return
        self.builder.get_object('calval_adjustment').set_value(
            self.instrument.config['calibrants'][calibrant][peak]['val'])
        self.builder.get_object('calerr_adjustment').set_value(
            self.instrument.config['calibrants'][calibrant][peak]['err'])
        logger.debug('Set from calibrant.')

    def on_addpair(self, button: Gtk.Button):
        model = self.builder.get_object('pairstore')
        calval = self.builder.get_object('calval_adjustment').get_value()
        calerr = self.builder.get_object('calerr_adjustment').get_value()
        uncalval = self.builder.get_object('uncalval_adjustment').get_value()
        uncalerr = self.builder.get_object('uncalerr_adjustment').get_value()
        cal = ErrorValue(calval, calerr)
        uncal = ErrorValue(uncalval, uncalerr)
        model.append((uncal.tostring(plusminus=' \u00b1 '), cal.tostring(plusminus=' \u00b1 '), uncalval, uncalerr,
                      calval, calerr))
        self.replot_calpairs()

    def replot_calpairs(self):
        uncalval = []
        uncalerr = []
        calval = []
        calerr = []
        for row in self.builder.get_object('pairstore'):
            uncalval.append(row[2])
            uncalerr.append(row[3])
            calval.append(row[4])
            calerr.append(row[5])
        self.figpairsaxes.clear()
        self.figpairsaxes.errorbar(uncalval, calval, calerr, uncalerr, '.')
        self.figpairsaxes.set_xlabel('Uncalibrated (pixel)')
        self.figpairsaxes.set_ylabel('Calibrated (nm$^{-1}$)')
        self.figpairscanvas.draw()
        self.do_getdistance()

    def on_removepair(self, button: Gtk.Button):
        model, it = self.builder.get_object('pairview').get_selection().get_selected()
        if it is None:
            return
        model.remove(it)
        self.replot_calpairs()

    def on_exportpairs(self, button: Gtk.Button):
        pass

    def on_overridemask_toggled(self, checkbutton: Gtk.CheckButton):
        self.builder.get_object('maskchooser').set_sensitive(checkbutton.get_active())

    def on_fitlorentz(self, button):
        self.do_fit('Lorentz')

    def on_fitgauss(self, button):
        self.do_fit('Gauss')

    def do_getdistance(self):
        model = self.builder.get_object('pairstore')
        uncalval = np.array([row[2] for row in model])
        uncalerr = np.array([row[3] for row in model])
        calval = np.array([row[4] for row in model])
        calerr = np.array([row[5] for row in model])
        logger.debug('Uncalval: ' + str(uncalval))
        logger.debug('Uncalerr: ' + str(uncalerr))
        logger.debug('Calval: ' + str(calval))
        logger.debug('Calerr: ' + str(calerr))
        assert isinstance(self._exposure, Exposure)
        assert self._exposure.header.pixelsizex == self._exposure.header.pixelsizey
        if len(uncalval) > 1:
            def fitfunc(pix_: np.ndarray, dist: float):
                return qfrompix(pix_, pixelsize=self._exposure.header.pixelsizex,
                                beampos=0, alpha=np.pi * 0.5,
                                wavelength=self._exposure.header.wavelength,
                                dist=dist)

            self._dist, stat = nonlinear_odr(uncalval, calval, uncalerr, calerr, fitfunc, [100])
            x = np.linspace(uncalval.min(), uncalval.max(), len(uncalval) * 100)
            self.figpairsaxes.plot(x, fitfunc(x, self._dist.val), 'r-')
        elif len(uncalval) == 1:
            q = ErrorValue(float(calval[0]), float(calerr[0]))
            pix = ErrorValue(float(uncalval[0]), float(uncalerr[0]))
            wl = ErrorValue(
                self._exposure.header.wavelength,
                0)  # wavelength error is not considered here:
            # it has already been considered in the pixel value (peak position)
            pixsize = self._exposure.header.pixelsizex
            self._dist = (pix * pixsize) / (2.0 * (wl * q / 4.0 / np.pi).arcsin()).tan()
        else:
            self._dist = None
            self.builder.get_object('distance_label').set_text('--')
            self.builder.get_object('savedistance_button').set_sensitive(True)
            return
        self.builder.get_object('distance_label').set_text(self._dist.tostring(plusminus=' \u00b1 ') + ' mm')
        self.builder.get_object('savedistance_button').set_sensitive(True)
        self.figpairscanvas.draw()

    def do_fit(self, curvetype: str):
        xmin, xmax = self.plot1d.get_zoom_xrange()
        assert isinstance(self._curve, Curve)
        try:
            x = self._curve.q
            y = self._curve.Intensity
            idx = (x >= xmin) & (x <= xmax)
            x = x[idx]
            y = y[idx]
            dy = self._curve.Error[idx]

            pos, hwhm, baseline, ampl = findpeak_single(x, y, dy)
            x_ = np.linspace(x.min(), x.max(), len(x) * 10)
            assert isinstance(x_, np.ndarray)
            if curvetype == 'Gauss':
                y_ = ampl * np.exp(-0.5 * (x_ - pos) ** 2 / hwhm ** 2) + baseline
            elif curvetype == 'Lorentz':
                y_ = ampl * hwhm ** 2 / (hwhm ** 2 + (pos - x_) ** 2) + baseline
            else:
                raise ValueError(curvetype)
            self.builder.get_object('uncalval_adjustment').set_value(pos.val)
            self.builder.get_object('uncalerr_adjustment').set_value(pos.err)
            self.plot1d.axes.plot(x_, y_, 'r-')
            self.plot1d.axes.text(pos.val, ampl.val + baseline.val, pos.tostring(plusminus=' \u00b1 '), ha='center',
                                  va='bottom')
            self.plot1d.canvas.draw()
        except Exception as exc:
            error_message(self.widget, 'Error while fitting', str(exc) + traceback.format_exc())

    def on_manualposition_selected(self, event):
        if (event.button == 1) and (event.inaxes == self.plot2d.axis):
            self.plot2d.canvas.mpl_disconnect(self._manualpickingconnection)
            self._manualpickingconnection = None
            self.on_findcenter((event.ydata, event.xdata))
            self.set_sensitive(True)
            self._cursor.clear(event)
            self._cursor = None
            stack = self.builder.get_object('plotstack')
            stack.child_set_property(stack.get_child_by_name('plot2d'), 'needs-attention', False)
            self.plot2d.replot()

    def on_findcenter(self, button: Union[Tuple[float, float], Gtk.Button]):
        if isinstance(button, tuple):
            posx, posy = button
        else:
            assert isinstance(button, Gtk.Button)
            method = self.builder.get_object('centeringmethod_selector').get_active_text()
            if method == 'Manual (click)':
                stack = self.builder.get_object('plotstack')
                stack.child_set_property(stack.get_child_by_name('plot2d'), 'needs-attention', True)
                self._cursor = Cursor(self.plot2d.axis, useblit=False, color='white', lw=1)
                self._manualpickingconnection = self.plot2d.canvas.mpl_connect(
                    'button_press_event', self.on_manualposition_selected)
                self.set_sensitive(False, 'Manual positioning active', ['input_box', 'close_button'])
                return
            elif method == 'Peak amplitude':
                assert isinstance(self._exposure, Exposure)
                xmin, xmax = self.plot1d.get_zoom_xrange()
                logger.debug('Peak amplitude method: xmin: {:f}. xmax: {:f}. Original beampos: {}, {}.'.format(
                    xmin, xmax, self._exposure.header.beamcenterx, self._exposure.header.beamcentery))
                posx, posy = findbeam_radialpeak(
                    self._exposure.intensity, [self._exposure.header.beamcenterx, self._exposure.header.beamcentery],
                    self._exposure.mask, xmin, xmax, drive_by='amplitude')
            elif method == 'Peak width':
                assert isinstance(self._exposure, Exposure)
                xmin, xmax = self.plot1d.get_zoom_xrange()
                posx, posy = findbeam_radialpeak(
                    self._exposure.intensity, [self._exposure.header.beamcenterx, self._exposure.header.beamcentery],
                    self._exposure.mask, xmin, xmax, drive_by='hwhm')
            elif method == 'Power-law goodness of fit':
                assert isinstance(self._exposure, Exposure)
                xmin, xmax = self.plot1d.get_zoom_xrange()
                posx, posy = findbeam_powerlaw(self._exposure.intensity, [self._exposure.header.beamcenterx,
                                                                          self._exposure.header.beamcentery],
                                               self._exposure.mask, xmin, xmax)
            else:
                raise ValueError(method)
        assert isinstance(self._exposure, Exposure)
        self._exposure.header.beamcenterx = posx
        self._exposure.header.beamcentery = posy
        self.builder.get_object('center_label').set_text('({}, {})'.format(posy, posx))
        self.plot2d.set_beampos(posx, posy)
        self.radial_average()
        self.builder.get_object('savecenter_button').set_sensitive(True)

    def on_savecenter(self, button):
        assert isinstance(self._exposure, Exposure)
        self.instrument.config['geometry']['beamposx'] = self._exposure.header.beamcenterx
        self.instrument.config['geometry']['beamposy'] = self._exposure.header.beamcentery
        self.instrument.save_state()
        logger.info('Beam center updated to ({}, {}) [(x, y) or (col, row)].'.format(
            self.instrument.config['geometry']['beamposy'],
            self.instrument.config['geometry']['beamposx']))
        self.instrument.save_state()
        button.set_sensitive(False)

    def on_replot(self, button):
        return self.radial_average()

    def on_savedistance(self, button):
        self.instrument.config['geometry']['dist_sample_det'] = self._dist.val
        self.instrument.config['geometry']['dist_sample_det.err'] = self._dist.err
        logger.info('Sample-to-detector distance updated to {:.4f} \u00b1 {:.4f} mm.'.format(
            self.instrument.config['geometry']['dist_sample_det'],
            self.instrument.config['geometry']['dist_sample_det.err']))
        self.instrument.save_state()
        button.set_sensitive(False)

    def radial_average(self):
        assert isinstance(self._exposure, Exposure)
        self._curve = self._exposure.radial_average(pixel=True)
        assert isinstance(self._curve, Curve)
        try:
            sampletitle = self._exposure.header.title
        except KeyError:
            sampletitle = 'no sample'
        self.plot1d.addcurve(
            self._curve.q, self._curve.Intensity, self._curve.qError, self._curve.Error,
            'FSN #{:d}: {}. Beam: ({}, {})'.format(
                self._exposure.header.fsn, sampletitle,
                self._exposure.header.beamcenterx,
                self._exposure.header.beamcentery), 'pixel')

    def on_loadexposure(self, exposureloader, im: Exposure):
        self.plot2d.set_image(im.intensity)
        self.plot2d.set_beampos(im.header.beamcenterx, im.header.beamcentery)
        self.plot2d.set_wavelength(im.header.wavelength)
        self.plot2d.set_distance(im.header.distance)
        self.plot2d.set_mask(im.mask)
        assert im.header.pixelsizex == im.header.pixelsizey
        self.plot2d.set_pixelsize(im.header.pixelsizex)
        self.builder.get_object('center_label').set_text('({}, {})'.format(
            im.header.beamcenterx,
            im.header.beamcentery))
        self._exposure = im
        self.radial_average()

    def on_loadexposure_error(self, exposureloader, message):
        self.error_message(message)
