import logging

import numpy as np
import pkg_resources
from gi.repository import Gtk
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.figure import Figure
from sastool.misc.basicfit import findpeak_single

from .plotimage import PlotImageWindow
from .toolwindow import error_message

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class ScanGraph(object):
    def __init__(self, signals=[], data=None, instrument=None, fsn=None, comment=None):
        """if data is an integer, we assume scanning mode, up to this number of data points. It can also be a numpy
         structured array with dtype `[(s,float) for s in signals]`: then we are in plotting mode. If in scan mode,
         self._dataindex <len(self._data). In plotting mode, self._dataindex>=len(self._data).

         signals should be a list of signal labels. The first one is the abscissa. This list has to have at least two
         elements.

         if instrument is given, motors can be moved.
         """
        object.__init__(self)
        self._comment = comment
        self._instrument=instrument
        if len(signals)<2:
            raise ValueError('At least one signal has to be given apart from the abscissa')
        if isinstance(data, np.ndarray):
            self._data=data
            self._dataindex=len(self._data)
        elif isinstance(data, int):
            self._data=np.zeros(data,dtype=[(s,float) for s in signals])
            self._dataindex=0
        else:
            raise NotImplementedError('Unknown type for data: %s'%type(data))

        self._builder=Gtk.Builder.new_from_file(pkg_resources.resource_filename('cct','resource/glade/core_scangraph.glade'))
        self._window=self._builder.get_object('scangraph')
        figbox=self._builder.get_object('figbox')
        self._fig=Figure()
        self._axes=self._fig.add_subplot(1,1,1)
        self._canvas=FigureCanvasGTK3Agg(self._fig)
        self._canvas.set_size_request(-1,400)
        self._toolbox=NavigationToolbar2GTK3(self._canvas, self._window)
        b=Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('view-refresh',Gtk.IconSize.LARGE_TOOLBAR),label='Redraw')
        b.set_tooltip_text('Redraw the signals')
        self._toolbox.insert(b,9)
        b.connect('clicked',lambda b:self._redraw_signals())
        figbox.pack_start(self._canvas,True,True,0)
        figbox.pack_start(self._toolbox,False, True, 0)
        counterview=self._builder.get_object('counterview')
        countermodel=self._builder.get_object('counterstore')
        for c in signals[1:]: # skip the first signal: it is the abscissa
            countermodel.append((c, True, Gtk.Adjustment(value=1, lower=0, upper=1e6, step_increment=1, page_increment=10, page_size=0),1))
        tc=Gtk.TreeViewColumn('Signal',Gtk.CellRendererText(), text=0)
        tc.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        counterview.append_column(tc)
        cr=Gtk.CellRendererToggle()
        cr.connect('toggled',self.on_column_visibility_changed, countermodel)
        tc=Gtk.TreeViewColumn('Show',cr,active=1)
        tc.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        counterview.append_column(tc)
        cr=Gtk.CellRendererSpin()
        cr.set_property('digits',2)
        cr.set_property('editable',True)
        cr.connect('edited', self.on_scaling_edited, countermodel)
        tc=Gtk.TreeViewColumn('Scaling',cr,adjustment=2,text=3)
        tc.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        counterview.append_column(tc)
        counterview.get_selection().select_iter(countermodel.get_iter_first())
        self._builder.get_object('buttonbox').set_visible(not self.is_scan_mode())
        self._builder.get_object('scalebox').set_visible(not self.is_scan_mode())

        self._builder.connect_signals(self)
        self._window.show_all()
        self._cursorindex=0
        if not self.is_scan_mode():
            self.start_view_mode()
        self._builder.get_object('move_to_cursor_button').set_visible(self._instrument is not None)
        self._builder.get_object('move_to_peak_button').set_visible(self._instrument is not None)
        self._builder.get_object('move_to_cursor_button').set_sensitive(self._instrument is not None)
        self._builder.get_object('move_to_peak_button').set_sensitive(False)
        self._redraw_signals()
        if fsn is not None:
            self._window.set_title('Scan #%d' % fsn)

    def is_scan_mode(self):
        return self._dataindex<len(self._data)

    def start_view_mode(self):
        if not self.is_scan_mode():
            self._builder.get_object('buttonbox').set_visible(True)
            self._builder.get_object('scalebox').set_visible(True)
            abscissa=self._data[self.get_abscissaname()]
            self._builder.get_object('cursorscale').set_range(
                abscissa.min(),
                abscissa.max())
            step=(abscissa.max()-abscissa.min())/(len(abscissa)-1)
            self._builder.get_object('cursorscale').set_increments(step,10*step)
            self._builder.get_object('cursorscale').set_value(abscissa[self._cursorindex])
            # we don't need to `self._redraw_cursor()` because self._redraw_signals() already took care of it.

    def truncate_scan(self):
        """Can be used for user-broken scans"""
        self._data=self._data[:self._dataindex]
        self.start_view_mode()

    def append_data(self, datatuple):
        if self.is_scan_mode():
            self._data[self._dataindex]=datatuple
            self._dataindex+=1
            self._redraw_signals()
            if not self.is_scan_mode(): # self._dataindex reached len(self._data)
                self.start_view_mode()
        else:
            raise ValueError('Cannot append data: not in scan mode')

    def on_column_visibility_changed(self, cellrenderer, treepath, model):
        model[treepath][1]=not model[treepath][1]
        self._redraw_signals()

    def on_scaling_edited(self, cellrenderer, treepath, newvalue, model):
        model[treepath][2].set_value(float(newvalue))
        model[treepath][3]=float(newvalue)
        self._redraw_signals()

    def on_close(self, window):
        self._window.destroy()

    def get_signals(self, onlyvisible=False):
        if onlyvisible:
            result=[]
            for row in self._builder.get_object('counterstore'):
                if row[1]:
                    result.append(row[0])
            return result
        else:
            return self._data.dtype.names[1:]

    def get_abscissaname(self):
        return self._data.dtype.names[0]

    def _redraw_cursor(self):
        if self.is_scan_mode():
            return
        try:
            self._cursor.remove()
            del self._cursor
        except AttributeError:
            pass
        abscissa=self._data[self.get_abscissaname()]
        cursorpos=abscissa[self._cursorindex]
        cursorwidth=(abscissa.max()-abscissa.min())/(len(abscissa)-1)/5
        self._cursor=self._axes.axvspan(cursorpos-cursorwidth*0.5,cursorpos+cursorwidth*0.5, facecolor='yellow', alpha=0.5)
        self._axes.legend(self._axes.lines, ['%s: %f'%(s, self._data[s][self._cursorindex]) for s in self.get_signals(onlyvisible=True)],
                          fontsize='small', loc='best')
        self._canvas.draw()
        if not hasattr(self, '_in_scalechanged'):
            self._in_scalechanged=True
            try:
                self._builder.get_object('cursorscale').set_value(cursorpos)
            finally:
                del self._in_scalechanged
        if self._builder.get_object('show2d_checkbutton').get_active():
            fsn=self._data['FSN'][self._cursorindex]
            data=self._instrument.filesequence.load_cbf(self._instrument.config['path']['prefixes']['scn'],fsn)
            mask=self._instrument.filesequence.get_mask(self._instrument.config['scan']['mask_total'])
            piw=PlotImageWindow.get_latest_window()
            piw.set_distance(self._instrument.config['geometry']['dist_sample_det'])
            piw.set_wavelength(self._instrument.config['geometry']['wavelength'])
            piw.set_image(data)
            piw.set_mask(mask)
            piw.set_pixelsize(self._instrument.config['geometry']['pixelsize'])
            piw.set_beampos(self._instrument.config['geometry']['beamposx'],self._instrument.config['geometry']['beamposy'])

    def _redraw_signals(self):
        try:
            del self._cursor
        except AttributeError:
            pass
        try:
            del self._lastpeakposition
            self._builder.get_object('move_to_peak_button').set_sensitive(False)
        except AttributeError:
            pass
        self._axes.clear()
        if not self._dataindex:
            return
        model=self._builder.get_object('counterstore')
        for row in model:
            if not row[1]:
                continue # signal not visible
            signal=row[0]
            scaling=row[3]
            self._axes.plot(self._data[self.get_abscissaname()][0:self._dataindex], self._data[signal][0:self._dataindex]*scaling,'.-',label=signal)
        self._axes.legend(loc='best',fontsize='small')
        self._axes.xaxis.set_label_text(self.get_abscissaname())
        if self._comment is not None:
            self._axes.set_title(self._comment)
        self._redraw_cursor()
        self._canvas.draw()

    def on_gofirst(self, button):
        self._cursorindex=0
        self._redraw_cursor()

    def on_goprevious(self, button):
        self._cursorindex=max(0,self._cursorindex-1)
        self._redraw_cursor()

    def on_gonext(self, button):
        self._cursorindex=min(self._dataindex-1,self._cursorindex+1)
        self._redraw_cursor()

    def on_golast(self, button):
        self._cursorindex=self._dataindex-1
        self._redraw_cursor()

    def on_scalechanged(self, scale):
        if hasattr(self, '_in_scalechanged'):
            return
        self._in_scalechanged=True
        try:
            val=scale.get_value()
            abscissa=self._data[self.get_abscissaname()]
            self._cursorindex=np.abs(abscissa-val).argmin()
            scale.set_value(abscissa[self._cursorindex])
            self._redraw_cursor()
        finally:
            del self._in_scalechanged

    def on_cursortomax(self, button):
        model, it=self._builder.get_object('counterview').get_selection().get_selected()
        if it is None:
            return
        signal=model[it][0]
        self._cursorindex=self._data[signal].argmax()
        self._redraw_cursor()

    def on_cursortomin(self, button):
        model, it=self._builder.get_object('counterview').get_selection().get_selected()
        if it is None:
            return
        signal=model[it][0]
        self._cursorindex=self._data[signal].argmin()
        self._redraw_cursor()

    def on_show2d_toggled(self, checkbutton):
        self._redraw_cursor()

    def on_fitpeak(self, menuentry):
        curvetype=menuentry.get_name()[:-1]
        if menuentry.get_name().endswith('0'):
            signs=(1,-1)
        elif menuentry.get_name().endswith('+'):
            signs=(1,)
        elif menuentry.get_name().endswith('-'):
            signs=(-1,)
        model, it=self._builder.get_object('counterview').get_selection().get_selected()
        signalname=model[it][0]
        abscissa=self._data[self.get_abscissaname()]
        signal=self._data[signalname]
        left,right,bottom,top=self._axes.axis()
        index=(abscissa>=left)&(abscissa<=right)&(signal<=top)&(signal>=bottom)
        try:
            position, hwhm, baseline, amplitude, stat=findpeak_single(abscissa[index],signal[index],None,return_stat=True,curve=curvetype, signs=signs)
        except ValueError:
            error_message(self._window,'Fitting error','Probably no points of the selected curve are in the beam.')
            return
        x=np.linspace(abscissa[index].min(),abscissa[index].max(),index.sum()*5)
        if curvetype=='Gaussian':
            y= amplitude * np.exp(-0.5 * (x - position) ** 2 / hwhm ** 2) + baseline
        elif curvetype=='Lorentzian':
            y= amplitude * hwhm ** 2 / (hwhm ** 2 + (position - x) ** 2) + baseline
        else:
            raise NotImplementedError(curvetype)
        self._axes.plot(x,y,'r-',label='Fit')
        self._axes.text(position.val, amplitude.val+baseline.val,str(position),ha='center',va='bottom')
        self._canvas.draw()
        self._lastpeakposition=position
        self._builder.get_object('move_to_peak_button').set_sensitive(True)


    def on_movetocursor(self, button):
        button.set_sensitive(False)
        self._motorconnection=self._instrument.motors[self.get_abscissaname()].connect('stop', self.on_endmove, button)
        self._instrument.motors[self.get_abscissaname()].moveto(self._data[self.get_abscissaname()][self._cursorindex])

    def on_endmove(self, motor, targetreached, button):
        button.set_sensitive(True)
        try:
            motor.disconnect(self._motorconnection)
            del self._motorconnection
        except AttributeError:
            pass

    def on_unmap(self, window):
        try:
            self._instrument.motors[self.get_abscissaname()].disconnect(self._motorconnection)
            del self._motorconnection
        except AttributeError:
            pass

    def on_movetopeak(self, button):
        button.set_sensitive(False)
        self._motorconnection=self._instrument.motors[self.get_abscissaname()].connect('stop', self.on_endmove, button)
        self._instrument.motors[self.get_abscissaname()].moveto(self._lastpeakposition.val)

    def on_showallsignals(self, button):
        for row in self._builder.get_object('counterstore'):
            row[1]=True
        self._redraw_signals()

    def on_hideallsignals(self, button):
        for row in self._builder.get_object('counterstore'):
            row[1]=False
        self._redraw_signals()

    def on_differentiate(self, button):
        newdata=np.zeros(self._dataindex-1, dtype=self._data.dtype)
        abscissaname=self.get_abscissaname()
        steps=self._data[abscissaname][1:self._dataindex]-self._data[abscissaname][0:self._dataindex-1]
        for field in self._data.dtype.names:
            if field==abscissaname:
                continue
            newdata[field]=(self._data[field][1:self._dataindex]-self._data[field][0:self._dataindex-1])/steps

        newdata[abscissaname]=0.5*(self._data[abscissaname][1:self._dataindex]+self._data[abscissaname][0:self._dataindex-1])
        sg=self.__class__(self._data.dtype.names, newdata, self._instrument)

    def on_integrate(self, button):
        newdata=np.zeros(self._dataindex-1, dtype=self._data.dtype)
        abscissaname=self.get_abscissaname()
        steps=self._data[abscissaname][1:self._dataindex]-self._data[abscissaname][0:self._dataindex-1]
        for field in self._data.dtype.names:
            newdata[field]=(self._data[field][1:self._dataindex]+self._data[field][0:self._dataindex-1])*0.5*steps

        newdata[abscissaname]=0.5*(self._data[abscissaname][1:self._dataindex]+self._data[abscissaname][0:self._dataindex-1])
        sg=self.__class__(self._data.dtype.names, newdata, self._instrument)

    def get_visible(self):
        return self._window.get_visible()