import logging
import traceback

import numpy as np
from gi.repository import Gtk
from matplotlib.widgets import Cursor
from sastool.misc.basicfit import findpeak_single
from sastool.misc.easylsq import nonlinear_odr
from sastool.utils2d.centering import findbeam_radialpeak, findbeam_powerlaw
from sastool.utils2d.integrate import radint_fullq_errorprop

from ...core.utils.errorvalue import ErrorValue

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from ..core.plotcurve import PlotCurveWidget
from ..core.plotimage import PlotImageWidget
from ..core.toolwindow import ToolWindow, error_message
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
from matplotlib.figure import Figure


def qfrompix(pix, pixelsize, beampos, alpha, wavelength, dist):
    pixsizedivdist = pixelsize / dist
    catethus_near = 1 + pixsizedivdist * (pix - beampos) * np.cos(alpha)
    catethus_opposite = pixsizedivdist * (pix - beampos) * np.sin(alpha)
    twotheta = np.arctan2(catethus_opposite, catethus_near)
    return 4 * np.pi * np.sin(0.5 * twotheta) / wavelength


class Calibration(ToolWindow):
    def _init_gui(self, *args):
        self._plot2d = PlotImageWidget()
        self._builder.get_object('figbox_2d').pack_start(self._plot2d._widget, True, True, 0)
        self._plot1d = PlotCurveWidget()
        self._builder.get_object('figbox_1d').pack_start(self._plot1d._widget, True, True, 0)
        self._figpairs = Figure(tight_layout=True)
        self._figpairscanvas = FigureCanvasGTK3Agg(self._figpairs)
        self._builder.get_object('figbox_distcalib').pack_start(self._figpairscanvas, True, True, 0)
        self._figpairstoolbox = NavigationToolbar2GTK3(self._figpairscanvas, self._window)
        self._builder.get_object('figbox_distcalib').pack_start(self._figpairstoolbox, False, True, 0)
        self._figpairsaxes = self._figpairs.add_subplot(1, 1, 1)
        tv = self._builder.get_object('pairview')
        tc = Gtk.TreeViewColumn('Uncalibrated', Gtk.CellRendererText(), text=0)
        tv.append_column(tc)
        tc = Gtk.TreeViewColumn('Calibrated', Gtk.CellRendererText(), text=1)
        tv.append_column(tc)
        csel = self._builder.get_object('calibrant_selector')
        csel.remove_all()
        for calibrant in self._instrument.config['calibrants']:
            csel.append_text(calibrant)
        csel.set_active(0)
        self.on_calibrant_selector_changed(csel)
        self.on_overridemask_toggled(self._builder.get_object('mask_check'))

    def on_map(self, window):
        ps = self._builder.get_object('prefix_combo')
        previous_active = ps.get_active_text()
        ps.remove_all()
        for i, p in enumerate(sorted(self._instrument.filesequence.get_prefixes())):
            ps.append_text(p)
            if p == previous_active:
                ps.set_active(i)
        if previous_active is None:
            ps.set_active(0)

    def on_calibrant_selector_changed(self, csel):
        peaksel = self._builder.get_object('peak_selector')
        peaksel.remove_all()
        for peak in sorted(self._instrument.config['calibrants'][csel.get_active_text()]):
            peaksel.append_text(peak)
        peaksel.set_active(0)

    def on_addpair(self, button):
        model = self._builder.get_object('pairstore')
        calval = self._builder.get_object('calval_adjustment').get_value()
        calerr = self._builder.get_object('calerr_adjustment').get_value()
        uncalval = self._builder.get_object('uncalval_adjustment').get_value()
        uncalerr = self._builder.get_object('uncalerr_adjustment').get_value()
        cal = ErrorValue(calval, calerr)
        uncal = ErrorValue(uncalval, uncalerr)
        model.append((uncal.tostring(plusminus=' \u00b1 '), cal.tostring(plusminus=' \u00b1 '), uncalval, uncalerr,
                      calval, calerr))
        self._replot_calpairs()

    def _replot_calpairs(self):
        uncalval = []
        uncalerr = []
        calval = []
        calerr = []
        for row in self._builder.get_object('pairstore'):
            uncalval.append(row[2])
            uncalerr.append(row[3])
            calval.append(row[4])
            calerr.append(row[5])
        self._figpairsaxes.clear()
        self._figpairsaxes.errorbar(uncalval, calval, calerr, uncalerr, '.')
        self._figpairsaxes.set_xlabel('Uncalibrated (pixel)')
        self._figpairsaxes.set_ylabel('Calibrated (nm$^{-1}$)')
        self._figpairscanvas.draw()
        self.do_getdistance()

    def on_removepair(self, button):
        model, it = self._builder.get_object('pairview').get_selection().get_selected()
        if it is None:
            return
        model.remove(it)
        self._replot_calpairs()

    def on_exportpairs(self, button):
        pass

    def on_overridemask_toggled(self, checkbutton):
        self._builder.get_object('maskchooser').set_sensitive(checkbutton.get_active())

    def on_setfromcalibrant(self, button):
        csel = self._builder.get_object('calibrant_selector').get_active_text()
        psel = self._builder.get_object('peak_selector').get_active_text()
        self._builder.get_object('calval_adjustment').set_value(
            self._instrument.config['calibrants'][csel][psel]['val'])
        self._builder.get_object('calerr_adjustment').set_value(
            self._instrument.config['calibrants'][csel][psel]['err'])
        logger.debug('Set from calibrant.')

    def on_fitlorentz(self, button):
        self.do_fit('Lorentz')

    def on_fitgauss(self, button):
        self.do_fit('Gauss')

    def do_getdistance(self):
        model = self._builder.get_object('pairstore')
        uncalval = np.array([row[2] for row in model])
        uncalerr = np.array([row[3] for row in model])
        calval = np.array([row[4] for row in model])
        calerr = np.array([row[5] for row in model])
        logger.debug('Uncalval: ' + str(uncalval))
        logger.debug('Uncalerr: ' + str(uncalerr))
        logger.debug('Calval: ' + str(calval))
        logger.debug('Calerr: ' + str(calerr))
        if len(uncalval) > 1:
            fitfunc = lambda pix, dist: qfrompix(pix, pixelsize=self._params['geometry']['pixelsize'],
                                                 beampos=0, alpha=np.pi * 0.5,
                                                 wavelength=self._params['geometry']['wavelength'],
                                                 dist=dist)
            self._dist, stat = nonlinear_odr(uncalval, calval, uncalerr, calerr, fitfunc, [100])
            x = np.linspace(uncalval.min(), uncalval.max(), len(uncalval) * 100)
            self._figpairsaxes.plot(x, fitfunc(x, self._dist.val), 'r-')
        elif len(uncalval) == 1:
            q = ErrorValue(float(calval[0]), float(calerr[0]))
            pix = ErrorValue(float(uncalval[0]), float(uncalerr[0]))
            wl = ErrorValue(self._params['geometry']['wavelength'],
                            self._params['geometry']['wavelength.err'])
            pixsize = self._params['geometry']['pixelsize']
            self._dist = (pix * pixsize) / (2 * (wl * q / 4 / np.pi).arcsin()).tan()
        else:
            self._dist = None
            self._builder.get_object('distance_label').set_text('--')
            self._builder.get_object('savedistance_button').set_sensitive(True)
            return
        self._builder.get_object('distance_label').set_text(self._dist.tostring(plusminus=' \u00b1 ') + ' mm')
        self._builder.get_object('savedistance_button').set_sensitive(True)
        self._figpairscanvas.draw()

    def do_fit(self, curvetype):
        xmin, xmax, ymin, ymax = self._plot1d._axes.axis()
        try:
            x = self._curve['x']
            y = self._curve['y']
            idx = (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax)
            x = x[idx]
            y = y[idx]
            dx = self._curve['dx'][idx]
            dy = self._curve['dy'][idx]
            pos, hwhm, baseline, ampl = findpeak_single(x, y, dy)
            x_ = np.linspace(x.min(), x.max(), len(x) * 10)
            if curvetype == 'Gauss':
                y_ = ampl * np.exp(-0.5 * (x_ - pos) ** 2 / hwhm ** 2) + baseline
            elif curvetype == 'Lorentz':
                y_ = ampl * hwhm ** 2 / (hwhm ** 2 + (pos - x_) ** 2) + baseline
            else:
                raise NotImplementedError(curvetype)
            self._builder.get_object('uncalval_adjustment').set_value(pos.val)
            self._builder.get_object('uncalerr_adjustment').set_value(pos.err)
            self._plot1d._axes.plot(x_, y_, 'r-')
            self._plot1d._axes.text(pos.val, ampl.val + baseline.val, pos.tostring(plusminus=' \u00b1 '), ha='center',
                                    va='bottom')
            self._plot1d._canvas.draw()
        except Exception as exc:
            error_message(self._window, 'Error while fitting', str(exc) + traceback.format_exc())

    def on_manualposition_selected(self, event):
        if (event.button == 1) and (event.inaxes == self._plot2d._axis):
            try:
                self._plot2d._canvas.mpl_disconnect(self._manualpickingconnection)
                del self._manualpickingconnection
            except AttributeError:
                pass
            self.on_findcenter((event.ydata, event.xdata))
            self._make_sensitive()
            self._cursor.clear(event)
            del self._cursor
            stack = self._builder.get_object('plotstack')
            stack.child_set_property(stack.get_child_by_name('plot2d'), 'needs-attention', False)
            self._plot2d._replot()

    def on_findcenter(self, button):
        if isinstance(button, tuple):
            posx, posy = button
        else:
            method = self._builder.get_object('centeringmethod_selector').get_active_text()
            if method == 'Manual (click)':
                stack = self._builder.get_object('plotstack')
                stack.child_set_property(stack.get_child_by_name('plot2d'), 'needs-attention', True)
                self._cursor = Cursor(self._plot2d._axis, useblit=False, color='white', lw=1)
                self._manualpickingconnection = self._plot2d._canvas.mpl_connect('button_press_event',
                                                                                 self.on_manualposition_selected)
                self._make_insensitive('Manual positioning active', widgets=['input_box', 'close_button'])
                return
            elif method == 'Peak amplitude':
                xmin, xmax = self._plot1d._axes.axis()[:2]
                posx, posy = findbeam_radialpeak(self._data, [self._params['geometry']['beamposx'],
                                                              self._params['geometry']['beamposy']],
                                                 self._mask, xmin, xmax, drive_by='amplitude')
            elif method == 'Peak width':
                xmin, xmax = self._plot1d._axes.axis()[:2]
                posx, posy = findbeam_radialpeak(self._data, [self._params['geometry']['beamposx'],
                                                              self._params['geometry']['beamposy']],
                                                 self._mask, xmin, xmax, drive_by='amplitude')
            elif method == 'Power-law goodness of fit':
                xmin, xmax = self._plot1d._axes.axis()[:2]
                posx, posy = findbeam_powerlaw(self._data, [self._params['geometry']['beamposx'],
                                                            self._params['geometry']['beamposy']],
                                               self._mask, xmin, xmax)
            else:
                raise NotImplementedError(method)
        self._params['geometry']['beamposx'] = posx
        self._params['geometry']['beamposy'] = posy
        self._builder.get_object('center_label').set_text('(%.3f, %.3f)' % (posy, posx))
        self._plot2d.set_beampos(posx, posy)
        self._radial_average()
        self._builder.get_object('savecenter_button').set_sensitive(True)

    def on_savecenter(self, button):
        self._instrument.config['geometry']['beamposx'] = self._params['geometry']['beamposx']
        self._instrument.config['geometry']['beamposy'] = self._params['geometry']['beamposy']
        self._instrument.save_state()
        logger.info('Beam center updated to (%.3f, %.3f) [(x, y) or (col, row)].' % (
        self._instrument.config['geometry']['beamposy'],
        self._instrument.config['geometry']['beamposx']))
        button.set_sensitive(False)

    def on_savedistance(self, button):
        self._instrument.config['geometry']['dist_sample_det'] = self._dist.val
        self._instrument.config['geometry']['dist_sample_det.err'] = self._dist.err
        logger.info('Sample-to-detector distance updated to %.4f \u00b1 %.4f mm.' % (
        self._instrument.config['geometry']['dist_sample_det'],
        self._instrument.config['geometry']['dist_sample_det.err']))
        button.set_sensitive(False)

    def _radial_average(self):
        pix, pixerror, Intensity, Error, Area = radint_fullq_errorprop(
            self._data, self._data ** 0.5, self._params['geometry']['wavelength'],
            self._params['geometry']['wavelength.err'], self._params['geometry']['dist_sample_det'],
            self._params['geometry']['dist_sample_det.err'], self._params['geometry']['pixelsize'],
            self._params['geometry']['pixelsize'], self._params['geometry']['beamposx'], 0.0,
            self._params['geometry']['beamposy'], 0.0, (~self._mask).astype(np.uint8), abscissa_kind=3)
        try:
            sampletitle = self._params['sample']['title']
        except KeyError:
            sampletitle = 'no sample'
        self._plot1d.addcurve(pix, Intensity, pixerror, Error, 'FSN #%d: %s. Beam: (%.3f, %.3f)' % (
            self._params['fsn'], sampletitle, self._params['geometry']['beamposy'],
            self._params['geometry']['beamposx']), 'pixel')
        self._curve = {'x': pix, 'dx': pixerror, 'y': Intensity, 'dy': Error}

    def on_loadexposure(self, button):
        self._data, self._mask, self._params = self._instrument.filesequence.load_exposure(
            self._builder.get_object('prefix_combo').get_active_text(),
            self._builder.get_object('fsn_adjustment').get_value())
        if self._builder.get_object('mask_check').get_active():
            self._mask = self._instrument.filesequence.get_mask(self._builder.get_object('maskchooser').get_filename())
        self._plot2d.set_image(self._data)
        self._plot2d.set_beampos(self._params['geometry']['beamposx'], self._params['geometry']['beamposy'])
        self._plot2d.set_wavelength(self._params['geometry']['wavelength'])
        self._plot2d.set_distance(self._params['geometry']['truedistance'])
        self._plot2d.set_mask(self._mask)
        self._plot2d.set_pixelsize(self._params['geometry']['pixelsize'])
        self._builder.get_object('center_label').set_text('(%.3f, %.3f)' % (self._params['geometry']['beamposy'],
                                                                            self._params['geometry']['beamposx']))
        self._radial_average()
