import logging

import numpy as np

from .script import Script, CommandError
from ..instrument.privileges import PRIV_BEAMSTOP
from ..utils.errorvalue import ErrorValue

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Transmission(Script):
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

    def execute(self, interpreter, arglist, instrument, namespace):
        self._instrument = instrument
        if not self._instrument.accounting.has_privilege(PRIV_BEAMSTOP):
            raise CommandError('Insufficient privileges to move the beamstop')

        if isinstance(arglist[0], str):
            samplenames = [arglist[0]]
        else:
            samplenames = arglist[0]
        if len(arglist) < 2:
            nimages = self._instrument.config['transmission']['nimages']
        else:
            nimages = int(arglist[1])
        if nimages <= 2:
            raise CommandError('Number of images must be larger than 2 to allow for uncertainty approximation')

        if len(arglist) < 3:
            exptime = self._instrument.config['transmission']['exptime']
        else:
            exptime = float(arglist[2])
        if nimages <= 0:
            raise CommandError('Exposure time must be positive')

        if len(arglist) < 4:
            emptyname = self._instrument.config['transmission']['empty_sample']
        else:
            emptyname = arglist[3]

        self._instrument_connections = [
            instrument.exposureanalyzer.connect('transmdata', self.on_transmdata),
        ]
        self._intensities = {}
        self._instrument = instrument
        self._cannot_return_yet = True
        self._nsamples = len(samplenames)
        self.emit('message', 'Starting transmission measurement of {:d} sample(s).'.format(self._nsamples))
        Script.execute(self, interpreter, (samplenames, nimages, exptime, emptyname), instrument, namespace)

    def on_transmdata(self, exposureanalyzer, prefix, fsn, data):
        logger.debug('Transmission data received: {}, {:d}, {}'.format(prefix, fsn, data))
        samplename, what, nimages, I = data
        if samplename not in self._intensities:
            self._intensities[samplename] = {'dark': [], 'empty': [], 'sample': []}

        self._intensities[samplename][what].append(I)
        if len(self._intensities[samplename][what]) == nimages:
            self._intensities[samplename][what] = ErrorValue(
                np.mean(self._intensities[samplename][what]),
                np.std(self._intensities[samplename][what])
            )
            self.emit('message', 'I_{} for sample {} is: {}'.format(
                what, samplename, self._intensities[samplename][what].tostring()))
            self.emit('detail', (what, samplename, self._intensities[samplename][what]))
            if what == 'sample':
                transm = ((self._intensities[samplename]['sample'] -
                           self._intensities[samplename]['dark']) /
                          (self._intensities[samplename]['empty'] -
                           self._intensities[samplename]['dark']))
                sam = self._instrument.samplestore.get_sample(samplename)
                sam.transmission = transm
                self._instrument.samplestore.set_sample(sam.title, sam)
                self.emit('message',
                          'Transmission value {} has been saved for sample {}.'.format(transm.tostring(), sam.title))
                self.emit('detail', ('transmission', samplename, transm))
                if self._nsamples == len(self._intensities):
                    del self._cannot_return_yet

    def cleanup(self):
        logger.debug('Cleaning up transmission command.')
        try:

            for c in self._instrument_connections:
                self._instrument.exposureanalyzer.disconnect(c)
                logger.debug('Disconnected a handler from exposureanalyzer')
            del self._instrument_connections
        except AttributeError:
            pass
        logger.debug('Calling Script.cleanup()')
        return Script.cleanup(self)
