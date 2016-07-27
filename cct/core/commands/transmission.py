import datetime
import logging
import time

import numpy as np
from sastool.misc.errorvalue import ErrorValue

from .command import Command, CommandError, CommandArgumentError, CommandTimeoutError
from ..instrument.privileges import PRIV_BEAMSTOP, PRIV_MOVEMOTORS

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Transmission(Command):
    """Measure the transmission of a sample

    Invocation: transmission(<samplename> [, <nimages> [, <countingtime [, <emptyname>]]])

    Arguments:
        <samplename>: the name of the sample. Can also be a list of strings if
            you want to measure multiple samples at once.
        <nimages>: number of images to expose. Integer, >2
        <countingtime>: counting time at each exposure
        <emptyname>: the sample to use for empty beam exposures

    """
    name = 'transmission'

    pulse_interval = 0.5

    required_devices = ['xray_source', 'pilatus', 'Motor_BeamStop_X', 'Motor_BeamStop_Y', 'Motor_Sample_X',
                        'Motor_Sample_Y']

    script = """
        #initialization of variables
        set('samplenames',_scriptargs[0])
        set('nimages',_scriptargs[1])
        set('exptime',_scriptargs[2])
        set('emptyname',_scriptargs[3])
        # initialization of instrument
        print('Initializing the instrument for transmission measurement')
        shutter('close')
        xray_power('low')
        beamstop('out')

        @startloop
            set('currentsample', samplenames.pop())
            print('Measuring transmission for sample',currentsample)
            print('Exposing dark current')
            exposemulti(exptime, nimages, _config['path']['prefixes']['tra'], 0.02, {'sample':currentsample, 'what':'dark', 'nimages':nimages})
            print('Exposing empty beam')
            sample(emptyname)
            shutter('open')
            exposemulti(exptime, nimages, _config['path']['prefixes']['tra'], 0.02, {'sample':currentsample, 'what':'empty', 'nimages':nimages})
            shutter('close')
            print('Exposing sample')
            sample(currentsample)
            shutter('open')
            exposemulti(exptime, nimages, _config['path']['prefixes']['tra'], 0.02, {'sample':currentsample, 'what':'sample', 'nimages':nimages})
            shutter('close')
            goif('startloop', len(samplenames)>0)
        print('End of transmission measurements, moving beamstop into the beam')
        beamstop('in')
        end()
        """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 4:
            raise CommandArgumentError('Command {} requires exactly four positional arguments.'.format(self.name))
        if not self.services['accounting'].has_privilege(PRIV_MOVEMOTORS):
            raise CommandError('Insufficient privileges to move motors.')
        self.samplenames = self.args[0]
        if isinstance(self.samplenames, str):
            self.samplenames = [self.samplenames]
        self.nimages = int(self.args[1])
        if self.nimages <= 2:
            raise CommandArgumentError('Number of images must be larger than two.')
        self.exptime = float(self.args[2])
        if self.exptime < 1e-6 or self.exptime > 1e6:
            raise CommandArgumentError('Exposure time must be between 1e-6 and 1e6 seconds.')
        self.emptyname = str(self.args[3])
        self.intensities = {}
        self.fsns_currently_exposed = []
        self.exposurestartdate = None
        self.current_sample = None
        self.what_are_we_doing = 'Initializing...'

    def validate(self):
        for s in self.samplenames:
            if s not in self.services['samplestore']:
                raise CommandArgumentError('Unknown sample: {}'.format(s))
        if self.emptyname not in self.services['samplestore']:
            raise CommandArgumentError('Unknown empty sample: {}'.format(self.emptyname))
        if not self.services['accounting'].has_privilege(PRIV_BEAMSTOP):
            raise CommandError('Insufficient privileges to move the beamstop')

    def on_pulse(self):
        if not self.intensities:
            self.emit('pulse', self.what_are_we_doing)

    def execute(self):
        self._expanalyzerconnection = [self.services['exposureanalyzer'].connect(
            'transmdata', self.on_transmdata),
            self.services['exposureanalyzer'].connect(
                'error', lambda ea, prefix, fsn, exc, tb: self.on_error(
                    ea, self.services['filesequence'].exposurefileformat(
                        prefix, fsn), exc, tb))]
        self.emit('message', 'Starting transmission measurement of {:d} sample(s).'.format(len(self.samplenames)))
        # initialize the system:
        # 1) close shutter
        # 2) X-ray source to low power
        # 3) beamstop out
        # 4) initialize detector: nimages, imgpath, exptime, expperiod
        self.get_device('xray_source').shutter(False)
        self.get_device('xray_source').set_power('low')

    def on_variable_change(self, device, variablename, newvalue):
        if device.name == self.get_device('xray_source').name:
            if variablename == '_status' and newvalue == 'Low power':
                # move beamstop out
                self.get_motor('BeamStop_X').moveto(
                    self.config['beamstop']['out'][0]
                )
            elif variablename == 'shutter' and newvalue == True:
                # start exposure.
                if self.what_are_we_doing == 'Moving empty sample into the beam.':
                    self.what_are_we_doing = 'Exposing empty beam for sample {}'.format(self.current_sample)
                else:
                    self.what_are_we_doing = 'Exposing sample {}'.format(self.current_sample)
                self.start_exposure()
            elif variablename == 'shutter' and newvalue == False:
                # Shutter has been closed after an exposure. Try to load all exposure files:
                t = time.monotonic()
                prefix = self.config['path']['prefixes']['tra']
                while not all([self.services['filesequence'].is_cbf_ready(
                        self.services['filesequence'].exposurefileformat(
                            prefix, f)) for f in self.fsns_currently_exposed]):
                    if time.monotonic() - t > 5:
                        raise CommandTimeoutError('Timeout on waiting for exposure files.')
                what = [w for w in ['dark', 'empty', 'sample'] if w not in self.intensities[self.current_sample]][0]

                for i, f in enumerate(self.fsns_currently_exposed):
                    self.services['filesequence'].new_exposure(
                        f, self.services['filesequence'].exposurefileformat(
                            prefix, f),
                        prefix, self.exposurestartdate + datetime.timedelta(0, (self.exptime + 0.003) * i),
                        what=what, sample=self.current_sample)
                # we expect transmdata signals from the exposureanalyzer service. However, we can
                # start exposing the next part.
                if what == 'dark':
                    # We will measure empty next. Move the sample there.
                    self.what_are_we_doing = 'Moving empty sample into the beam.'
                    self.get_motor('Sample_X').moveto(
                        self.services['samplestore'].get_sample(self.emptyname).positionx.val
                    )
                elif what == 'empty':
                    # We measure the sample next. Move the sample to the beam.
                    self.what_are_we_doing = 'Moving sample {} into the beam.'.format(self.current_sample)
                    self.get_motor('Sample_X').moveto(
                        self.services['samplestore'].get_sample(self.current_sample).positionx.val
                    )
                else:
                    assert what == 'sample'
                    # we have finished this sample. Go to the next one.
                    self.next_sample()
        elif device.name == self.get_device('detector').name:
            if variablename == 'imgpath':
                # detector initialization finished. Start first sample measurement.
                self.next_sample()
            elif variablename == '_status' and newvalue == 'exposing multi':
                self.exposurestartdate = datetime.datetime.now()
            elif variablename == '_status' and newvalue == 'idle':
                # exposure finished. Close the shutter.
                self.get_device('xray_source').shutter(False)

    def next_sample(self):
        try:
            self.current_sample = [s for s in self.samplenames if s not in self.intensities][0]
        except IndexError:
            # we are ready with all samples: do nothing..
            return
        self.intensities[self.current_sample] = {}
        # Commence dark exposure. The X-ray shutter is closed: this is good for us.
        self.what_are_we_doing = 'Exposing dark for sample {}'.format(self.current_sample)
        self.start_exposure()

    def start_exposure(self):
        self.fsns_currently_exposed = self.services['filesequence'].get_nextfreefsns(
            self.config['path']['prefixes']['tra'],
            self.nimages)
        self.get_device('detector').expose(
            self.services['filesequence'].exposurefileformat(
                self.config['path']['prefixes']['tra'],
                self.fsns_currently_exposed[0]
            )
        )

    def on_motor_stop(self, motor, targetreached):
        if not targetreached:
            self.emit('fail', 'Positioning error on motor {}'.format(motor.name))
            self.idle_return(None)
        if (motor.name == 'BeamStop_X' and abs(
                    motor.where() - self.config['beamstop']['out'][0]) < 0.001):
            # Beamstop X is out, move Beamstop Y to out as well.
            self.get_motor('BeamStop_Y').moveto(
                self.config['beamstop']['out'][1]
            )
        elif (motor.name == 'BeamStop_Y' and abs(
                    motor.where() - self.config['beamstop']['out'][1]) < 0.001):
            # Beamstop Y is out, we can initialize the detector.
            self.get_device('pilatus').set_variable('exptime', self.exptime)
            self.get_device('pilatus').set_variable('expperiod', self.exptime + 0.003)
            self.get_device('pilatus').set_variable(
                'imgpath', self.config['path']['directories']['images_detector'][0] + '/' +
                           self.config['path']['prefixes']['tra'])
        elif (motor.name == 'BeamStop_X' and abs(
                    motor.where() - self.config['beamstop']['in'][0]) < 0.001):
            # Beamstop X is in, move Beamstop Y in as well.
            self.get_motor('BeamStop_Y').moveto(
                self.config['beamstop']['in'][1]
            )
        elif (motor.name == 'BeamStop_Y' and abs(
                    motor.where() - self.config['beamstop']['in'][1]) < 0.001):
            # Beamstop Y is in, finish the command.
            self.idle_return(None)
        elif (motor.name == 'Sample_X'):
            if self.what_are_we_doing == 'Moving empty sample into the beam.':
                self.get_motor('Sample_Y').moveto(
                    self.services['samplestore'].get_sample(self.emptyname).positiony.val)
            else:
                # we have been moving the sample into the beam
                self.get_motor('Sample_Y').moveto(
                    self.services['samplestore'].get_sample(self.current_sample).positiony.val)
        elif (motor.name == 'Sample_Y'):
            # open shutter
            self.get_device('xray_source').shutter(True)

    def on_transmdata(self, exposureanalyzer, prefix, fsn, samplename, what, counter):
        if what not in self.intensities[samplename]:
            self.intensities[samplename][what] = []
        assert isinstance(self.intensities[samplename][what], list)
        self.intensities[samplename][what].append(counter)
        if len(self.intensities[samplename][what]) < self.nimages:
            return False
        self.intensities[samplename][what] = ErrorValue(np.mean(self.intensities[samplename][what]),
                                                        np.std(self.intensities[samplename][what]))
        self.emit('message', 'I_{} for sample {} is: {}'.format(
            what, samplename, self.intensities[samplename][what].tostring()))
        self.emit('detail', (what, samplename, self.intensities[samplename][what]))
        if what == 'sample':
            transm = ((self.intensities[samplename]['sample'] -
                       self.intensities[samplename]['dark']) /
                      (self.intensities[samplename]['empty'] -
                       self.intensities[samplename]['dark']))
            sam = self.services['samplestore'].get_sample(samplename)
            sam.transmission = transm
            self.services['samplestore'].set_sample(sam.title, sam)
            self.emit('message',
                      'Transmission value {} has been saved for sample {}.'.format(transm.tostring(), sam.title))
            self.emit('detail', ('transmission', samplename, transm))
            if len(self.samplenames) == len(self.intensities):
                # we are finished. Move the beamstop back in the beam.
                self.get_motor('BeamStop_X').moveto(
                    self.config['beamstop']['in'][0]
                )
        return False

    def cleanup(self, *args, **kwargs):
        for c in self._expanalyzerconnection:
            self.services['exposureanalyzer'].disconnect(c)
        self._expanalyzerconnection = []
        super().cleanup(*args, **kwargs)
