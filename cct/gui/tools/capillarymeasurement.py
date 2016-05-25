import numpy as np
from gi.repository import Gtk, GLib
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.figure import Figure
from sastool.misc.basicfit import findpeak_single

from ..core.toolwindow import ToolWindow, error_message, info_message
from ...core.utils.errorvalue import ErrorValue


class CapillaryMeasurement(ToolWindow):
    def _init_gui(self, *args):
        fb = self._builder.get_object('figbox')
        self._figure = Figure(tight_layout=True)
        self._axes = self._figure.add_subplot(1, 1, 1)
        self._canvas = FigureCanvasGTK3Agg(self._figure)
        self._canvas.set_size_request(600, -1)
        fb.pack_start(self._canvas, True, True, 0)
        self._toolbar = NavigationToolbar2GTK3(self._canvas, self._window)
        fb.pack_start(self._toolbar, False, True, 0)
        b = Gtk.ToolButton.new(Gtk.Image.new_from_icon_name('view-refresh', Gtk.IconSize.LARGE_TOOLBAR), 'Redraw')
        self._toolbar.insert(b, 9)
        b.connect('clicked', lambda button: self._redraw())

    def _redraw(self):
        if not hasattr(self, '_scandata'):
            return True
        try:
            del self._lefttext
        except AttributeError:
            pass
        try:
            del self._leftcurve
        except AttributeError:
            pass
        try:
            del self._righttext
        except AttributeError:
            pass
        try:
            del self._rightcurve
        except AttributeError:
            pass
        self._figure.clear()
        self._axes = self._figure.add_subplot(1, 1, 1)
        x = self._scandata['signals'][0]
        y = self._builder.get_object('signalname_combo').get_active_text()
        if y is None:
            return
        self._xdata = self._scandata['data'][x]
        self._ydata = self._scandata['data'][y]
        ylabel = y
        if self._builder.get_object('plotderivative_checkbutton').get_active():
            self._ydata = (self._ydata[1:] - self._ydata[:-1]) / (self._xdata[1:] - self._xdata[:-1])
            self._xdata = 0.5 * (self._xdata[1:] + self._xdata[:-1])
            ylabel = 'Derivative of ' + y
        self._axes.plot(self._xdata, self._ydata, 'b.-', label=ylabel)
        self._axes.xaxis.set_label_text(x)
        self._axes.yaxis.set_label_text(ylabel)
        self._axes.grid(True, which='both')
        self._axes.set_title(self._scandata['comment'])
        self._canvas.draw()
        return True

    # noinspection PyUnusedLocal
    def on_reload_clicked(self, button):
        GLib.idle_add(lambda si=self._builder.get_object('scanindex_spin').get_value_as_int(): self.load_scan(si))

    def on_scanindex_change(self, spinbutton):
        GLib.idle_add(lambda si=spinbutton.get_value_as_int(): self.load_scan(si))

    def load_scan(self, scanidx):
        try:
            self._scandata = self._instrument.filesequence.load_scan(scanidx)
        except KeyError as ke:
            error_message(self._window, 'Scan %d not found' % ke.args[0])
            return
        signalselector = self._builder.get_object('signalname_combo')
        prevselected = signalselector.get_active_text()
        signalselector.remove_all()
        for i, signal in enumerate(self._scandata['signals'][1:]):
            signalselector.append_text(signal)
            if signal == prevselected:
                signalselector.set_active(i)
        if prevselected is None:
            signalselector.set_active(0)
        if signalselector.get_active_text() is None:
            signalselector.set_active(0)
        for i in ['_left', '_right', '_thickness', '_position']:
            try:
                delattr(self, i)
            except AttributeError:
                pass
        self._builder.get_object('leftval_adjustment').set_value(0)
        self._builder.get_object('lefterr_adjustment').set_value(0)
        self._builder.get_object('rightval_adjustment').set_value(0)
        self._builder.get_object('righterr_adjustment').set_value(0)
        self._builder.get_object('thickness_label').set_text('--')
        self._builder.get_object('position_label').set_text('--')
        self._builder.get_object('saveposition_button').set_sensitive(False)
        self._builder.get_object('savethickness_button').set_sensitive(False)
        self._builder.get_object('saveall_button').set_sensitive(False)
        self._redraw()
        return False

    # noinspection PyUnusedLocal
    def on_signalname_changed(self, combo):
        self._redraw()

    # noinspection PyUnusedLocal
    def on_plotderivative_changed(self, combo):
        self._redraw()
        return True

    def do_fit(self, left):
        if not (hasattr(self, '_xdata') and hasattr(self, '_ydata')):
            return
        xmin, xmax, ymin, ymax = self._axes.axis()
        x = self._xdata
        y = self._ydata
        idx = (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax)
        x = x[idx]
        y = y[idx]
        if left:
            signs = (-1,)
        else:
            signs = (1,)
        pos, hwhm, y0, A = findpeak_single(x, y, signs=signs, curve='Lorentz')
        x = np.linspace(x.min(), x.max(), 100 * len(x))
        curve = self._axes.plot(x, A * hwhm ** 2 / (hwhm ** 2 + (pos - x) ** 2) + y0, 'r-', label='')[0]
        if left:
            if hasattr(self, '_leftcurve'):
                self._leftcurve.remove()
                self._lefttext.remove()
            self._leftcurve = curve
            self._lefttext = self._axes.text(pos.val, A.val + y0.val, str(pos), ha='center', va='top')
        else:
            if hasattr(self, '_rightcurve'):
                self._rightcurve.remove()
                self._righttext.remove()
            self._rightcurve = curve
            self._righttext = self._axes.text(pos.val, A.val + y0.val, str(pos), ha='center', va='bottom')
        self._canvas.draw()
        if left:
            self._builder.get_object('leftval_adjustment').set_value(pos.val)
            self._builder.get_object('lefterr_adjustment').set_value(pos.err)
            self._left = pos
        else:
            self._builder.get_object('rightval_adjustment').set_value(pos.val)
            self._builder.get_object('righterr_adjustment').set_value(pos.err)
            self._right = pos
        if hasattr(self, '_left') and hasattr(self, '_right'):
            self._thickness = (self._right - self._left).abs()
            self._position = (self._right + self._left) * 0.5
            self._builder.get_object('thickness_label').set_text(str(self._thickness) + ' mm')
            self._builder.get_object('position_label').set_text(str(self._position))
            self._builder.get_object('saveposition_button').set_sensitive(True)
            self._builder.get_object('savethickness_button').set_sensitive(True)
            self._builder.get_object('saveall_button').set_sensitive(True)

    # noinspection PyUnusedLocal
    def on_fitleft(self, button):
        self.do_fit(True)

    # noinspection PyUnusedLocal
    def on_fitright(self, button):
        self.do_fit(False)

    # noinspection PyUnusedLocal
    def on_saveposition(self, button):
        sn = self._builder.get_object('sampleselector').get_active_text()
        if sn is None:
            error_message(self._window, 'Cannot save position', 'Please select a sample first.')
            return
        sam = self._instrument.samplestore.get_sample(sn)
        if self._scandata['signals'][0].upper().endswith('X'):
            sam.positionx = ErrorValue(self._position.val, self._position.err)
            self._instrument.samplestore.set_sample(sn, sam)
            self._instrument.save_state()
            info_message(self._window, 'Updated sample %s' % sn, 'X position set to: %s' % str(sam.positionx))
        elif self._scandata['signals'][0].upper().endswith('Y'):
            sam.positiony = ErrorValue(self._position.val, self._position.err)
            self._instrument.samplestore.set_sample(sn, sam)
            self._instrument.save_state()
            info_message(self._window, 'Updated sample %s' % sn, 'Y position set to: %s' % str(sam.positiony))
        else:
            error_message(self._window, 'Cannot update position for sample %s' % sn,
                          'Motor name not recognized: %s ends in neither "X" nor "Y".' %
                          self._scandata['signals'][0])
            return
        self._builder.get_object('saveposition_button').set_sensitive(False)
        self._builder.get_object('saveall_button').set_sensitive(False)
        return

    # noinspection PyUnusedLocal
    def on_savethickness(self, button):
        sn = self._builder.get_object('sampleselector').get_active_text()
        if sn is None:
            error_message(self._window, 'Cannot save position', 'Please select a sample first.')
            return
        sam = self._instrument.samplestore.get_sample(sn)
        sam.thickness = ErrorValue(self._thickness.val / 10, self._thickness.err / 10)
        self._instrument.samplestore.set_sample(sn, sam)
        self._instrument.save_state()
        info_message(self._window, 'Updated sample %s' % sn, 'Thickness set to: %s' % str(sam.thickness))
        self._builder.get_object('savethickness_button').set_sensitive(False)
        self._builder.get_object('saveall_button').set_sensitive(False)
        return True

    def on_saveall(self, button):
        self.on_saveposition(button)
        self.on_savethickness(button)
        return True

    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        try:
            self._instrument.samplestore.disconnect(self._samplestoreconnection)
            del self._samplestoreconnection
        except AttributeError:
            pass
        self._samplestoreconnection = self._instrument.samplestore.connect('list-changed', self.on_samplelist_changed)
        self.on_samplelist_changed(self._instrument.samplestore)

    def on_unmap(self, window):
        ToolWindow.on_unmap(self, window)
        try:
            self._instrument.samplestore.disconnect(self._samplestoreconnection)
            del self._samplestoreconnection
        except AttributeError:
            pass

    def on_samplelist_changed(self, samplestore):
        ssel = self._builder.get_object('sampleselector')
        prevsel = ssel.get_active_text()
        ssel.remove_all()
        for i, sam in sorted(enumerate(samplestore)):
            ssel.append_text(sam.title)
            if sam.title == prevsel:
                ssel.set_active(i)
        if prevsel is None:
            ssel.set_active(0)
        if ssel.get_active_text() is None:
            ssel.set_active(0)
