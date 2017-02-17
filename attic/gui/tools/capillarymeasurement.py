import numpy as np
from gi.repository import Gtk, GLib
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.figure import Figure
from sastool.misc.basicfit import findpeak_single
from sastool.misc.errorvalue import ErrorValue

from ..core.dialogs import error_message
from ..core.functions import update_comboboxtext_choices, savefiguretoclipboard
from ..core.toolwindow import ToolWindow


class CapillaryMeasurement(ToolWindow):
    def __init__(self, *args, **kwargs):
        self._scandata = None
        self._negpeak_text = None
        self._negpeak_curve = None
        self._pospeak_text = None
        self._pospeak_curve = None
        self._scancurve = None
        self._negpeak_pos = None
        self._pospeak_pos = None
        self._thickness = None
        self._position = None
        self._xdata = None
        self._ydata = None
        self._samplestoreconnection = None
        self.fig = None
        self.axes = None
        self.canvas = None
        self.toolbar = None
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        fb = self.builder.get_object('figbox')
        self.fig = Figure(tight_layout=True)
        self.axes = self.fig.add_subplot(1, 1, 1)
        self.canvas = FigureCanvasGTK3Agg(self.fig)
        self.canvas.set_size_request(600, -1)
        fb.pack_start(self.canvas, True, True, 0)
        self.toolbar = NavigationToolbar2GTK3(self.canvas, self.widget)
        fb.pack_start(self.toolbar, False, True, 0)
        b = Gtk.ToolButton.new(Gtk.Image.new_from_icon_name('view-refresh', Gtk.IconSize.LARGE_TOOLBAR), 'Redraw')
        self.toolbar.insert(b, 9)
        b.connect('clicked', lambda button: self.redraw())
        b = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('edit-copy', Gtk.IconSize.LARGE_TOOLBAR),
                           label='Copy')
        b.set_tooltip_text('Copy the image to the clipboard')
        b.connect('clicked', lambda b_, f=self.fig: savefiguretoclipboard(f))
        self.toolbar.insert(b, 9)

    def clearfigure(self, full=False):
        for attr in ['_negpeak_text', '_negpeak_curve', '_pospeak_text', '_pospeak_curve', '_scancurve']:
            try:
                getattr(self, attr).remove()
            except AttributeError:
                pass
            finally:
                setattr(self, attr, None)
        if full:
            assert isinstance(self.fig, Figure)
            self.fig.clear()
            self.axes = self.fig.add_subplot(1, 1, 1)

    def redraw(self):
        if self._scandata is None:
            return True
        self.clearfigure()
        x = self._scandata['signals'][0]
        y = self.builder.get_object('signalname_combo').get_active_text()
        if y is None:
            return
        self._xdata = self._scandata['data'][x]
        self._ydata = self._scandata['data'][y]
        ylabel = y
        if self.builder.get_object('plotderivative_checkbutton').get_active():
            self._ydata = (self._ydata[1:] - self._ydata[:-1]) / (self._xdata[1:] - self._xdata[:-1])
            self._xdata = 0.5 * (self._xdata[1:] + self._xdata[:-1])
            ylabel = 'Derivative of ' + y
        self._scancurve = self.axes.plot(self._xdata, self._ydata, 'b.-', label=ylabel)[0]
        self.axes.xaxis.set_label_text(x)
        self.axes.yaxis.set_label_text(ylabel)
        self.axes.grid(True, which='both')
        self.axes.set_title(self._scandata['comment'])
        self.canvas.draw_idle()
        return True

    # noinspection PyUnusedLocal
    def on_reload_clicked(self, button):
        GLib.idle_add(lambda si=self.builder.get_object('scanindex_spin').get_value_as_int(): self.load_scan(si))

    def on_scanindex_change(self, spinbutton):
        GLib.idle_add(lambda si=spinbutton.get_value_as_int(): self.load_scan(si))

    def load_scan(self, scanidx):
        try:
            self._scandata = self.instrument.services['filesequence'].load_scan(scanidx)
        except KeyError:
            self.error_message('Scan {:d} not found in file {}'.format(
                scanidx,
                self.instrument.services['filesequence'].get_scanfile()))
            return
        update_comboboxtext_choices(self.builder.get_object('signalname_combo'),
                                    self._scandata['signals'][2:])
        for attr in ['_left', '_right', '_thickness', '_position']:
            setattr(self, attr, None)
        self.builder.get_object('leftval_adjustment').set_value(0)
        self.builder.get_object('lefterr_adjustment').set_value(0)
        self.builder.get_object('rightval_adjustment').set_value(0)
        self.builder.get_object('righterr_adjustment').set_value(0)
        self.builder.get_object('thickness_label').set_text('--')
        self.builder.get_object('position_label').set_text('--')
        self.builder.get_object('saveposition_button').set_sensitive(False)
        self.builder.get_object('savethickness_button').set_sensitive(False)
        self.builder.get_object('saveall_button').set_sensitive(False)
        self.clearfigure(full=True)
        self.redraw()
        return False

    # noinspection PyUnusedLocal
    def on_signalname_changed(self, combo):
        self.redraw()

    # noinspection PyUnusedLocal
    def on_plotderivative_changed(self, combo):
        self.redraw()
        return True

    def do_fit(self, left):
        if (self._xdata is None) or (self._ydata is None):
            return
        xmin, xmax, ymin, ymax = self.axes.axis()
        x = self._xdata
        y = self._ydata
        idx = (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax)
        x = x[idx]
        y = y[idx]
        if left:
            signs = (-1,)
        else:
            signs = (1,)
        try:
            pos, hwhm, y0, amplitude = findpeak_single(x, y, signs=signs, curve='Lorentz')
        except ValueError:
            self.error_message('Fitting error, not enough points in the selected range.')
            return
        x = np.linspace(x.min(), x.max(), 100 * len(x))
        curve = self.axes.plot(x, amplitude * hwhm ** 2 / (hwhm ** 2 + (pos - x) ** 2) + y0, 'r-', label='')[0]
        if left:
            try:
                self._negpeak_curve.remove()
                self._negpeak_text.remove()
                self._negpeak_text = None
            except AttributeError:
                pass
            assert self._negpeak_text is None
            self._negpeak_curve = curve
            self._negpeak_text = self.axes.text(pos.val, amplitude.val + y0.val, str(pos), ha='center', va='top')
        else:
            try:
                self._pospeak_curve.remove()
                self._pospeak_text.remove()
                self._pospeak_text = None
            except AttributeError:
                pass
            assert self._pospeak_text is None
            self._pospeak_curve = curve
            self._pospeak_text = self.axes.text(pos.val, amplitude.val + y0.val, str(pos), ha='center', va='bottom')
        self.canvas.draw_idle()
        if left:
            self.builder.get_object('leftval_adjustment').set_value(pos.val)
            self.builder.get_object('lefterr_adjustment').set_value(pos.err)
            self._negpeak_pos = pos
        else:
            self.builder.get_object('rightval_adjustment').set_value(pos.val)
            self.builder.get_object('righterr_adjustment').set_value(pos.err)
            self._pospeak_pos = pos
        if (self._negpeak_pos is not None) and (self._pospeak_pos is not None):
            self._thickness = (self._pospeak_pos - self._negpeak_pos).abs()
            self._position = (self._pospeak_pos + self._negpeak_pos) * 0.5
            self.builder.get_object('thickness_label').set_text(str(self._thickness) + ' mm')
            self.builder.get_object('position_label').set_text(str(self._position))
            self.builder.get_object('saveposition_button').set_sensitive(True)
            self.builder.get_object('savethickness_button').set_sensitive(True)
            self.builder.get_object('saveall_button').set_sensitive(True)

    # noinspection PyUnusedLocal
    def on_fitleft(self, button):
        self.do_fit(True)

    # noinspection PyUnusedLocal
    def on_fitright(self, button):
        self.do_fit(False)

    # noinspection PyUnusedLocal
    def on_saveposition(self, button):
        sn = self.builder.get_object('sampleselector').get_active_text()
        if sn is None:
            self.error_message('Cannot save position, please select a sample first.')
            return
        sam = self.instrument.services['samplestore'].get_sample(sn)
        if self._scandata['signals'][0].upper().endswith('X'):
            sam.positionx = ErrorValue(self._position.val, self._position.err)
            msg = 'X position set to: {}'.format(str(sam.positionx))
        elif self._scandata['signals'][0].upper().endswith('Y'):
            sam.positiony = ErrorValue(self._position.val, self._position.err)
            msg = 'Y position set to: {}'.format(str(sam.positiony))
        else:
            self.error_message('Cannot update position for sample {}: motor name {} not recognized'.format(
                sn, self._scandata['signals']))
            return
        self.instrument.services['samplestore'].set_sample(sn, sam)
        self.instrument.save_state()
        self.info_message('Sample {} {}'.format(sn, msg))
        self.builder.get_object('saveposition_button').set_sensitive(False)
        self.builder.get_object('saveall_button').set_sensitive(False)
        return

    # noinspection PyUnusedLocal
    def on_savethickness(self, button):
        sn = self.builder.get_object('sampleselector').get_active_text()
        if sn is None:
            error_message(self.widget, 'Cannot save position', 'Please select a sample first.')
            return
        sam = self.instrument.services['samplestore'].get_sample(sn)
        sam.thickness = ErrorValue(self._thickness.val / 10, self._thickness.err / 10)
        self.instrument.services['samplestore'].set_sample(sn, sam)
        self.instrument.save_state()
        self.info_message('Thickness of sample {} set to: {} cm'.format(sn, sam.thickness))
        self.builder.get_object('savethickness_button').set_sensitive(False)
        self.builder.get_object('saveall_button').set_sensitive(False)
        return True

    def on_saveall(self, button):
        self.on_saveposition(button)
        self.on_savethickness(button)
        return True

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self._samplestoreconnection = self.instrument.services['samplestore'].connect('list-changed',
                                                                                      self.on_samplelist_changed)
        self.on_samplelist_changed(self.instrument.services['samplestore'])

    def cleanup(self):
        self.instrument.services['samplestore'].disconnect(self._samplestoreconnection)
        self._samplestoreconnection = None

    def on_samplelist_changed(self, samplestore):
        update_comboboxtext_choices(self.builder.get_object('sampleselector'), sorted([x.title for x in samplestore]))
