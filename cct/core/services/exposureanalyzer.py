import logging
import multiprocessing
import os
import pickle
import queue
import resource
import traceback
from logging.handlers import QueueHandler

import numpy as np
from gi.repository import GLib, GObject
from sastool.io.twodim import readcbf
from sastool.misc.easylsq import nonlinear_odr
from scipy.io import loadmat

from .service import Service, ServiceError
from ..utils.errorvalue import ErrorValue
from ..utils.geometrycorrections import solidangle, angledependentabsorption, angledependentairtransmission
from ..utils.io import write_legacy_paramfile
from ..utils.pathutils import find_in_subfolders
from ..utils.sasimage import SASImage

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DataReductionEnd(Exception):
    pass


class QueueLogHandler(QueueHandler):
    def prepare(self, record):
        return (None, 'log', record)


def get_statistics(matrix, masktotal=None, mask=None):
    """Calculate different statistics of a detector image, such as sum, max,
    center of gravity, etc."""
    assert (isinstance(matrix, np.ndarray))
    if mask is None:
        mask = 1
    if masktotal is None:
        masktotal = 1
    result = {}
    matrixorig = matrix
    for prefix, mask in [('total_', masktotal), ('', mask)]:
        matrix = matrixorig * mask
        x = np.arange(matrix.shape[0])
        y = np.arange(matrix.shape[1])
        result[prefix + 'sum'] = (matrix).sum()
        result[prefix + 'max'] = (matrix).max()
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


class ExposureAnalyzer(Service):
    """This service works as a separate process. Every time a new exposure is
    finished, it must be `.submit()`-ted to this process, which will carry out
    computationally more intensive tasks in the background. The tasks to be
    done depend on the filename prefix:

    crd: carry out the on-line data reduction on the image
    scn: calculate various statistics on the image and return a tuple of them,
        to be added to the scan dataset
    """
    __gsignals__ = {
        'error': (GObject.SignalFlags.RUN_FIRST, None, (str, int, object, str)),
        'scanpoint': (GObject.SignalFlags.RUN_FIRST, None, (str, int, object)),
        'datareduction-done': (GObject.SignalFlags.RUN_FIRST, None, (str, int, object)),
        'transmdata': (GObject.SignalFlags.RUN_FIRST, None, (str, int, object)),
        'image': (GObject.SignalFlags.RUN_FIRST, None, (str, int, object, object, object)),
        'idle': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'telemetry': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, *args, **kwargs):
        self._logger = logger
        Service.__init__(self, *args, **kwargs)
        self._backendprocess = multiprocessing.Process(
            target=self._backgroundworker, daemon=True)
        self._queue_to_backend = multiprocessing.Queue()
        self._queue_to_frontend = multiprocessing.Queue()
        self._handler = GLib.idle_add(self._idle_function)
        # A copy of the config hierarchy will be inherited by the back-end
        # process. Note that updates to instrument.config won't affect us,
        # since we are running in a different process
        self._config = self.instrument.config
        self._backendprocess.start()
        self._working = {}

    def get_mask(self, maskname):
        if not hasattr(self, '_masks'):
            self._masks = {}
        try:
            return self._masks[maskname]
        except KeyError:
            if not os.path.isabs(maskname):
                filename = find_in_subfolders(self._config['path']['directories']['mask'],
                                              maskname)
            else:
                filename = maskname
            m = loadmat(filename)
            self._masks[maskname] = m[
                [k for k in m.keys() if not k.startswith('__')][0]].view(bool)
            return self._masks[maskname]

    def get_telemetry(self):
        self._queue_to_backend.put_nowait(('_telemetry', None, None, None))

    def _backgroundworker(self):
        self._logger = logging.getLogger(__name__ + '::backgroundprocess')
        if not self._logger.hasHandlers():
            self._logger.propagate = False
            self._logger.addHandler(QueueLogHandler(self._queue_to_frontend))
            self._logger.addHandler(logging.StreamHandler())
            self._logger.setLevel(logger.level)
        while True:
            prefix, fsn, filename, args = self._queue_to_backend.get()
            #            self._logger.debug(
            #                'Exposureanalyzer background process got work: %s, %d, %s, %s' % (prefix, fsn, filename, str(args)))
            if not prefix.startswith('_'):
                cbfdata = None
                for fn in [filename, os.path.split(filename)[-1]]:
                    for subpath in [prefix, '']:
                        try:
                            cbfdata = readcbf(os.path.join(self._config['path']['directories']['images'],
                                                           subpath, fn))[0]
                            break
                        except FileNotFoundError as fe:
                            cbfdata = (fe, traceback.format_exc())
                if isinstance(cbfdata, tuple) and (isinstance(cbfdata[0], FileNotFoundError)):
                    # could not load cbf file
                    self._queue_to_frontend.put_nowait(((prefix, fsn), 'error', cbfdata))
                    continue
            else:
                cbfdata = None
            if prefix == '_exit':
                break
            elif prefix == '_config':
                self._config = filename
            elif prefix == '_telemetry':
                self._queue_to_frontend.put_nowait((None, 'telemetry', self._get_telemetry()))
            elif prefix == self._config['path']['prefixes']['crd']:
                # data reduction needed
                try:
                    maskfilename=args[0]['geometry']['mask']
                    logger.debug('Mask found from parameter dictionary: '+maskfilename)
                except (KeyError,TypeError):
                    maskfilename=self._config['geometry']['mask']
                    logger.debug('Using default mask from _config hierarchy: '+maskfilename)
                try:
                    mask = self.get_mask(maskfilename)
                    im = self.datareduction(cbfdata, mask, args[0])
                    self.savecorrected(prefix, fsn, im)
                    self._queue_to_frontend.put_nowait(
                        ((prefix, fsn), 'datareduction-done', (im,)))
                    self._queue_to_frontend.put_nowait(
                        ((prefix, fsn), 'image', (cbfdata, mask) + args))
                except Exception as exc:
                    self._queue_to_frontend.put_nowait(
                        ((prefix, fsn), 'error', (exc, traceback.format_exc())))
                    self._logger.error('Error in data reduction: %s, %s' % (str(exc), traceback.format_exc()))
            elif prefix == self._config['path']['prefixes']['tra']:
                # transmission measurement
                try:
                    transmmask = self.get_mask(self._config['transmission']['mask'])
                except (IOError, OSError, IndexError) as exc:
                    # could not load a mask file
                    self._queue_to_frontend.put_nowait(
                        ((prefix, fsn), 'error', (exc, traceback.format_exc())))
                else:
                    self._queue_to_frontend.put_nowait(
                        ((prefix, fsn), 'transmdata', args + ((cbfdata * transmmask).sum(),)))
            elif prefix == self._config['path']['prefixes']['scn']:
                try:
                    scanmask = self.get_mask(self._config['scan']['mask'])
                    scanmasktotal = self.get_mask(self._config['scan']['mask_total'])
                except (IOError, OSError, IndexError) as exc:
                    # could not load a mask file
                    self._queue_to_frontend.put_nowait(
                        ((prefix, fsn), 'error', (exc, traceback.format_exc())))
                else:
                    # scan point, we have to calculate something.
                    stat = get_statistics(cbfdata, scanmasktotal, scanmask)
                    stat['FSN'] = fsn
                    resultlist = tuple([args] + [stat[k]
                                                 for k in self._config['scan']['columns']])
                    self._queue_to_frontend.put_nowait(
                        ((prefix, fsn), 'scanpoint', resultlist))
            else:
                try:
                    mask = self.get_mask(self._config['geometry']['mask'])
                except (IOError, OSError, IndexError) as exc:
                    # could not load a mask file
                    self._queue_to_frontend.put_nowait(
                        ((prefix, fsn), 'error', (exc, traceback.format_exc())))
                else:
                    self._queue_to_frontend.put_nowait(
                        ((prefix, fsn), 'image', (cbfdata, mask) + args))

    def _idle_function(self):
        try:
            prefix_fsn, what, arguments = self._queue_to_frontend.get_nowait()
            self._logger.debug('what=%s' % what)
            if what in ['image', 'scanpoint', 'error', 'transmdata']:
                if prefix_fsn[0] in self._working:
                    self._working[prefix_fsn[0]] -= 1
                    if self._working[prefix_fsn[0]] < 0:
                        raise ServiceError(
                            'Working[%s]==%d less than zero!' % (prefix_fsn[0], self._working[prefix_fsn[0]]))
            self._logger.debug('Exposureanalyzer working on %d jobs' % sum(self._working.values()))
        except queue.Empty:
            return True
        if what == 'error':
            logger.error('Error in exposureanalyzer while treating exposure (prefix %s, fsn %d): %s %s' % (
            prefix_fsn[0], prefix_fsn[1], arguments[0], arguments[1]))
            self.emit(
                'error', prefix_fsn[0], prefix_fsn[1], arguments[0], arguments[1])
        elif what == 'scanpoint':
            self.emit('scanpoint', prefix_fsn[0], prefix_fsn[1], arguments)
        elif what == 'datareduction-done':
            self._logger.debug('Emitting datareduction-done message')
            self.emit('datareduction-done', prefix_fsn[0], prefix_fsn[1], arguments[0])
        elif what == 'transmdata':
            self.emit('transmdata', prefix_fsn[0], prefix_fsn[1], arguments)
        elif what == 'image':
            self.emit('image', prefix_fsn[0], prefix_fsn[1], arguments[0], arguments[1], arguments[2])
        elif what == 'telemetry':
            self.emit('telemetry', arguments)
        elif what == 'log':
            logger.handle(arguments)
        if all([self._working[k] <= 0 for k in self._working]):
            self.emit('idle')
        return True

    def submit(self, fsn, filename, prefix, args):
        logger.debug('Submitting work to exposureanalyzer. Prefix: %s, fsn: %d. Filename: %s' % (prefix, fsn, filename))
        self._queue_to_backend.put_nowait((prefix, fsn, filename, args))
        if prefix not in self._working:
            self._working[prefix] = 0
        self._working[prefix] += 1

    def _get_telemetry(self):
        return {'processname': multiprocessing.current_process().name,
                'self': resource.getrusage(resource.RUSAGE_SELF),
                'children': resource.getrusage(resource.RUSAGE_CHILDREN),
                'inqueuelen': self._queue_to_backend.qsize()}

    def prescaling(self, im):
        im /= im.params['exposure']['exptime']
        transmission = ErrorValue(im.params['sample']['transmission.val'], im.params['sample']['transmission.err'])
        im /= transmission
        im.params['datareduction']['history'].append('Divided by exposure time')
        im.params['datareduction']['history'].append('Divided by transmission: %s' % str(transmission))
        im.params['datareduction']['statistics']['02_prescaling']=im.get_statistics()
        self._logger.debug('Done prescaling FSN %d' % im.params['exposure']['fsn'])
        return im

    def subtractbackground(self, im):
        if im.params['sample']['title'] == self._config['datareduction']['backgroundname']:
            self._lastbackground = im
            self._logger.debug('Done bgsub FSN %d: this is background' % im.params['exposure']['fsn'])
            raise DataReductionEnd()
        if (abs(im.params['geometry']['truedistance'] -
                    self._lastbackground.params['geometry']['truedistance']) <
                self._config['datareduction']['distancetolerance']):
            im -= self._lastbackground
            im.params['datareduction']['history'].append(
                'Subtracted background FSN #%d' % self._lastbackground.params['exposure']['fsn'])
            im.params['datareduction']['emptybeamFSN'] = self._lastbackground.params['exposure']['fsn']
        else:
            raise ServiceError('Last seen background measurement does not match the exposure under reduction.')
        im.params['datareduction']['statistics']['03_subtractbackground']=im.get_statistics()
        self._logger.debug('Done bgsub FSN %d' % im.params['exposure']['fsn'])
        return im

    def correctgeometry(self, im):
        tth = im.twotheta_rad
        im.params['datareduction']['tthval_statistics']=self._get_matrix_statistics(tth.val)
        im.params['datareduction']['ttherr_statistics']=self._get_matrix_statistics(tth.err)
        corr_sa=solidangle(tth.val, tth.err, im.params['geometry']['truedistance'],
                           im.params['geometry']['truedistance.err'], im.params['geometry']['pixelsize'])
        im *= corr_sa
        im.params['datareduction']['history'].append('Corrected for solid angle')
        im.params['datareduction']['solidangle_matrixval_statistics']=self._get_matrix_statistics(corr_sa.val)
        im.params['datareduction']['solidangle_matrixerr_statistics']=self._get_matrix_statistics(corr_sa.err)
        corr_ada = angledependentabsorption(tth.val, tth.err, im.params['sample']['transmission.val'],
                                            im.params['sample']['transmission.err'])
        im *= corr_ada
        im.params['datareduction']['angledependentabsorption_matrixval_statistics']=self._get_matrix_statistics(corr_ada.val)
        im.params['datareduction']['angledependentabsorption_matrixerr_statistics']=self._get_matrix_statistics(corr_ada.err)
        im.params['datareduction']['history'].append('Corrected for angle-dependent absorption')
        if 'vacuum_pressure' in im.params['environment']:
            corr_adat = angledependentairtransmission(tth.val, tth.err, im.params['environment']['vacuum_pressure'],
                                                im.params['geometry']['truedistance'],
                                                im.params['geometry']['truedistance.err'],
                                                self._config['datareduction']['mu_air'],
                                                self._config['datareduction']['mu_air.err'])
            im *=corr_adat
            im.params['datareduction']['angledependentairtransmission_matrixval_statistics']=self._get_matrix_statistics(corr_adat.val)
            im.params['datareduction']['angledependentairtransmission_matrixerr_statistics']=self._get_matrix_statistics(corr_adat.err)
            im.params['datareduction']['history'].append(
                'Corrected for angle-dependent air absorption. Pressure: %f mbar' % (
                    im.params['environment']['vacuum_pressure']))
        else:
            im.params['datareduction']['history'].append(
                'Skipped angle-dependent air absorption correction: no pressure value.')
        im.params['datareduction']['statistics']['04_correctgeometry']=im.get_statistics()
        self._logger.debug('Done correctgeometry FSN %d' % im.params['exposure']['fsn'])
        return im

    def dividebythickness(self, im):
        im /= ErrorValue(im.params['sample']['thickness.val'], im.params['sample']['thickness.err'])
        im.params['datareduction']['statistics']['05_dividebythickness']=im.get_statistics()
        self._logger.debug('Done dividebythickness FSN %d' % im.params['exposure']['fsn'])
        return im

    def absolutescaling(self, im):
        if im.params['sample']['title'] == self._config['datareduction']['absintrefname']:
            dataset = np.loadtxt(self._config['datareduction']['absintrefdata'])
            self._logger.debug('Q-range of absint dataset: %g to %g, %d points.' % (
                dataset[:, 0].min(), dataset[:, 0].max(), len(dataset[:, 0])))
            q, dq, I, dI, area = im.radial_average(qrange=dataset[:, 0], raw_result=True)
            dataset = dataset[area > 0, :]
            I = I[area > 0]
            dI = dI[area > 0]
            q = q[area > 0]
            self._logger.debug('Common q-range: %g to %g, %d points.' % (q.min(), q.max(), len(q)))
            scalingfactor, stat = nonlinear_odr(I, dataset[:, 1], dI, dataset[:, 2], lambda x, a: a * x, [1])
            im.params['datareduction']['absintscaling']={'q':q,'area':area,'Imeas':I,'dImeas':dI,'Iref':dataset[:,1],'dIref':dataset[:,2],'factor.val':scalingfactor.val,'factor.err':scalingfactor.err,'stat':stat}
            scalingfactor = ErrorValue(scalingfactor.val,
                                       scalingfactor.err)  # convert from sastool's ErrorValue to ours
            self._logger.debug('Scaling factor: %s' % scalingfactor)
            self._logger.debug('Chi2: %f' % stat['Chi2_reduced'])
            self._lastabsintref = im
            self._absintscalingfactor = scalingfactor
            self._absintstat = stat
            self._absintqrange = q
            im.params['datareduction']['history'].append(
                'Determined absolute intensity scaling factor: %s. Reduced Chi2: %f. DoF: %d. This corresponds to beam flux %s photons*eta/sec' % (
                    self._absintscalingfactor, self._absintstat['Chi2_reduced'], self._absintstat['DoF'],
                    1 / self._absintscalingfactor))
            self._logger.debug('History:\n  ' + '\n  '.join(h for h in im.params['datareduction']['history']))
        if abs(im.params['geometry']['truedistance'] - self._lastabsintref.params['geometry']['truedistance']) < \
                self._config['datareduction']['distancetolerance']:
            im *= self._absintscalingfactor
            im.params['datareduction']['statistics']['06_absolutescaling']=im.get_statistics()
            im.params['datareduction']['history'].append(
                'Using absolute intensity factor %s from measurement FSN #%d for absolute intensity calibration.' % (
                    self._absintscalingfactor, self._lastabsintref.params['exposure']['fsn']))
            im.params['datareduction']['absintrefFSN'] = self._lastabsintref.params['exposure']['fsn']
            im.params['datareduction']['flux'] = (1 / self._absintscalingfactor).val
            im.params['datareduction']['flux.err'] = (1 / self._absintscalingfactor).err
            im.params['datareduction']['absintchi2'] = self._absintstat['Chi2_reduced']
            im.params['datareduction']['absintdof'] = self._absintstat['DoF']
            im.params['datareduction']['absintfactor'] = self._absintscalingfactor.val
            im.params['datareduction']['absintfactor.err'] = self._absintscalingfactor.err
            im.params['datareduction']['absintqmin'] = self._absintqrange.min()
            im.params['datareduction']['absintqmax'] = self._absintqrange.max()
        else:
            raise ServiceError(
                'S-D distance of the last seen absolute intensity reference measurement does not match the exposure under reduction.')
        self._logger.debug('Done absint FSN %d' % im.params['exposure']['fsn'])
        return im

    def savecorrected(self, prefix, fsn, im):
        npzname = os.path.join(self._config['path']['directories']['eval2d'],
                               prefix + '_%%0%dd' % self._config['path']['fsndigits'] % fsn + '.npz')
        np.savez_compressed(npzname, Intensity=im.val, Error=im.err)
        picklefilename = os.path.join(self._config['path']['directories']['eval2d'],
                                      prefix + '_%%0%dd' % self._config['path']['fsndigits'] % fsn + '.pickle')
        with open(picklefilename, 'wb') as f:
            pickle.dump(im.params, f)
        write_legacy_paramfile(picklefilename[:-len('.pickle')] + '.param', im.params)
        self._logger.debug('Done savecorrected FSN %d' % im.params['exposure']['fsn'])

    def datareduction(self, intensity, mask, params):
        im = SASImage(intensity, intensity ** 0.5, params, mask)
        im.params['datareduction'] = {'history': [], 'statistics':{'01_initial':im.get_statistics()}}
        try:
            self.prescaling(im)
            self.subtractbackground(im)
            self.correctgeometry(im)
            self.dividebythickness(im)
            self.absolutescaling(im)
        except DataReductionEnd:
            pass
        return im

    def sendconfig(self):
        self._queue_to_backend.put_nowait(('_config', None, self.instrument.config, None))

    def _get_matrix_statistics(self, matrix):
        return {'NaNs':np.isnan(matrix).sum(),'finites':np.isfinite(matrix).sum(),'negatives':(matrix<0).sum(),
                }
