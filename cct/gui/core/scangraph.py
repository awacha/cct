import logging
from typing import List, Union, Optional

import numpy as np
from gi.repository import Gtk
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.figure import Figure
from sastool.misc.basicfit import findpeak_single

from .functions import savefiguretoclipboard
from .plotimage import PlotImageWindow
from .toolwindow import ToolWindow
from ...core.devices import Motor
from ...core.instrument.instrument import Instrument

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ScanGraph(ToolWindow):
    widgets_to_make_insensitive = ['buttonbox', 'scalebox']

    def __init__(self, signals: List[str], data: Union[np.ndarray, int], windowtitle: Union[int, str], comment: str,
                 instrument: Optional[Instrument] = None):
        """if data is an integer, we assume scanning mode, up to this number of data points. It can also be a numpy
        structured array with dtype `[(s,float) for s in signals]`: then we are in plotting mode. If in scan mode,
        self._dataindex <len(self._data). In plotting mode, self._dataindex>=len(self._data).

        signals should be a list of signal labels. The first one is the abscissa. This list has to have at least two
        elements.

        if instrument is given, motors can be moved.
        """
        self._in_scalechanged = False
        self.fig = None
        self.axes = None
        self.canvas = None
        self.toolbox = None
        if isinstance(windowtitle, int):
            windowtitle = 'Scan #{:d}'.format(windowtitle)
        self.comment = comment
        if isinstance(data, np.ndarray):
            self._data = data
            self._dataindex = len(self._data)
        elif isinstance(data, int):
            self._data = np.zeros(data, dtype=[(s, float) for s in signals])
            self._dataindex = 0
        else:
            raise TypeError('Unknown type for data: %s' % type(data))
        if len(signals) < 2:
            raise ValueError('At least one signal has to be given apart from the abscissa')
        if instrument.online:
            self.required_devices = ['Motor_' + self.abscissaname]
        self._cursorindex = 0
        self._cursor = None
        self._lastimage = None
        self._lastpeakposition = None
        super().__init__('core_scangraph.glade', 'scangraph',
                         instrument, windowtitle)

    def init_gui(self, *args, **kwargs):
        self.fig = Figure()
        self.axes = self.fig.add_subplot(1, 1, 1)
        self.canvas = FigureCanvasGTK3Agg(self.fig)
        self.canvas.set_size_request(-1, 400)
        self.toolbox = NavigationToolbar2GTK3(self.canvas, self.widget)
        b = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('view-refresh', Gtk.IconSize.LARGE_TOOLBAR),
                           label='Redraw')
        b.set_tooltip_text('Redraw the signals')
        b.connect('clicked', lambda b_: self.redraw_signals())
        self.toolbox.insert(b, 9)
        b = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('edit-copy', Gtk.IconSize.LARGE_TOOLBAR),
                           label='Copy')
        b.set_tooltip_text('Copy the image to the clipboard')
        b.connect('clicked', lambda b_, f=self.fig: savefiguretoclipboard(f))
        self.toolbox.insert(b, 9)
        # pack the figure into the appropriate vbox
        figbox = self.builder.get_object('figbox')
        figbox.pack_start(self.canvas, True, True, 0)
        figbox.pack_start(self.toolbox, False, True, 0)
        # adjust the treeview of the counters
        counterview = self.builder.get_object('counterview')
        assert isinstance(counterview, Gtk.TreeView)
        countermodel = counterview.get_model()
        assert isinstance(countermodel, Gtk.ListStore)
        # the model columns are:
        #    signal name, visibility, scaling adjustment, scale value.
        for c in self.signals:
            countermodel.append((c, True, Gtk.Adjustment(
                value=1.0, lower=0.0, upper=1.0e6, step_increment=1.0,
                page_increment=10.0, page_size=0.0), 1.0))
        # create the needed treeview columns
        # Signal name column
        tc = Gtk.TreeViewColumn('Signal', Gtk.CellRendererText(), text=0)
        tc.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        counterview.append_column(tc)
        # Signal visibility column
        cr = Gtk.CellRendererToggle()
        cr.connect('toggled', self.on_column_visibility_changed, countermodel)
        tc = Gtk.TreeViewColumn('Show', cr, active=1)
        tc.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        counterview.append_column(tc)
        # Signal scaling column
        cr = Gtk.CellRendererSpin()
        cr.set_property('digits', 2)
        cr.set_property('editable', True)
        cr.connect('edited', self.on_scaling_edited, countermodel)
        tc = Gtk.TreeViewColumn('Scaling', cr, adjustment=2, text=3)
        tc.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        counterview.append_column(tc)
        # Select the second counter: first is always the FSN of the image.
        it = countermodel.get_iter_first()
        countermodel.iter_next(it)
        counterview.get_selection().select_iter(it)
        del it
        # set visibility of the buttonbox and the cursor movement box.
        self.builder.get_object('buttonbox').set_visible(not self.is_scan_mode())
        self.builder.get_object('scalebox').set_visible(not self.is_scan_mode())

        if not self.is_scan_mode():
            self.start_view_mode()
        # if we have self.instrument, make motor moving buttons visible and sensitive.
        self.builder.get_object('move_to_cursor_button').set_visible(self.instrument.online)
        self.builder.get_object('move_to_peak_button').set_visible(self.instrument.online)
        self.builder.get_object('move_to_cursor_button').set_sensitive(self.instrument.online)
        self.builder.get_object('move_to_peak_button').set_sensitive(False)
        self.redraw_signals()

    def is_scan_mode(self) -> bool:
        """Decide if we are in scan mode: if the data array is not yet full."""
        return self._dataindex < len(self._data)

    def start_view_mode(self):
        if self.is_scan_mode():
            raise ValueError('Cannot start view mode: a scan is running.')
        if not len(self._data) or not self._dataindex:
            # empty scan
            self.error_message('No scan points.')
            return
        # set button box and cursor box visible.
        self.builder.get_object('buttonbox').set_visible(True)
        self.builder.get_object('scalebox').set_visible(True)
        # adjust the limits and increments of the cursor movement scale widget
        abscissa = self.abscissa
        self.builder.get_object('cursorscale').set_range(
            abscissa.min(),
            abscissa.max())
        step = (abscissa.max() - abscissa.min()) / (len(abscissa) - 1)
        self.builder.get_object('cursorscale').set_increments(step, 10 * step)
        self.builder.get_object('cursorscale').set_value(abscissa[self._cursorindex])
        # we don't need to `self.redraw_cursor()` because self.redraw_signals() already took care of it.

    def truncate_scan(self):
        """Can be used for user-broken scans"""
        self._data = self._data[:self._dataindex]
        self.start_view_mode()

    def append_data(self, datatuple):
        """Append a new scan point"""
        if not self.is_scan_mode():
            raise ValueError('Cannot append data: not in scan mode')
        self._data[self._dataindex] = datatuple
        self._dataindex += 1
        self.redraw_signals()
        if not self.is_scan_mode():  # self._dataindex reached len(self._data)
            self.start_view_mode()

    def new_image(self, matrix, param, mask):
        self._lastimage = matrix
        self.redraw_2dimage()

    def on_column_visibility_changed(self, cellrenderer, treepath, model):
        model[treepath][1] = not model[treepath][1]
        self.redraw_signals()

    def on_scaling_edited(self, cellrenderer, treepath, newvalue, model):
        model[treepath][2].set_value(float(newvalue))
        model[treepath][3] = float(newvalue)
        self.redraw_signals()

    @property
    def abscissaname(self):
        return self._data.dtype.names[0]

    @property
    def signals(self):
        return self._data.dtype.names[1:]

    @property
    def visible_signals(self):
        return [row[0] for row in self.builder.get_object('counterstore') if row[1]]

    @property
    def abscissa(self):
        return self._data[self.abscissaname]

    def __len__(self):
        return self._dataindex

    def redraw_cursor(self):
        if self.is_scan_mode() or (not len(self._data)) or (not self._dataindex):
            # do not draw cursor in scan mode and when no points are available
            return
        try:
            self._cursor.remove()
        except AttributeError:
            pass
        finally:
            self._cursor = None
        cursorpos = self.abscissa[self._cursorindex]
        cursorwidth = (self.abscissa.max() - self.abscissa.min()) / (len(self) - 1) / 5
        self._cursor = self.axes.axvspan(cursorpos - cursorwidth * 0.5, cursorpos + cursorwidth * 0.5,
                                         facecolor='yellow', alpha=0.5)
        self.axes.legend(self.axes.lines,
                         ['%s: %f' % (s, self._data[s][self._cursorindex]) for s in self.visible_signals],
                         fontsize='small', loc='best')
        self.canvas.draw()
        if not self._in_scalechanged:
            self._in_scalechanged = True
            try:
                self.builder.get_object('cursorscale').set_value(cursorpos)
            finally:
                self._in_scalechanged = False
        self.redraw_2dimage()

    def redraw_2dimage(self):
        if not self.builder.get_object('show2d_checkbutton').get_active():
            return
        if not self.is_scan_mode():
            fsn = int(self._data['FSN'][self._cursorindex])
            data = self.instrument.services['filesequence'].load_cbf(
                self.instrument.config['path']['prefixes']['scn'], fsn)
            imgindex = self._cursorindex + 1
        else:
            data = self._lastimage
            if self._lastimage is None:
                return
            imgindex = self._dataindex
        mask = self.instrument.services['filesequence'].get_mask(self.instrument.config['scan']['mask_total'])
        piw = PlotImageWindow.get_latest_window()
        piw.set_image(data)
        piw.set_distance(self.instrument.config['geometry']['dist_sample_det'])
        piw.set_wavelength(self.instrument.config['geometry']['wavelength'])
        piw.set_pixelsize(self.instrument.config['geometry']['pixelsize'])
        piw.set_beampos(self.instrument.config['geometry']['beamposy'],
                        self.instrument.config['geometry']['beamposx'])
        piw.set_mask(mask)
        piw.set_title('{:d}/{:d} point of {}'.format(imgindex, len(self), self.widget.get_title()))

    def redraw_signals(self):
        try:
            self._cursor.remove()
        except AttributeError:
            pass
        finally:
            self._cursor = None
        self._lastpeakposition = None
        self.builder.get_object('move_to_peak_button').set_sensitive(False)
        self.axes.clear()
        if not self._dataindex:
            # no data point, do not plot anything.
            return
        model = self.builder.get_object('counterstore')
        for row in model:
            if not row[1]:
                continue  # signal not visible
            signal = row[0]  # signal name
            scaling = row[3]  # scaling factor
            self.axes.plot(self.abscissa[0:self._dataindex],
                           self._data[signal][0:self._dataindex] * scaling, '.-', label=signal)
        self.axes.legend(loc='best', fontsize='small')
        self.axes.xaxis.set_label_text(self.abscissaname)
        if self.comment is not None:
            self.axes.set_title(self.comment)
        self.redraw_cursor()
        self.canvas.draw()

    def on_gofirst(self, button):
        self._cursorindex = 0
        self.redraw_cursor()

    def on_goprevious(self, button):
        self._cursorindex = max(0, self._cursorindex - 1)
        self.redraw_cursor()

    def on_gonext(self, button):
        self._cursorindex = min(self._dataindex - 1, self._cursorindex + 1)
        self.redraw_cursor()

    def on_golast(self, button):
        self._cursorindex = self._dataindex - 1
        self.redraw_cursor()

    def on_scalechanged(self, scale):
        if self._in_scalechanged:
            return
        self._in_scalechanged = True
        try:
            val = scale.get_value()
            self._cursorindex = np.abs(self.abscissa - val).argmin()
            scale.set_value(self.abscissa[self._cursorindex])
            self.redraw_cursor()
        finally:
            self._in_scalechanged = False

    def on_cursortomax(self, button):
        model, it = self.builder.get_object('counterview').get_selection().get_selected()
        if it is None:
            return
        signal = model[it][0]
        self._cursorindex = self._data[signal].argmax()
        self.redraw_cursor()

    def on_cursortomin(self, button):
        model, it = self.builder.get_object('counterview').get_selection().get_selected()
        if it is None:
            return
        signal = model[it][0]
        self._cursorindex = self._data[signal].argmin()
        self.redraw_cursor()

    def on_show2d_toggled(self, checkbutton):
        if checkbutton.get_active():
            self.redraw_2dimage()

    def on_fitpeak(self, menuentry: Gtk.MenuItem):
        curvetype = menuentry.get_name()[:-1]
        if menuentry.get_name().endswith('0'):
            signs = (1, -1)
        elif menuentry.get_name().endswith('+'):
            signs = (1,)
        elif menuentry.get_name().endswith('-'):
            signs = (-1,)
        else:
            raise ValueError(menuentry.get_name())
        model, it = self.builder.get_object('counterview').get_selection().get_selected()
        if it is None:
            return False
        signalname = model[it][0]
        abscissa = self.abscissa
        signal = self._data[signalname]
        left, right, bottom, top = self.axes.axis()
        index = (abscissa >= left) & (abscissa <= right) & (signal <= top) & (signal >= bottom)
        try:
            position, hwhm, baseline, amplitude, stat = findpeak_single(abscissa[index], signal[index], None,
                                                                        return_stat=True, curve=curvetype, signs=signs)
        except ValueError:
            self.error_message('Fitting error: Probably no points of the selected curve are in the zoomed area.')
            return
        x = np.linspace(abscissa[index].min(), abscissa[index].max(), index.sum() * 5)
        assert isinstance(x, np.ndarray)
        if curvetype == 'Gaussian':
            y = amplitude * np.exp(-0.5 * (x - position) ** 2 / hwhm ** 2) + baseline
        elif curvetype == 'Lorentzian':
            y = amplitude * hwhm ** 2 / (hwhm ** 2 + (position - x) ** 2) + baseline
        else:
            raise ValueError(curvetype)
        self.axes.plot(x, y, 'r-', label='Fit')
        self.axes.text(position.val, amplitude.val + baseline.val, str(position), ha='center', va='bottom')
        self.canvas.draw()
        self._lastpeakposition = position
        self.builder.get_object('move_to_peak_button').set_sensitive(True)

    def on_movetocursor(self, button):
        self.set_sensitive(False, 'Moving motor {} to cursor.'.format(self.abscissaname), ['move_to_cursor_button'])
        self.instrument.motors[self.abscissaname].moveto(self.abscissa[self._cursorindex])

    def on_motor_stop(self, motor: Motor, targetreached: bool):
        if not self.get_sensitive():
            # the motor was moving because of a Move to cursor or 
            # Move to peak operation
            self.set_sensitive(True)

    def on_movetopeak(self, button):
        self.set_sensitive(False, 'Moving motor {} to peak.'.format(self.abscissaname), ['move_to_peak_button'])
        self.instrument.motors[self.abscissaname].moveto(self._lastpeakposition.val)

    def on_showallsignals(self, button):
        for row in self.builder.get_object('counterstore'):
            row[1] = True
        self.redraw_signals()

    def on_hideallsignals(self, button):
        for row in self.builder.get_object('counterstore'):
            row[1] = False
        self.redraw_signals()

    def on_differentiate(self, button):
        newdata = np.zeros(self._dataindex - 1, dtype=self._data.dtype)
        abscissaname = self.abscissaname
        steps = self.abscissa[1:self._dataindex] - self.abscissa[0:self._dataindex - 1]
        for field in self._data.dtype.names:
            if field == abscissaname:
                continue
            newdata[field] = (self._data[field][1:self._dataindex] - self._data[field][0:self._dataindex - 1]) / steps

        newdata[abscissaname] = 0.5 * (
            self.abscissa[1:self._dataindex] + self.abscissa[0:self._dataindex - 1])
        sg = self.__class__(self._data.dtype.names, newdata, 'Derivative of ' + self.widget.get_title(),
                            'Derivative of ' + self.comment, self.instrument)
        sg.show_all()

    def on_integrate(self, button):
        newdata = np.zeros(self._dataindex - 1, dtype=self._data.dtype)
        abscissaname = self.abscissaname
        steps = self.abscissa[1:self._dataindex] - self.abscissa[0:self._dataindex - 1]
        for field in self._data.dtype.names:
            newdata[field] = (self._data[field][1:self._dataindex] + self._data[field][
                                                                     0:self._dataindex - 1]) * 0.5 * steps

        newdata[abscissaname] = 0.5 * (
            self.abscissa[1:self._dataindex] + self.abscissa[0:self._dataindex - 1])
        sg = self.__class__(self._data.dtype.names, newdata, 'Integral of ' + self.widget.get_title(),
                            'Integral of ' + self.comment, self.instrument)
        sg.show_all()

    def cleanup(self):
        assert isinstance(self.fig, Figure)
        self.fig.clear()
        del self.axes
        del self.fig
        del self.canvas
        del self.toolbox
        del self._data
