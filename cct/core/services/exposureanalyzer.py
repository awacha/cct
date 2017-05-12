import logging
import multiprocessing
import multiprocessing.queues
import os
import pickle
import queue
import time
import traceback
from logging.handlers import QueueHandler
from typing import Union, Dict

import numpy as np
from sastool.io.credo_cct import Exposure, Header
from sastool.io.twodim import readcbf
from sastool.misc.easylsq import nonlinear_odr
from sastool.misc.errorvalue import ErrorValue
from scipy.io import loadmat

from .service import Service, ServiceError
from ..devices.device.message import Message
from ..utils.callback import SignalFlags
from ..utils.geometrycorrections import solidangle, angledependentabsorption, angledependentairtransmission
from ..utils.io import write_legacy_paramfile
from ..utils.pathutils import find_in_subfolders
from ..utils.telemetry import TelemetryInfo
from ..utils.timeout import IdleFunction

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DataReductionEnd(Exception):
    pass


class QueueLogHandler(QueueHandler):
    def prepare(self, record):
        return Message('log', 0, 'exposureanalyzer_backend', logrecord=record)


def get_statistics(matrix: np.ndarray, masktotal: Union[np.ndarray, int, None],
                   mask: Union[np.ndarray, int, None] = None) -> Dict:
    """Calculate different statistics of a detector image, such as sum, max,
    center of gravity, etc."""
    assert (isinstance(matrix, np.ndarray))
    if mask is None:
        mask = 1
    if masktotal is None:
        masktotal = 1
    assert isinstance(masktotal, np.ndarray) or isinstance(masktotal, int)
    assert isinstance(mask, np.ndarray) or isinstance(mask, int)
    result = {}
    matrixorig = matrix
    for prefix, mask in [('total_', masktotal), ('', mask)]:
        matrix = matrixorig * mask
        x = np.arange(matrix.shape[0])
        y = np.arange(matrix.shape[1])
        result[prefix + 'sum'] = matrix.sum()
        result[prefix + 'max'] = matrix.max()
        result[prefix + 'beamx'] = (matrix * x[:, np.newaxis]).sum() / result[prefix + 'sum']
        result[prefix + 'beamy'] = (matrix * y[np.newaxis, :]).sum() / result[prefix + 'sum']
        result[prefix + 'sigmax'] = (
                                        (matrix * (x[:, np.newaxis] - result[prefix + 'beamx']) ** 2).sum() /
                                        result[prefix + 'sum']) ** 0.5
        result[prefix + 'sigmay'] = (
                                        (matrix * (y[np.newaxis, :] - result[prefix + 'beamy']) ** 2).sum() /
                                        result[prefix + 'sum']) ** 0.5
        result[prefix + 'sigma'] = (result[prefix + 'sigmax'] ** 2 + result[prefix + 'sigmay'] ** 2) ** 0.5
    return result


# noinspection PyPep8Naming
class ExposureAnalyzer_Backend(object):
    """Background worker process of exposureanalyzer.
    
    Implements a similar message-passing communication as between the front-
    and backends of the devices. Messages (instances of 
    cct.core.device.device.message.Message) are passed through queues. The
    following message types are accepted:
    
    'analyze': analyze an exposure.
        'prefix': the file prefix
        'filename': the filename
        'fsn': the file sequence number
        'param': the parameter dictionary
    'exit': finish working and exit.
    'config': a config dictionary is sent in the 'configdict' field.
    """
    name = 'exposureanalyzer_backend'

    telemetry_interval = 1

    def __init__(self, loglevel, config, inqueue, outqueue):
        self._logger = logging.getLogger(__name__ + '::' + self.name + '__backgroundprocess')
        self._logger.propagate = False
        self.inqueue = inqueue
        self.outqueue = outqueue
        self.config = config
        self._msgid = 0
        if not self._logger.hasHandlers():
            self._logger.propagate = False
            self._logger.addHandler(QueueLogHandler(self.outqueue))
            self._logger.addHandler(logging.StreamHandler())
            self._logger.setLevel(loglevel)
        self.masks = {}
        self._lastdarkbackground = None
        self._lastabsintref = None
        self._lastbackground = None
        self._absintscalingfactor = None
        self._absintqrange = None
        self._absintstat = None
        self._lasttelemetry = 0

    def get_telemetry(self):
        self._lasttelemetry = time.monotonic()
        tm = TelemetryInfo()
        return tm

    def send_to_frontend(self, type_: str, **kwargs):
        self._msgid += 1
        self.outqueue.put_nowait(Message(type_, self._msgid, self.name, **kwargs))

    def worker(self):
        try:
            while True:
                assert isinstance(self.inqueue, multiprocessing.queues.Queue)
                if (time.monotonic() - self._lasttelemetry) > self.telemetry_interval:
                    # forge a telemetry request message.
                    message = Message('telemetry', 0, self.name)
                else:
                    try:
                        message = self.inqueue.get(True, self.telemetry_interval)
                    except queue.Empty:
                        continue
                assert isinstance(message, Message)
                if message['type'] == 'exit':
                    break  # the while True loop
                elif message['type'] == 'config':
                    self.config = message['configdict']
                elif message['type'] == 'telemetry':
                    self.send_to_frontend('telemetry', telemetry=self.get_telemetry())
                elif message['type'] == 'analyze':
                    self._logger.debug(
                        'Got work: prefix = {}, fsn = {}, filename = {}'.format(message['prefix'], message['fsn'],
                                                                                message['filename']))
                    cbfdata = None
                    for fn in [message['filename'], os.path.split(message['filename'])[-1]]:
                        self._logger.debug('Trying filename form: {}'.format(fn))
                        for subpath in [message['prefix'], '']:
                            try:
                                self._logger.debug('Trying subpath {}'.format(subpath))
                                cbfdata = readcbf(os.path.join(self.config['path']['directories']['images'],
                                                               subpath, fn))[0]
                                self._logger.debug('File found in subpath {}'.format(subpath))
                                break
                            except FileNotFoundError as fe:
                                cbfdata = (fe, traceback.format_exc())
                            except Exception as ex:
                                self.send_to_frontend('error', exception=ex, traceback=traceback.format_exc(),
                                                      fsn=message['fsn'], prefix=message['prefix'])
                                raise
                        if isinstance(cbfdata, np.ndarray):
                            # the file has been found, do not try to load it in a different form.
                            break
                    if isinstance(cbfdata, tuple) and (isinstance(cbfdata[0], FileNotFoundError)):
                        # could not load cbf file, send a message to the frontend.
                        self._logger.error('Cannot load file: {}'.format(message['filename']))
                        self.send_to_frontend('error', exception=cbfdata[0],
                                              traceback=cbfdata[1], fsn=message['fsn'],
                                              prefix=message['prefix'])
                        self.send_to_frontend('done', prefix=message['prefix'], fsn=message['fsn'])
                        continue
                    self._logger.debug('File {} loaded successfully.'.format(message['filename']))
                    assert isinstance(cbfdata, np.ndarray)
                    self._logger.debug('Survived assertion')
                    if message['prefix'] == self.config['path']['prefixes']['crd']:
                        self._logger.debug('Data reduction needed.')
                        # data reduction needed
                        try:
                            maskfilename = message['param']['geometry']['mask']
                            logger.debug('Mask found from parameter dictionary: ' + maskfilename)
                        except (KeyError, TypeError):
                            maskfilename = self.config['geometry']['mask']
                            logger.debug('Using default mask from config dictionary: ' + maskfilename)
                        try:
                            mask = self.get_mask(maskfilename)
                            assert isinstance(mask, np.ndarray)
                            im = self.datareduction(cbfdata, mask, message['param'])
                            self.savecorrected(message['prefix'], message['fsn'], im)
                            self.send_to_frontend('datareduction-done', prefix=message['prefix'], fsn=message['fsn'],
                                                  image=im)
                            self.send_to_frontend('image', prefix=message['prefix'], fsn=message['fsn'],
                                                  data=cbfdata, mask=mask, param=message['param'])
                        except Exception as exc:
                            self.send_to_frontend('error', prefix=message['prefix'], fsn=message['fsn'],
                                                  exception=exc, traceback=traceback.format_exc())
                            self._logger.error(
                                'Error in data reduction: {}, {}'.format(str(exc), traceback.format_exc()))
                        self.send_to_frontend('done', prefix=message['prefix'], fsn=message['fsn'])
                    elif message['prefix'] == self.config['path']['prefixes']['tra']:  # transmission measurement
                        self._logger.debug('This is a transmission measurement.')
                        try:
                            transmmask = self.get_mask(self.config['transmission']['mask'])
                            assert isinstance(transmmask, np.ndarray)
                        except (IOError, OSError, IndexError) as exc:
                            # could not load a mask file
                            self.send_to_frontend('error', prefix=message['prefix'], fsn=message['fsn'],
                                                  exception=exc, traceback=traceback.format_exc())
                            self.send_to_frontend('done', prefix=message['prefix'], fsn=message['fsn'])
                        else:
                            self.send_to_frontend('transmdata', prefix=message['prefix'], fsn=message['fsn'],
                                                  data=(cbfdata * transmmask).sum(), what=message['what'],
                                                  sample=message['sample'], )
                            self.send_to_frontend('done', prefix=message['prefix'], fsn=message['fsn'])
                    elif message['prefix'] == self.config['path']['prefixes']['scn']:
                        self._logger.debug('This is a scan point.')
                        try:
                            scanmask = self.get_mask(self.config['scan']['mask'])
                            scanmasktotal = self.get_mask(self.config['scan']['mask_total'])
                        except (IOError, OSError, IndexError) as exc:
                            # could not load a mask file
                            self.send_to_frontend('error', prefix=message['prefix'], fsn=message['fsn'], exception=exc,
                                                  traceback=traceback.format_exc())
                            self.send_to_frontend('done', prefix=message['prefix'], fsn=message['fsn'])
                            continue
                        assert isinstance(scanmask, np.ndarray)
                        assert isinstance(scanmasktotal, np.ndarray)
                        self._logger.debug('We have the scan masks')
                        # scan point, we have to calculate something.
                        stat = get_statistics(cbfdata, scanmasktotal, scanmask)
                        self._logger.debug('We have the statistics')
                        stat['FSN'] = message['fsn']
                        resultlist = tuple([message['position']] + [stat[k]
                                                                    for k in self.config['scan']['columns']])
                        self._logger.debug('Sending the image')
                        self.send_to_frontend('image', prefix=message['prefix'], fsn=message['fsn'],
                                              param=message['param'], mask=scanmasktotal, data=cbfdata)
                        self._logger.debug('Sending the scanpoint')
                        self.send_to_frontend('scanpoint', prefix=message['prefix'], fsn=message['fsn'],
                                              counters=resultlist, position=message['position'])
                        self.send_to_frontend('done', prefix=message['prefix'], fsn=message['fsn'])

                    else:
                        self._logger.debug('Unknown prefix, just sending back image.')
                        try:
                            mask = self.get_mask(self.config['geometry']['mask'])
                        except (IOError, OSError, IndexError) as exc:
                            # could not load a mask file
                            self.send_to_frontend('error', prefix=message['prefix'], fsn=message['fsn'], exception=exc,
                                                  traceback=traceback.format_exc())
                        else:
                            self.send_to_frontend('image', prefix=message['prefix'], fsn=message['fsn'], data=cbfdata,
                                                  mask=mask, param=message['param'])
                        self.send_to_frontend('done', prefix=message['prefix'], fsn=message['fsn'])
        except Exception as exc:
            self.send_to_frontend('error', prefix='', fsn=0, exception=exc, traceback=traceback.format_exc())
        self.send_to_frontend('exited', prefix=None, fsn=None)

    def get_mask(self, maskname: str) -> np.ndarray:
        self._logger.debug('Getting mask: {}'.format(maskname))
        try:
            return self.masks[maskname]
        except KeyError:
            self._logger.debug('Mask {} not found, trying to load it.'.format(maskname))
            if not os.path.isabs(maskname):
                filename = find_in_subfolders(self.config['path']['directories']['mask'],
                                              maskname)
            else:
                filename = maskname
            try:
                m = loadmat(filename)
            except FileNotFoundError:
                filename = find_in_subfolders(self.config['path']['directories']['mask'],
                                              os.path.split(maskname)[-1])
                m = loadmat(filename)
            self.masks[maskname] = m[
                [k for k in m.keys() if not k.startswith('__')][0]].view(bool)
            self._logger.debug('Loaded mask {} from file {}'.format(maskname, filename))
            return self.masks[maskname]

    def normalize_flux(self, im: Exposure, datared: Dict):
        im /= im.header.exposuretime
        datared['history'].append('Divided by exposure time')
        datared['statistics']['02_normalize_flux'] = im.get_statistics()
        self._logger.debug('Done normalizing by flux FSN {:d}'.format(im.header.fsn))
        return im, datared

    def subtractdarkbackground(self, im: Exposure, datared: Dict):
        if im.header.title == self.config['datareduction']['darkbackgroundname']:
            self._lastdarkbackground = im.mean()
            self._logger.debug('Determined background level: {:g} cps per pixel'.format(self._lastdarkbackground))
            self._logger.debug('Done darkbgsub FSN {:d}: this is dark background'.format(im.header.fsn))
            datared['history'].append(
                'This is a dark background measurement. Level: {:g} cps per pixel (overall {:g} cps)'.format(
                    self._lastdarkbackground, self._lastdarkbackground * im.shape[0] * im.shape[1]))
            raise DataReductionEnd()
        # otherwise subtract the background.
        im -= self._lastdarkbackground
        datared['history'].append(
            'Subtracted dark background level: {:g} cps per pixel (overall {:g} cps)'.format(
                self._lastdarkbackground, self._lastdarkbackground * im.shape[0] * im.shape[1]))
        datared['darkbackgroundlevel'] = self._lastdarkbackground
        datared['statistics']['03_subtractdarkbackground'] = im.get_statistics()
        self._logger.debug('Done darkbgsub FSN {:d}'.format(im.header.fsn))
        return im, datared

    def normalize_transmission(self, im: Exposure, datared: Dict):
        transmission = im.header.transmission
        im /= im.header.transmission
        datared['history'].append('Divided by transmission: ' + str(im.header.transmission))
        datared['statistics']['04_normalize_transmission'] = im.get_statistics()
        self._logger.debug('Done normalizing by transmission FSN {:d}'.format(im.header.fsn))
        return im, datared

    def subtractemptybeambackground(self, im: Exposure, datared: Dict):
        if im.header.title == self.config['datareduction']['backgroundname']:
            self._lastbackground = im
            self._logger.debug('Done bgsub FSN {:d}: this is background'.format(im.header.fsn))
            datared['history'].append('This is an empty beam measurement.')
            raise DataReductionEnd()
        if ((im.header.distance - self._lastbackground.header.distance).abs() <
                self.config['datareduction']['distancetolerance']):
            im -= self._lastbackground
            datared['history'].append(
                'Subtracted background FSN #{:d}'.format(self._lastbackground.header.fsn))
            datared['emptybeamFSN'] = self._lastbackground.header.fsn
        else:
            raise ServiceError('Last seen background measurement does not match the exposure under reduction.')
        datared['statistics']['05_subtractbackground'] = im.get_statistics()
        self._logger.debug('Done bgsub FSN {:d}'.format(im.header.fsn))
        return im, datared

    def correctgeometry(self, im: Exposure, datared: Dict):
        tth = im.twotheta
        assert isinstance(tth, ErrorValue)
        datared['tthval_statistics'] = self.get_matrix_statistics(tth.val)
        datared['ttherr_statistics'] = self.get_matrix_statistics(tth.err)
        assert im.header.pixelsizex == im.header.pixelsizey
        corr_sa = solidangle(tth.val, tth.err, im.header.distance.val,
                             im.header.distance.err, im.header.pixelsizex)
        im *= corr_sa
        datared['history'].append('Corrected for solid angle')
        datared['solidangle_matrixval_statistics'] = self.get_matrix_statistics(corr_sa.val)
        datared['solidangle_matrixerr_statistics'] = self.get_matrix_statistics(corr_sa.err)
        corr_ada = angledependentabsorption(tth.val, tth.err, im.header.transmission.val,
                                            im.header.transmission.err)
        im *= corr_ada
        datared['angledependentabsorption_matrixval_statistics'] = self.get_matrix_statistics(
            corr_ada.val)
        datared['angledependentabsorption_matrixerr_statistics'] = self.get_matrix_statistics(
            corr_ada.err)
        datared['history'].append('Corrected for angle-dependent absorption')
        try:
            vacuum = im.header.vacuum
        except KeyError:
            datared['history'].append(
                'Skipped angle-dependent air absorption correction: no pressure value.')
        else:
            corr_adat = angledependentairtransmission(tth.val, tth.err, vacuum,
                                                      im.header.distance.val,
                                                      im.header.distance.err,
                                                      self.config['datareduction']['mu_air'],
                                                      self.config['datareduction']['mu_air.err'])
            im *= corr_adat
            datared[
                'angledependentairtransmission_matrixval_statistics'] = self.get_matrix_statistics(corr_adat.val)
            datared[
                'angledependentairtransmission_matrixerr_statistics'] = self.get_matrix_statistics(corr_adat.err)
            datared['history'].append(
                'Corrected for angle-dependent air absorption. Pressure: {:f} mbar'.format(
                    im.header.vacuum))
        datared['statistics']['06_correctgeometry'] = im.get_statistics()
        self._logger.debug('Done correctgeometry FSN {:d}'.format(im.header.fsn))
        return im, datared

    def dividebythickness(self, im: Exposure, datared: Dict):
        im /= im.header.thickness
        datared['history'].append('Divided by thickness {:g} cm'.format(im.header.thickness))
        datared['statistics']['07_dividebythickness'] = im.get_statistics()
        self._logger.debug('Done dividebythickness FSN {:d}'.format(im.header.fsn))
        return im, datared

    def absolutescaling(self, im: Exposure, datared: Dict):
        if im.header.title == self.config['datareduction']['absintrefname']:
            self._logger.debug('History: {}'.format('\n'.join([h for h in datared['history']])))
            dataset = np.loadtxt(self.config['datareduction']['absintrefdata'])
            self._logger.debug('Q-range of absint dataset: {:g} to {:g}, {:d} points.'.format(
                dataset[:, 0].min(), dataset[:, 0].max(), len(dataset[:, 0])))
            testradavg = im.radial_average()
            self._logger.debug('Auto-Q-range of the measured dataset: {:g} to {:g}, {:d} points.'.format(
                testradavg.q.min(), testradavg.q.max(), len(testradavg)))
            # noinspection PyPep8Naming,PyPep8Naming
            q, dq, I, dI, area = im.radial_average(qrange=dataset[:, 0], raw_result=True)
            dataset = dataset[area > 0, :]
            # noinspection PyPep8Naming
            I = I[area > 0]
            # noinspection PyPep8Naming
            dI = dI[area > 0]
            q = q[area > 0]
            self._logger.debug('Common q-range: {:g} to {:g}, {:d} points.'.format(q.min(), q.max(), len(q)))
            scalingfactor, stat = nonlinear_odr(I, dataset[:, 1], dI, dataset[:, 2], lambda x, a: a * x, [1])
            datared['absintscaling'] = {'q': q, 'area': area, 'Imeas': I, 'dImeas': dI,
                                        'Iref': dataset[:, 1], 'dIref': dataset[:, 2],
                                        'factor.val': scalingfactor.val,
                                        'factor.err': scalingfactor.err, 'stat': stat}
            self._logger.debug('Scaling factor: ' + str(scalingfactor))
            self._logger.debug('Chi2: {:f}'.format(stat['Chi2_reduced']))
            self._lastabsintref = im
            self._absintscalingfactor = scalingfactor
            self._absintstat = stat
            self._absintqrange = q
            datared['history'].append(
                'This is an absolute intensity reference measurement. '
                'Determined absolute intensity scaling factor: {}. Reduced Chi2: {:f}. DoF: {:d}. '
                'This corresponds to beam flux {} photons*eta/sec'.format(
                    self._absintscalingfactor, self._absintstat['Chi2_reduced'], self._absintstat['DoF'],
                    1 / self._absintscalingfactor))
        if ((im.header.distance - self._lastabsintref.header.distance).abs() <
                self.config['datareduction']['distancetolerance']):
            im *= self._absintscalingfactor
            datared['statistics']['08_absolutescaling'] = im.get_statistics()
            datared['history'].append(
                'Using absolute intensity factor {} from measurement FSN #{:d} '
                'for absolute intensity calibration.'.format(
                    self._absintscalingfactor, self._lastabsintref.header.fsn))
            datared['history'].append('Absint factor was determined with Chi2 {:f} (DoF {:d})'.format(
                self._absintstat['Chi2_reduced'], self._absintstat['DoF']))
            datared['history'].append('Estimated flux: {} photons*eta/sec'.format(
                self._absintscalingfactor.__reciprocal__()))
            datared['absintrefFSN'] = self._lastabsintref.header.fsn
            datared['flux'] = self._absintscalingfactor.__reciprocal__().val
            datared['flux.err'] = self._absintscalingfactor.__reciprocal__().err
            datared['absintchi2'] = self._absintstat['Chi2_reduced']
            datared['absintdof'] = self._absintstat['DoF']
            datared['absintfactor'] = self._absintscalingfactor.val
            datared['absintfactor.err'] = self._absintscalingfactor.err
            datared['absintqmin'] = self._absintqrange.min()
            datared['absintqmax'] = self._absintqrange.max()
        else:
            raise ServiceError(
                'S-D distance of the last seen absolute intensity reference measurement '
                'does not match the exposure under reduction.')
        self._logger.debug('Done absint FSN ' + str(im.header.fsn))
        return im, datared

    def savecorrected(self, prefix: str, fsn: int, im: Exposure):
        npzname = os.path.join(self.config['path']['directories']['eval2d'],
                               '{prefix}_{fsn:0{fsndigits:d}d}.npz'.format(
                                   prefix=prefix, fsndigits=self.config['path']['fsndigits'], fsn=fsn))
        np.savez_compressed(npzname, Intensity=im.intensity, Error=im.error)
        picklefilename = os.path.join(self.config['path']['directories']['eval2d'],
                                      '{prefix}_{fsn:0{fsndigits:d}d}.pickle'.format(
                                          prefix=prefix, fsndigits=self.config['path']['fsndigits'], fsn=fsn))
        with open(picklefilename, 'wb') as f:
            pickle.dump(im.header.param, f)
        write_legacy_paramfile(picklefilename[:-len('.pickle')] + '.param', im.header.param)
        self._logger.debug('Done savecorrected FSN ' + str(im.header.fsn))

    def datareduction(self, intensity: np.ndarray, mask: np.ndarray, params: dict):
        im = Exposure(intensity, intensity ** 0.5, Header(params), mask)
        im.mask_negative()
        im.mask_nonfinite()
        im.mask_nan()
        self._logger.debug('Commencing data reduction of FSN #{:d} (sample {}).'.format(im.header.fsn, im.header.title))
        datared = {'history': [], 'statistics': {'01_initial': im.get_statistics()}}
        try:
            self.normalize_flux(im, datared)
            self.subtractdarkbackground(im, datared)
            self.normalize_transmission(im, datared)
            self.subtractemptybeambackground(im, datared)
            self.correctgeometry(im, datared)
            self.dividebythickness(im, datared)
            self.absolutescaling(im, datared)
        except DataReductionEnd:
            pass
        self._logger.info('Data reduction history for FSN #{:d}:\n  '.format(im.header.fsn) +
                          '\n  '.join(h for h in datared['history']))
        im.header.param['datareduction'] = datared
        return im

    # noinspection PyMethodMayBeStatic
    def get_matrix_statistics(self, matrix: np.ndarray):
        return {'NaNs': np.isnan(matrix).sum(),
                'finites': np.isfinite(matrix).sum(),
                'negatives': (matrix < 0).sum(),
                }

    @classmethod
    def create_and_run(cls, *args, **kwargs):
        obj = cls(*args, **kwargs)
        obj.worker()


class ExposureAnalyzer(Service):
    """This service works as a separate process. Every time a new exposure is
    finished, it must be `.submit()`-ted to this process, which will carry out
    computationally more intensive tasks in the background. The tasks to be
    done depend on the filename prefix:

    crd: carry out the on-line data reduction on the image
    scn: calculate various statistics on the image and return a tuple of them,
        to be added to the scan dataset
    """
    __signals__ = {
        # emitted on a failure. Arguments: prefix, fsn, exception, formatted
        # traceback
        'error': (SignalFlags.RUN_FIRST, None, (str, int, object, str)),
        # emitted on a new scan point. Arguments: prefix, fsn, motor position,
        # list of counter readings (floats)
        'scanpoint': (SignalFlags.RUN_FIRST, None, (str, int, float, object)),
        # emitted when data reduction is done on an image. Arguments. prefix,
        # fsn, corrected SASImage
        'datareduction-done': (SignalFlags.RUN_FIRST, None, (str, int, object)),
        # emitted when a part of transmission measurement is available. Arguments:
        # prefix, fsn, samplename, what ('sample', 'empty' or 'dark') and the
        # counter reading (float).
        'transmdata': (SignalFlags.RUN_FIRST, None, (str, int, str, str, float)),
        # Returned when an image is ready. Arguments: prefix, fsn, image
        # (np.array), params (dict), mask (np.array)
        'image': (SignalFlags.RUN_FIRST, None, (str, int, object, object, object)),
        # Emitted when telemetry data received from the backend.
        'telemetry': (SignalFlags.RUN_FIRST, None, (object,)),
    }

    name = 'exposureanalyzer'

    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self._queue_to_backend = multiprocessing.Queue()
        self._queue_to_frontend = multiprocessing.Queue()
        self._backendprocess = None
        self._handler = None
        self._msgid = 0
        # A copy of the config hierarchy will be inherited by the back-end
        # process. Note that updates to instrument.config won't affect us,
        # since we are running in a different process
        self.config = self.instrument.config
        self._working = {}

    def start(self):
        super().start()
        self._handler = IdleFunction(self._idle_function)
        self._backendprocess = multiprocessing.Process(
            target=ExposureAnalyzer_Backend.create_and_run,
            args=(logger.level, self.config, self._queue_to_backend,
                  self._queue_to_frontend))
        self._backendprocess.daemon = False
        self._backendprocess.start()

    def is_busy(self):
        return sum(self._working.values()) > 0

    def _idle_function(self):
        try:
            try:
                njobs_before = sum(self._working.values())
                message = self._queue_to_frontend.get_nowait()
                assert isinstance(message, Message)
                if message['type'] in ['done']:
                    assert message['prefix'] in self._working
                    self._working[message['prefix']] -= 1
                    if self._working[message['prefix']] < 0:
                        raise ServiceError(
                            'Working[{}]=={:d} less than zero!'.format(
                                message['prefix'], self._working[message['prefix']]))
                njobs = sum(self._working.values())
                if njobs:
                    logger.debug('Exposureanalyzer working on {:d} jobs'.format(njobs))
                elif njobs_before:
                    self.emit('idle-changed', True)
            except queue.Empty:
                return True
            if message['type'] == 'error':
                logger.error('Error in exposureanalyzer while treating exposure (prefix {}, fsn {:d}): {} {}'.format(
                    message['prefix'], message['fsn'], message['exception'], message['traceback']))
                self.emit(
                    'error', message['prefix'], message['fsn'], message['exception'], message['traceback'])
            elif message['type'] == 'scanpoint':
                logger.debug('New scan point at motor position {:f}'.format(message['position']))
                self.emit('scanpoint', message['prefix'], message['fsn'], message['position'], message['counters'])
            elif message['type'] == 'datareduction-done':
                logger.debug('Emitting datareduction-done message')
                self.emit('datareduction-done', message['prefix'], message['fsn'], message['image'])
            elif message['type'] == 'transmdata':
                logger.debug(
                    'transmission data for sample {} ({}): {}'.format(message['sample'], message['what'], message['data']))
                self.emit('transmdata', message['prefix'], message['fsn'], message['sample'], message['what'],
                          message['data'])
            elif message['type'] == 'image':
                logger.debug('New image received from exposureanalyzer backend: fsn: {}, prefix: {}'.format(message['fsn'],
                                                                                                            message[
                                                                                                                'prefix']))
                self.emit('image', message['prefix'], message['fsn'], message['data'], message['param'], message['mask'])
            elif message['type'] == 'telemetry':
                self.emit('telemetry', message['telemetry'])
            elif message['type'] == 'log':
                logger.handle(message['logrecord'])
            elif message['type'] == 'exited':
                self.emit('shutdown')
        except Exception as exc:
            logger.error('Error in the idle function for exposureanalyzer: {} {}'.format(
                exc, traceback.format_exc()))
        return True

    def submit(self, fsn, filename, prefix, **kwargs):
        logger.debug(
            'Submitting work to exposureanalyzer. Prefix: {}, fsn: {:d}. Filename: {}'.format(prefix, fsn, filename))

        self.send_to_backend('analyze', prefix=prefix, fsn=fsn, filename=filename, **kwargs)
        was_idle = not self.is_busy()
        if prefix not in self._working:
            self._working[prefix] = 0
        self._working[prefix] += 1
        logger.debug('Exposureanalyzer currently working on {:d} jobs.'.format(sum(self._working.values())))
        if was_idle:
            self.emit('idle-changed', False)

    def update_config(self, dictionary):
        self.send_to_backend('config', configdict=dictionary)

    def stop(self):
        if self._backendprocess.is_alive():
            self.send_to_backend('exit')
        else:
            self.emit('shutdown')

    def send_to_backend(self, msgtype, **kwargs):
        self._msgid += 1
        self._queue_to_backend.put_nowait(Message(msgtype, self._msgid, 'exposureanalyzer_frontend', **kwargs))

    def do_scanpoint(self, prefix, fsn, position, counters):
        self.instrument.services['filesequence'].write_scandataline(position, counters)
        return False

    def do_shutdown(self):
        if self._handler is not None:
            self._handler.stop()
            self._handler = None
        self._backendprocess.join()
        self.starttime = None
