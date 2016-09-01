import logging
import traceback
from typing import Optional

import numpy as np
import pkg_resources
from gi.repository import Gtk
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.figure import Figure
from matplotlib.scale import ScaleBase, register_scale
from matplotlib.ticker import AutoLocator, ScalarFormatter, NullFormatter
from matplotlib.transforms import Transform
from numpy import ma

from .builderwidget import BuilderWidget

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class PowerScale(ScaleBase):
    """Scales data by raising it to a given power.
    """
    name = 'power'

    def __init__(self, axis, **kwargs):
        super().__init__()
        self.exponent = kwargs.pop("exponent", 2)

    def get_transform(self):
        return self.PowerTransform(self.exponent)

    def set_default_locators_and_formatters(self, axis):
        axis.set_major_locator(AutoLocator())
        axis.set_major_formatter(ScalarFormatter())
        axis.set_minor_formatter(NullFormatter())

    def limit_range_for_scale(self, vmin, vmax, minpos):
        logger.debug('vmin: %g. vmax: %g. minpos: %g, eps: %g' % (vmin, vmax, minpos, 7 / 3 - 4 / 3 - 1))
        if vmin > vmax:
            return max(minpos, 7 / 3 - 4 / 3 - 1), max(vmax, max(minpos, 7 / 3 - 4 / 3 - 1))
        else:
            return (max(vmin, max(minpos, 7 / 3 - 4 / 3 - 1)),
                    max(vmax, max(minpos, 7 / 3 - 4 / 3 - 1)))

    # noinspection PyAbstractClass
    class PowerTransform(Transform):
        input_dims = 1
        output_dims = 1
        is_separable = True

        def __init__(self, exponent):
            super().__init__()
            self.exponent = exponent

        def transform_non_affine(self, a: np.ndarray):
            masked = ma.masked_where(a <= 0, a)
            if masked.mask.any():
                return ma.power(a, self.exponent)
            else:
                return np.power(a, self.exponent)

        def inverted(self):
            return type(self)(1.0 / self.exponent)


register_scale(PowerScale)


class PlotCurveWidget(BuilderWidget):
    def __init__(self, **kwargs):
        super().__init__(pkg_resources.resource_filename('cct', 'resource/glade/core_plotcurve.glade'),
                         'plotcurve')
        self._curves = []
        self._inhibit_replot = False
        self.fig = Figure(tight_layout=True)
        self.canvas = FigureCanvasGTK3Agg(self.fig)
        self.canvas.set_size_request(530, 350)
        self.axes = self.fig.add_subplot(1, 1, 1)
        self._toolbar = NavigationToolbar2GTK3(self.canvas, None)
        b = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('view-refresh', Gtk.IconSize.LARGE_TOOLBAR),
                           label='Redraw')
        b.set_tooltip_text('Redraw the curves')
        self._toolbar.insert(b, 9)
        b.connect('clicked', self.request_replot)
        self.widget.pack_start(self.canvas, True, True, 0)
        self.widget.pack_start(self._toolbar, False, True, 0)
        self.builder.get_object('dsigmadomega_yunit').get_children()[0].set_markup('cm<sup>-1</sup>sr<sup>-1</sup>')
        self.builder.get_object('dsigmadomegathickness_yunit').get_children()[0].set_markup('sr<sup>-1</sup>')
        self.builder.connect_signals(self)
        self.builder.get_object('dsigmadomega_yunit').set_active(True)
        self.widget.show_all()

    def addcurve(self, x, y, dx, dy, legend, xunits, pixelsize=None, dist=None, wavelength=None):
        if not self.builder.get_object('hold_toggle').get_active():
            self._curves = []
        curvedata = {'y': y, 'legend': legend}
        if dy is not None:
            curvedata['dy'] = dy
        if pixelsize is not None:
            curvedata['pixelsize'] = pixelsize
        if dist is not None:
            curvedata['dist'] = dist
        if wavelength is not None:
            curvedata['wavelength'] = wavelength

        # check the units of x. Save the x array in an appropriate place in curvedata,
        # then try to calculate other scales as well, if the needed parameters are present
        if xunits == 'pixel':
            curvedata['pixel'] = x
            curvedata['dpixel'] = dx
            try:
                curvedata.update(self._get_rho_up(curvedata['pixel'], curvedata['dpixel'], curvedata['pixelsize']))
                curvedata.update(self._get_tth_up(curvedata['rho'], curvedata['drho'], curvedata['dist']))
                curvedata.update(self._get_q_up(curvedata['tth'], curvedata['dtth'], curvedata['wavelength']))
            except KeyError:
                pass
        if xunits == 'detradius':
            curvedata['rho'] = x
            curvedata['drho'] = dx
            try:
                curvedata.update(self._get_tth_up(curvedata['rho'], curvedata['drho'], curvedata['dist']))
                curvedata.update(self._get_q_up(curvedata['tth'], curvedata['dtth'], curvedata['wavelength']))
            except KeyError:
                pass
            try:
                curvedata.update(self._get_pixel_down(curvedata['rho'], curvedata['drho'], curvedata['pixelsize']))
            except KeyError:
                pass
        elif xunits == 'twotheta':
            curvedata['tth'] = x
            curvedata['dtth'] = dx
            try:
                curvedata.update(self._get_q_up(curvedata['tth'], curvedata['dtth'], curvedata['wavelength']))
            except KeyError:
                pass
            try:
                curvedata.update(self._get_rho_down(curvedata['tth'], curvedata['dtth'], curvedata['dist']))
                curvedata.update(self._get_pixel_down(curvedata['rho'], curvedata['drho'], curvedata['pixelsize']))
            except KeyError:
                pass
        elif xunits == 'q':
            curvedata['q'] = x
            curvedata['dq'] = dx
            try:
                curvedata.update(self._get_tth_down(curvedata['q'], curvedata['dq'], curvedata['wavelength']))
                curvedata.update(self._get_rho_down(curvedata['tth'], curvedata['dtth'], curvedata['dist']))
                curvedata.update(self._get_pixel_down(curvedata['rho'], curvedata['drho'], curvedata['pixelsize']))
            except KeyError:
                pass
        self._curves.append(curvedata)
        self._validate_entries()
        self.request_replot(None)

    def _validate_entries(self):
        self.builder.get_object('pixels_xunit').set_sensitive(all(['pixel' in c for c in self._curves]))
        self.builder.get_object('radius_xunit').set_sensitive(all(['rho' in c for c in self._curves]))
        self.builder.get_object('twotheta_xunit').set_sensitive(all(['tth' in c for c in self._curves]))
        self.builder.get_object('q_xunit').set_sensitive(all(['q' in c for c in self._curves]))
        for objname in ['q_xunit', 'twotheta_xunit', 'radius_xunit', 'pixels_xunit']:
            if self.builder.get_object(objname).get_sensitive():
                self.builder.get_object(objname).set_active(True)
                break

        qactive = self.builder.get_object('q_xunit').get_active()
        self.builder.get_object('guinier3d_type').set_sensitive(qactive)
        self.builder.get_object('guinier2d_type').set_sensitive(qactive)
        self.builder.get_object('guinier1d_type').set_sensitive(qactive)
        self.builder.get_object('kratky_type').set_sensitive(qactive)
        self.builder.get_object('porod_type').set_sensitive(qactive)
        if any([self.builder.get_object(on).get_active() for on in
                ['guinier3d_type', 'guinier2d_type', 'guinier1d_type',
                 'kratky_type', 'porod_type']]) and not qactive:
            self.builder.get_object('loglog_type').set_active(True)
        if not any([self.builder.get_object(on).get_active() for on in
                    ['arbunits_yunit', 'dsigmadomega_yunit', 'dsigmadomegathickness_yunit']]):
            self.builder.get_object('dsigmadomega_yunit').set_active(True)

    def request_replot(self, widget: Optional[Gtk.RadioMenuItem]):
        try:
            if isinstance(widget, Gtk.RadioMenuItem) and not widget.get_active():
                # avoid plotting twice when another radio item has been selected
                logger.debug('Not plotting (yet)')
                return
            self.axes.clear()
            if self.builder.get_object('pixels_xunit').get_active():
                xkey = 'pixel'
                dxkey = 'dpixel'
                xlabel = 'Distance from origin (pixel)'
            elif self.builder.get_object('radius_xunit').get_active():
                xkey = 'rho'
                dxkey = 'drho'
                xlabel = 'Distance from origin (mm)'
            elif self.builder.get_object('twotheta_xunit').get_active():
                xkey = 'tth'
                dxkey = 'dtth'
                xlabel = 'Scattering angle ($^\circ$)'
            elif self.builder.get_object('q_xunit').get_active():
                if self.builder.get_object('guinier3d_type').get_active():
                    for c in self._curves:
                        assert isinstance(c, dict)
                        self.axes.errorbar(c['q'], c['y'], c['dy'], c['dq'], label=c['legend'])
                        c['_x'] = c['q']
                        c['_y'] = c['y']
                    self.axes.set_xscale('power', exponent=2)
                    self.axes.set_yscale('log')
                    if self.builder.get_object('arbunits_yunit').get_active():
                        self.axes.yaxis.set_label_text('Intensity (arb. units)')
                    elif self.builder.get_object('dsigmadomega_yunit').get_active():
                        self.axes.yaxis.set_label_text('$d\sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
                    elif self.builder.get_object('dsigmadomegathickness_yunit').get_active():
                        self.axes.yaxis.set_label_text('$d\sigma/d\Omega\\times t$ (sr$^{-1}$)')
                    else:
                        assert False
                    if self.builder.get_object('legend_toggle').get_active():
                        self.axes.legend(loc='best', fontsize='small')
                    self.axes.xaxis.set_label_text('q (nm${-1}$)')
                    self.canvas.draw()
                    return
                elif self.builder.get_object('guinier2d_type').get_active():
                    for c in self._curves:
                        assert isinstance(c, dict)
                        y = c['y'] * c['q']
                        if c['dy'] is not None and c['dq'] is not None:
                            dy = (c['dq'] ** 2 * c['y'] ** 2 + c['dy'] ** 2 * c['q'] ** 2) ** 0.5
                        elif c['dy'] is not None:
                            dy = c['dy'] * c['q']
                        elif c['dq'] is not None:
                            dy = c['dq'] * c['y']
                        else:
                            dy = None
                        self.axes.errorbar(c['q'], y, dy, c['dq'], label=c['legend'])
                        c['_x'] = c['q']
                        c['_y'] = y
                    self.axes.set_xscale('power', exponent=2)
                    self.axes.set_yscale('log')
                    if self.builder.get_object('arbunits_yunit').get_active():
                        self.axes.yaxis.set_label_text('Intensity*q (arb. units * nm$^{-1})')
                    elif self.builder.get_object('dsigmadomega_yunit').get_active():
                        self.axes.yaxis.set_label_text('$d\sigma/d\Omega\cdot q$ (cm$^{-1}$ sr$^{-1}$ nm$^{-1}$)')
                    elif self.builder.get_object('dsigmadomegathickness_yunit').get_active():
                        self.axes.yaxis.set_label_text('$d\sigma/d\Omega\cdot t\cdot q$ (sr$^{-1}$ nm$^{-1}$)')
                    else:
                        assert False
                    if self.builder.get_object('legend_toggle').get_active():
                        self.axes.legend(loc='best', fontsize='small')
                    self.axes.xaxis.set_label_text('q (nm${-1}$)')
                    self.canvas.draw()
                    return
                elif self.builder.get_object('guinier1d_type').get_active():
                    for c in self._curves:
                        assert isinstance(c, dict)
                        y = c['y'] * c['q'] ** 2
                        if c['dy'] is not None and c['dq'] is not None:
                            dy = (c['dq'] ** 2 * c['y'] ** 2 * 4 * c['q'] ** 2 + c['dy'] ** 2 * c['q'] ** 4) ** 0.5
                        elif c['dy'] is not None:
                            dy = c['dy'] * c['q'] ** 2
                        elif c['dq'] is not None:
                            dy = c['dq'] * 2 * c['q'] ** 2 * c['y']
                        else:
                            dy = None
                        self.axes.errorbar(c['q'], y, dy, c['dq'], label=c['legend'])
                        c['_x'] = c['q']
                        c['_y'] = y
                    self.axes.set_xscale('power', exponent=2)
                    self.axes.set_yscale('log')
                    if self.builder.get_object('arbunits_yunit').get_active():
                        self.axes.yaxis.set_label_text('Intensity*q$^2$ (arb. units * nm$^{-2})')
                    elif self.builder.get_object('dsigmadomega_yunit').get_active():
                        self.axes.yaxis.set_label_text('$d\sigma/d\Omega\cdot q^2$ (cm$^{-1}$ sr$^{-1}$ nm$^{-2}$)')
                    elif self.builder.get_object('dsigmadomegathickness_yunit').get_active():
                        self.axes.yaxis.set_label_text('$d\sigma/d\Omega\cdot t\cdot q^2$ (sr$^{-1}$ nm$^{-2}$)')
                    else:
                        assert False
                    if self.builder.get_object('legend_toggle').get_active():
                        self.axes.legend(loc='best', fontsize='small')
                    self.axes.xaxis.set_label_text('q (nm${-1}$)')
                    self.canvas.draw()
                    return
                elif self.builder.get_object('kratky_type').get_active():
                    for c in self._curves:
                        assert isinstance(c, dict)
                        y = c['y'] * c['q'] ** 2
                        if c['dy'] is not None and c['dq'] is not None:
                            dy = (c['dq'] ** 2 * c['y'] ** 2 * 4 * c['q'] ** 2 + c['dy'] ** 2 * c['q'] ** 4) ** 0.5
                        elif c['dy'] is not None:
                            dy = c['dy'] * c['q'] ** 2
                        elif c['dq'] is not None:
                            dy = c['dq'] * 2 * c['q'] ** 2 * c['y']
                        else:
                            dy = None
                        self.axes.errorbar(c['q'], y, dy, c['dq'], label=c['legend'])
                        c['_x'] = c['q']
                        c['_y'] = y
                    self.axes.set_xscale('linear')
                    self.axes.set_yscale('linear')
                    if self.builder.get_object('arbunits_yunit').get_active():
                        self.axes.yaxis.set_label_text('Intensity*q$^2$ (arb. units * nm$^{-2})')
                    elif self.builder.get_object('dsigmadomega_yunit').get_active():
                        self.axes.yaxis.set_label_text('$d\sigma/d\Omega\cdot q^2$ (cm$^{-1}$ sr$^{-1}$ nm$^{-2}$)')
                    elif self.builder.get_object('dsigmadomegathickness_yunit').get_active():
                        self.axes.yaxis.set_label_text('$d\sigma/d\Omega\cdot t\cdot q^2$ (sr$^{-1}$ nm$^{-2}$)')
                    else:
                        assert False
                    if self.builder.get_object('legend_toggle').get_active():
                        self.axes.legend(loc='best', fontsize='small')
                    self.axes.xaxis.set_label_text('q (nm${-1}$)')
                    self.canvas.draw()
                    return
                elif self.builder.get_object('porod_type').get_active():
                    for c in self._curves:
                        assert isinstance(c, dict)
                        y = c['y'] * c['q'] ** 4
                        if c['dy'] is not None and c['dq'] is not None:
                            dy = (c['dq'] ** 2 * c['y'] ** 2 * 16 * c['q'] ** 6 + c['dy'] ** 2 * c['q'] ** 8) ** 0.5
                        elif c['dy'] is not None:
                            dy = c['dy'] * c['q'] ** 4
                        elif c['dq'] is not None:
                            dy = c['dq'] * 4 * c['q'] ** 6 * c['y']
                        else:
                            dy = None
                        self.axes.errorbar(c['q'], y, dy, c['dq'], label=c['legend'])
                        c['_x'] = c['q']
                        c['_y'] = y
                    self.axes.set_xscale('linear')
                    self.axes.set_yscale('power', exponent=4)
                    if self.builder.get_object('arbunits_yunit').get_active():
                        self.axes.yaxis.set_label_text('Intensity*q$^4$ (arb. units * nm$^{-4})')
                    elif self.builder.get_object('dsigmadomega_yunit').get_active():
                        self.axes.yaxis.set_label_text('$d\sigma/d\Omega\cdot q^4$ (cm$^{-1}$ sr$^{-1}$ nm$^{-4}$)')
                    elif self.builder.get_object('dsigmadomegathickness_yunit').get_active():
                        self.axes.yaxis.set_label_text('$d\sigma/d\Omega\cdot t\cdot q^4$ (sr$^{-1}$ nm$^{-4}$)')
                    else:
                        assert False
                    if self.builder.get_object('legend_toggle').get_active():
                        self.axes.legend(loc='best', fontsize='small')
                    self.axes.xaxis.set_label_text('q (nm${-1}$)')
                    self.canvas.draw()
                    return
                else:
                    xkey = 'q'
                    dxkey = 'dq'
                    xlabel = 'q (nm$^{-1}$)'
            else:
                assert False

            for c in self._curves:
                assert isinstance(c, dict)
                self.axes.errorbar(c[xkey], c['y'], c['dy'], c[dxkey], label=c['legend'])
                c['_x'] = c[xkey]
                c['_y'] = c['y']
            if self.builder.get_object('loglog_type').get_active():
                self.axes.set_xscale('log')
                self.axes.set_yscale('log')
            elif self.builder.get_object('logx_type').get_active():
                self.axes.set_xscale('log')
                self.axes.set_yscale('linear')
            elif self.builder.get_object('logy_type').get_active():
                self.axes.set_xscale('linear')
                self.axes.set_yscale('log')
            elif self.builder.get_object('linlin_type').get_active():
                self.axes.set_xscale('linear')
                self.axes.set_yscale('linear')
            if self.builder.get_object('arbunits_yunit').get_active():
                self.axes.yaxis.set_label_text('Intensity (arb. units)')
            elif self.builder.get_object('dsigmadomega_yunit').get_active():
                self.axes.yaxis.set_label_text('$d\sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
            elif self.builder.get_object('dsigmadomegathickness_yunit').get_active():
                self.axes.yaxis.set_label_text('$d\sigma/d\Omega\\times t$ (sr$^{-1}$)')
            else:
                assert False
            self.axes.xaxis.set_label_text(xlabel)
            if self.builder.get_object('legend_toggle').get_active():
                self.axes.legend(loc='best', fontsize='small')
            self.canvas.draw()
            return
        except Exception as exc:
            logger.error('Error while plotting one-dimensional curve: %s ' % str(exc) + traceback.format_exc())
            self.axes.clear()
            self.canvas.draw()

    @staticmethod
    def _get_pixel_down(rho, drho, pixelsize):
        dic = {'pixel': rho / pixelsize, 'dpixel': None}
        if drho is not None:
            dic['dpixel'] = drho / pixelsize
        return dic

    @staticmethod
    def _get_rho_up(pix, dpix, pixelsize):
        dic = {'rho': pix * pixelsize, 'drho': None}
        if dpix is not None:
            dic['drho'] = dpix * pixelsize
        return dic

    @staticmethod
    def _get_rho_down(tth, dtth, dist):
        dic = {'rho': np.tan(tth * np.pi / 180) * dist, 'drho': None}
        if dtth is not None:
            dic['drho'] = dtth * np.pi / 180 * (1 + np.tan(tth * np.pi / 180))
        return dic

    @staticmethod
    def _get_tth_up(rho, drho, dist):
        dic = {'tth': np.arctan(rho / dist) * 180 / np.pi, 'dtth': None}
        if drho is not None:
            dic['dtth'] = 1 / (1 + rho ** 2 / dist ** 2) * 180 / np.pi * drho / dist
        return dic

    @staticmethod
    def _get_tth_down(q, dq, wavelength):
        dic = {'tth': 2 * 180 / np.pi * np.arcsin(q * wavelength / 4 / np.pi), 'dtth': None}
        if dq is not None:
            dic['dtth'] = 2 * 180 / np.pi / (1 - (q * wavelength / 4 / np.pi) ** 2) ** 0.5 * dq * wavelength / 4 / np.pi
        return dic

    @staticmethod
    def _get_q_up(tth, dtth, wavelength):
        dic = {'q': 4 * np.pi * np.sin(0.5 * np.pi / 180 * tth) / wavelength, 'dq': None}
        if dtth is not None:
            dic['dq'] = 4 * np.pi / wavelength * np.cos(0.5 * np.pi / 180 * tth) * 0.5 * np.pi / 180 * dtth
        return dic

    def get_zoom_xrange(self):
        xminlim, xmaxlim, yminlim, ymaxlim = self.axes.axis()
        xmin = xminlim
        xmax = xmaxlim
        for c in self._curves:
            assert isinstance(c, dict)
            idx = (xminlim <= c['_x']) & (xmaxlim >= c['_x']) & (yminlim <= c['_y']) & (ymaxlim >= c['_y'])
            xmin = max(xmin, np.min(c['_x'][idx]))
            xmax = min(xmax, np.max(c['_x'][idx]))
        return xmin, xmax


class PlotCurveWindow(PlotCurveWidget):
    instancelist = []

    def __init__(self, **kwargs):
        PlotCurveWidget.__init__(self, **kwargs)
        self._window = Gtk.Window()
        self._window.add(self.widget)
        self._window.connect('destroy', self.on_destroy)
        self._window.connect('focus-in-event', self.on_focus_in)
        self._window.show_all()
        PlotCurveWindow.instancelist.append(self)

    def on_destroy(self, window):
        PlotCurveWindow.instancelist.remove(self)
        self.widget.destroy()
        del self._window
        return False

    def on_focus_in(self, window, event):
        PlotCurveWindow.instancelist.remove(self)
        PlotCurveWindow.instancelist.append(self)

    @classmethod
    def get_latest_window(cls):
        if not cls.instancelist:
            return cls()
        else:
            return cls.instancelist[-1]
