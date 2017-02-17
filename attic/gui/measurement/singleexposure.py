import logging
from typing import Optional

from gi.repository import Gtk
from sastool.io.credo_cct import Header, Exposure

from ..core.functions import update_comboboxtext_choices
from ..core.plotcurve import PlotCurveWindow
from ..core.plotimage import PlotImageWindow
from ..core.toolwindow import ToolWindow
from ...core.commands.detector import Expose, ExposeMulti
from ...core.commands.motor import SetSample
from ...core.commands.xray_source import Shutter
from ...core.services.interpreter import Interpreter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SingleExposure(ToolWindow):
    required_devices = ['detector', 'xray_source', 'Motor_Sample_X', 'Motor_Sample_Y']
    widgets_to_make_insensitive = ['inputframe']

    def __init__(self, *args, **kwargs):
        self._images_done = 0
        self._images_requested = 0
        self._sampleconnection = None
        self._killed = False
        self._nimages = 0
        self._images_done = 0
        self._expanalyzerconnection = None
        super().__init__(*args, **kwargs)

    def cleanup(self):
        if self._sampleconnection is not None:
            self.instrument.services['samplestore'].disconnect(self._sampleconnection)
            self._sampleconnection = None

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self._sampleconnection = self.instrument.services['samplestore'].connect(
            'list-changed', self.on_samplelist_changed)
        self.on_samplelist_changed(self.instrument.services['samplestore'])
        update_comboboxtext_choices(
            self.builder.get_object('prefixselector'),
            sorted(self.instrument.services['filesequence'].get_prefixes()),
            self.instrument.config['path']['prefixes']['tst']
        )
        self.on_samplecheck_toggled(self.builder.get_object('samplename_check'))

    def on_samplecheck_toggled(self, togglebutton):
        self.builder.get_object('sampleselector').set_sensitive(togglebutton.get_active())

    def on_command_return(self, interpreter: Interpreter, commandname: Optional[str], returnvalue: object):
        if commandname is not None:
            super().on_command_return(interpreter, commandname, returnvalue)

        if self._killed:
            commandname = 'shutter'
            returnvalue = False

        if commandname is None:
            # not a true command, we just enter here because self.start() called us.
            if self.builder.get_object('samplename_check').get_active():
                self.execute_command(
                    SetSample, (self.builder.get_object('sampleselector').get_active_text(),))
                return False
            else:
                self.instrument.services['samplestore'].set_active(None)
                commandname = 'sample'
                returnvalue = None
                self.on_command_return(interpreter, 'sample', None)
                # pass through to the next if.

        if commandname == 'sample':
            logger.debug('Sample in place')
            if self.builder.get_object('shutter_check').get_active():
                logger.debug('Opening shutter')
                self.execute_command(
                    Shutter, (True,))
                return False
            else:
                logger.debug('Not opening shutter, passing through to next command.')
                commandname = 'shutter'
                returnvalue = True
                # pass through to the next if.

        if commandname == 'shutter' and returnvalue is True:
            # start exposure
            logger.debug('Starting exposure')
            prefix = self.builder.get_object('prefixselector').get_active_text()
            exptime = self.builder.get_object('exptime_spin').get_value()
            self._nimages = self.builder.get_object('nimages_spin').get_value_as_int()
            expdelay = self.builder.get_object('expdelay_spin').get_value()

            self.builder.get_object('progressframe').show_all()
            self.builder.get_object('progressframe').set_visible(True)
            if self._nimages == 1:
                logger.debug('Executing Expose')
                self.execute_command(
                    Expose, (exptime, prefix))
            else:
                logger.debug('Executing ExposeMulti')
                self.execute_command(
                    ExposeMulti, (exptime, self._nimages, prefix, expdelay))
            return False

        if commandname in ['expose', 'exposemulti']:
            logger.debug('Exposure ended.')
            if self.builder.get_object('shutter_check').get_active():
                logger.debug('Closing shutter')
                self.execute_command(
                    Shutter, (False,))
                return False
            else:
                logger.debug('Not closing shutter')
                commandname = 'shutter'
                returnvalue = False
                # pass through to the next if.

        if commandname == 'shutter' and returnvalue is False:
            # this is the end.
            logger.debug('Shutter is closed, ending singleexposure')
            self.builder.get_object('start_button').set_label('Start')
            self.builder.get_object('start_button').get_image().set_from_icon_name('system-run', Gtk.IconSize.BUTTON)
            self.builder.get_object('progressframe').set_visible(False)
            self.set_sensitive(True)
            self.widget.resize(1, 1)
            self._killed = False
            return False

        # we should not reach here.
        raise ValueError(commandname, returnvalue)

    def on_command_pulse(self, interpreter, commandname, message):
        self.builder.get_object('exposure_progress').set_text(message)
        self.builder.get_object('exposure_progress').pulse()

    def on_command_progress(self, interpreter, commandname, message, fraction):
        self.builder.get_object('exposure_progress').set_text(message)
        self.builder.get_object('exposure_progress').set_fraction(fraction)

    def on_start(self, button):
        if button.get_label() == 'Start':
            button.set_label('Stop')
            button.get_image().set_from_icon_name('gtk-stop', Gtk.IconSize.BUTTON)
            self._images_done = 0
            self._expanalyzerconnection = self.instrument.services['exposureanalyzer'].connect('image', self.on_image)
            self.on_command_return(self.instrument.services['interpreter'], None, None)
        else:
            self._killed = True
            self.instrument.services['interpreter'].kill()

    def on_image(self, exposureanalyzer, prefix, fsn, matrix, params, mask):

        im = Exposure(matrix, header=Header(params), mask=mask)
        try:
            sample = im.header.title
        except KeyError:
            sample = 'unknown sample'
        legend = 'FSN #{:d}, {} at {:.2f} mm'.format(
            im.header.fsn, sample, float(im.header.distance))
        if self.builder.get_object('plotimage_check').get_active():
            if self.builder.get_object('reuseimage_check').get_active():
                imgwin = PlotImageWindow.get_latest_window()
            else:
                imgwin = PlotImageWindow()
            imgwin.set_image(im.intensity)
            imgwin.set_mask(im.mask)
            imgwin.set_distance(im.header.distance)
            imgwin.set_beampos(im.header.beamcenterx,
                               im.header.beamcentery)
            assert im.header.pixelsizex == im.header.pixelsizey
            imgwin.set_pixelsize(im.header.pixelsizex)
            imgwin.set_wavelength(im.header.wavelength)
            imgwin.set_title(legend)
        if self.builder.get_object('plotradial_check').get_active():
            if self.builder.get_object('reuseradial_check').get_active():
                curvewin = PlotCurveWindow.get_latest_window()
            else:
                curvewin = PlotCurveWindow()
            curve = im.radial_average()
            assert im.header.pixelsizex == im.header.pixelsizey
            curvewin.addcurve(curve.q, curve.Intensity, curve.qError, curve.Error, legend, 'q',
                              im.header.pixelsizex,
                              im.header.distance, im.header.wavelength)
        self._images_done += 1
        if self._images_done >= self._nimages:
            self.instrument.services['exposureanalyzer'].disconnect(self._expanalyzerconnection)
            self._expanalyzerconnection = None

    def on_samplelist_changed(self, samplestore):
        update_comboboxtext_choices(
            self.builder.get_object('sampleselector'),
            sorted([x.title for x in samplestore]))

    def on_nimages_changed(self, spinbutton):
        self.builder.get_object('expdelay_spin').set_sensitive(spinbutton.get_value_as_int() > 1)

    def on_maskoverride_toggled(self, togglebutton):
        pass
