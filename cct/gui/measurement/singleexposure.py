import logging

import numpy as np
from sastool.utils2d.integrate import radint_fullq_errorprop

from ..core.plotcurve import PlotCurveWindow
from ..core.plotimage import PlotImageWindow
from ..core.toolwindow import ToolWindow, error_message
from ...core.commands.detector import Expose, ExposeMulti

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class SingleExposure(ToolWindow):
    def _init_gui(self, *args):
        pass

    def _break_connections(self):
        try:
            self._instrument.samplestore.disconnect(self._sampleconnections)
        except AttributeError:
            pass

    def on_map(self, window):
        self._break_connections()
        self._sampleconnections=self._instrument.samplestore.connect('list-changed', self.on_samplelist_changed)
        self.on_samplelist_changed(self._instrument.samplestore)
        prefixselector=self._builder.get_object('prefixselector')
        prefixselector.remove_all()
        for i,p in enumerate(sorted(self._instrument.filesequence.get_prefixes())):
            prefixselector.append_text(p)
            if p==self._instrument.config['path']['prefixes']['tst']:
                prefixselector.set_active(i)
        self.on_maskoverride_toggled(self._builder.get_object('mask_checkbutton'))
        self.on_samplecheck_toggled(self._builder.get_object('samplename_check'))

    def on_unmap(self, window):
        self._break_connections()

    def on_samplecheck_toggled(self, togglebutton):
        self._builder.get_object('sampleselector').set_sensitive(togglebutton.get_active())

    def on_maskoverride_toggled(self, togglebutton):
        self._builder.get_object('maskchooserbutton').set_sensitive(togglebutton.get_active())

    def _init_exposure(self):
        self._builder.get_object('start_button').set_label('Stop')
        self._make_insensitive('Exposure is running', ['entrygrid', 'close_button'])
        self._expanalyzerconnection = self._instrument.exposureanalyzer.connect('image', self.on_image)
        self._interpreter_connections = [
            self._instrument.interpreter.connect('cmd-return', self.on_cmd_return),
            self._instrument.interpreter.connect('cmd-fail', self.on_cmd_fail),
            self._instrument.interpreter.connect('pulse', self.on_pulse),
            self._instrument.interpreter.connect('progress', self.on_progress),
        ]

    def _cleanup_exposure(self):
        try:
            for c in self._interpreter_connections:
                self._instrument.interpreter.disconnect(c)
            del self._interpreter_connections
        except AttributeError:
            pass
        try:
            self._instrument.exposureanalyzer.disconnect(self._expanalyzerconnection)
            del self._expanalyzerconnection
        except AttributeError:
            pass
        self._builder.get_object('start_button').set_label('Start')
        self._builder.get_object('progressframe').set_visible(False)
        self._make_sensitive()
        self._window.resize(1, 1)

    def on_cmd_return(self, interpreter, commandname, returnvalue):
        if hasattr(self, '_kill'):
            self._cleanup_exposure()
            del self._kill
        elif commandname == 'start':
            # not a true command, we just enter here.
            if self._builder.get_object('samplename_check').get_active():
                self._instrument.interpreter.execute_command(
                    'sample("%s")' % self._builder.get_object('sampleselector').get_active_text())
            else:
                self._instrument.samplestore.set_active(None)
                self.on_cmd_return(interpreter, 'sample', None)
        elif commandname == 'sample':
            if self._builder.get_object('shutter_check').get_active():
                self._instrument.interpreter.execute_command('shutter("open")')
            else:
                self.on_cmd_return(interpreter, 'shutter', True)
        elif commandname == 'shutter' and returnvalue is None:
            # shutter timeout
            self._cleanup_exposure()
            error_message(self._window, 'Shutter timeout')
        elif commandname == 'shutter' and returnvalue is True:
            # start exposure
            prefix=self._builder.get_object('prefixselector').get_active_text()
            exptime=self._builder.get_object('exptime_spin').get_value()
            nimages=self._builder.get_object('nimages_spin').get_value_as_int()
            expdelay=self._builder.get_object('expdelay_spin').get_value()

            self._builder.get_object('progressframe').show_all()
            self._builder.get_object('progressframe').set_visible(True)
            if nimages == 1:
                self._instrument.interpreter.execute_command(Expose(), (exptime, prefix))
            else:
                self._instrument.interpreter.execute_command(ExposeMulti(), (exptime, nimages, prefix, expdelay))
        elif commandname == 'shutter' and returnvalue is False:
            # this is the end.
            self._cleanup_exposure()
        elif commandname in ['expose', 'exposemulti']:
            if self._builder.get_object('shutter_check').get_active():
                self._instrument.interpreter.execute_command('shutter("close")')
            else:
                self.on_cmd_return(interpreter, 'shutter', False)
        return

    def on_cmd_fail(self, interpreter, commandname, exc, tback):
        error_message(self._window, 'Error in command %s: %s' % (commandname, str(exc)), tback)

    def on_pulse(self, interpreter, commandname, message):
        self._builder.get_object('exposure_progress').set_text(message)
        self._builder.get_object('exposure_progress').pulse()

    def on_progress(self, interpreter, commandname, message, fraction):
        self._builder.get_object('exposure_progress').set_text(message)
        self._builder.get_object('exposure_progress').set_fraction(fraction)

    def on_start(self, button):
        if button.get_label() == 'Start':
            self._init_exposure()
            self.on_cmd_return(self._instrument.interpreter, 'start', None)
        else:
            self._kill = True
            self._instrument.interpreter.kill()

    def on_image(self, exposureanalyzer, prefix, fsn, matrix, mask, params):
        if 'sample' in params:
            legend = 'FSN #%d, %s at %.2f mm' % (
            params['fsn'], params['sample']['title'], params['geometry']['dist_sample_det'])
        else:
            legend = 'FSN #%d, unknown sample at %.2f mm' % (params['fsn'], params['geometry']['dist_sample_det'])
        if self._builder.get_object('plotimage_check').get_active():
            if self._builder.get_object('reuseimage_check').get_active():
                imgwin = PlotImageWindow.get_latest_window()
            else:
                imgwin = PlotImageWindow()
            imgwin.set_image(matrix)
            imgwin.set_mask(mask)
            imgwin.set_distance(params['geometry']['dist_sample_det'])
            imgwin.set_beampos(params['geometry']['beamposx'],
                               params['geometry']['beamposy'])
            imgwin.set_pixelsize(params['geometry']['pixelsize'])
            imgwin.set_wavelength(params['geometry']['wavelength'])
            imgwin._window.set_title(legend)
        if self._builder.get_object('plotradial_check').get_active():
            if self._builder.get_object('reuseradial_check').get_active():
                curvewin = PlotCurveWindow.get_latest_window()
            else:
                curvewin = PlotCurveWindow()
            q, qerror, Intensity, Error, Area = radint_fullq_errorprop(
                matrix, matrix ** 0.5, params['geometry']['wavelength'],
                params['geometry']['wavelength.err'], params['geometry']['dist_sample_det'],
                params['geometry']['dist_sample_det.err'], params['geometry']['pixelsize'],
                params['geometry']['pixelsize'], params['geometry']['beamposx'], 0.0,
                params['geometry']['beamposy'], 0.0, mask.astype(np.uint8))
            curvewin.addcurve(q, Intensity, qerror, Error, legend, 'q', params['geometry']['pixelsize'],
                              params['geometry']['dist_sample_det'], params['geometry']['wavelength'])

    def on_samplelist_changed(self, samplestore):
        sampleselector=self._builder.get_object('sampleselector')
        previously_selected=sampleselector.get_active_text()
        if previously_selected is None:
            previously_selected = samplestore.get_active_name()
        sampleselector.remove_all()
        for i,sample in enumerate(sorted(samplestore, key=lambda x:x.title)):
            sampleselector.append_text(sample.title)
            if sample.title==previously_selected:
                sampleselector.set_active(i)

    def on_nimages_changed(self, spinbutton):
        self._builder.get_object('expdelay_spin').set_sensitive(spinbutton.get_value_as_int()>1)