import logging
import multiprocessing
import os
import queue
import traceback

import numpy as np
from gi.repository import GLib, GObject
from sastool.io.twodim import readcbf
from scipy.io import loadmat

from .filesequence import find_in_subfolders
from .service import Service

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_statistics(matrix, masktotal=None, mask=None):
    """Calculate different statistics of a detector image, such as sum, max,
    center of gravity, etc."""
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
        'datareduction-done': (GObject.SignalFlags.RUN_FIRST, None, (str, int)),
        'transmdata': (GObject.SignalFlags.RUN_FIRST, None, (str, int, object)),
        'image': (GObject.SignalFlags.RUN_FIRST, None, (str, int, object, object, object)),
        'idle': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, *args, **kwargs):
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
        self._working=0

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

    def _backgroundworker(self):
        while True:
            prefix, fsn, filename, args = self._queue_to_backend.get()
            logger.debug(
                'Exposureanalyzer background process got work: %s, %d, %s, %s' % (prefix, fsn, filename, str(args)))
            cbfdata = readcbf(
                os.path.join(self._config['path']['directories']['images'], filename))[0]
            if prefix == 'exit':
                break
            elif prefix == self._config['path']['prefixes']['crd']:
                # data reduction needed
                mask=self.get_mask(self._config['geometry']['mask'])
                I, dI, param,mask=self.datareduction(cbfdata, mask, args[0])
                self._queue_to_frontend.put_nowait(
                    ((prefix, fsn), 'datareduction-done')
                )
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
            self._working-=1
        except queue.Empty:
            return True
        if what == 'error':
            self.emit(
                'error', prefix_fsn[0], prefix_fsn[1], arguments[0], arguments[1])
        elif what == 'scanpoint':
            logger.debug('Emitting scanpoint with arguments: %s'%str(arguments))
            self.emit('scanpoint', prefix_fsn[0], prefix_fsn[1], arguments)
        elif what == 'datareduction':
            self.emit('datareduction-done', prefix_fsn[0], prefix_fsn[1])
        elif what == 'transmdata':
            self.emit('transmdata', prefix_fsn[0], prefix_fsn[1], arguments)
        elif what == 'image':
            self.emit('image', prefix_fsn[0], prefix_fsn[1], arguments[0], arguments[1], arguments[2])
        if self._working==0:
            self.emit('idle')
        return True

    def submit(self, fsn, filename, prefix, args):
        logger.debug('Submitting to exposureanalyzer: %s, %d, %s, %s'%(prefix,fsn,filename,str(args)))
        self._queue_to_backend.put_nowait((prefix, fsn, filename, args))
        self._working+=1

    def prescaling(self, intensity, error, mask, params):
        intensity/=params['devices']['pilatus']['exptime']
        error/=params['devices']['pilatus']['exptime']
        return intensity, error, mask, params

    def subtractbackground(self, intensity, error, mask, params):
        return intensity, error, mask, params

    def correctgeometry(self, intensity, error, mask, params):
        return intensity, error, mask, params

    def absolutescaling(self, intensity, error, mask, params):
        return intensity, error, mask, params

    def datareduction(self, intensity, mask, params):
        error=intensity**0.5
        intensity, error, mask, params=self.prescaling(intensity,error,mask,params)
        intensity, error, mask, params=self.subtractbackground(intensity, error, mask, params)
        intensity, error, mask, params=self.correctgeometry(intensity, error, mask, params)
        intensity, error, mask, params=self.absolutescaling(intensity, error, mask, params)

