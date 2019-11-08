"""A class representing a processing job: for one sample and one sample-to-detector distance"""
import multiprocessing
from datetime import datetime
from typing import List, Optional

import h5py
import numpy as np
from sastool import ErrorValue
from sastool.classes2 import Curve
from sastool.io.credo_cct import Header, Exposure

from . import outliers
from .correlmatrix import correlmatrix_cython
from .loader import Loader


class ProcessingError(Exception):
    """Exception raised during the processing. Accepts a single string argument."""
    pass


class Message:
    def __init__(self, type_: str, message: str, totalcount: int = None, currentcount: int = None):
        self.type_ = type_
        self.message = message
        self.totalcount = totalcount
        self.currentcount = currentcount


class ProcessingJob:
    """A separate process for processing (summarizing, azimuthally averaging, finding outliers) of a range
    of exposures belonging to the same sample, measured at the same sample-to-detector distance.
    """
    _errorpropagationtypes = ['Weighted', 'Average', 'Squared (Gaussian)', 'Conservative']
    headers: List[Header] = None
    curves: List[Curve] = None
    curvesforcmap: List[Curve] = None
    exposures: List[Exposure] = None
    _loader: Loader = None
    bigmemorymode: bool = False
    badfsns: List[int] = None
    h5compression: Optional[str] = 'gzip'

    def __init__(self, resultsqueue: multiprocessing.Queue, rootdir: str, fsnlist: List[int],
                 h5file: str,
                 ierrorprop: str, qerrorprop: str, outliermethod: str, outliermultiplier: float, logcmat: bool,
                 qrange: Optional[np.ndarray], bigmemorymode: bool = False):
        super().__init__()
        self.fsnlist = fsnlist
        self._loader = Loader(rootdir)
        self.subprocess = None
        self.starttime = None
        self.h5file = h5file
        self.resultsqueue = resultsqueue
        if ierrorprop in self._errorpropagationtypes:
            self.ierrorprop = ierrorprop
        else:
            raise ValueError('Invalid value for ierrorprop')
        if qerrorprop in self._errorpropagationtypes:
            self.qerrorprop = qerrorprop
        else:
            raise ValueError('Invalid value for qerrorprop')
        if outliermethod in ['Z-score', 'Modified Z-score', 'Interquartile Range']:
            self.outliermethod = outliermethod
        else:
            raise ValueError('Invalid value for outlier method')
        self.outliermultiplier = outliermultiplier
        self.logcmat = logcmat
        self.qrange = qrange
        self.bigmemorymode = bigmemorymode

    def sendProgress(self, message: str, total: Optional[int] = None,
                     current: Optional[int] = None):
        self.resultsqueue.put(
            Message(type_='message', message=message, totalcount=total, currentcount=current))

    def sendError(self, message: str):
        self.resultsqueue.put(Message(type_='error', message=message))

    def _loadheaders(self):
        # first load all header files
        self.headers = []
        self.sendProgress('Loading headers {}/{}'.format(0, len(self.fsnlist)),
                          total=len(self.fsnlist), current=0)
        for i, fsn in enumerate(self.fsnlist, start=1):
            try:
                self.headers.append(self._loader.loadHeader(fsn))
                self.sendProgress('Loading headers {}/{}'.format(i, len(self.fsnlist)),
                                  total=len(self.fsnlist), current=i)
            except FileNotFoundError:
                continue
        # check if all headers correspond to the same sample and distance
        if len({(h.title, h.distance) for h in self.headers}) > 1:
            self.sendError('There are more samples/distances!')
            return

    def _loadexposures(self):
        """Load all exposures, i.e. 2D images. Do radial averaging as well."""
        if not self.headers:
            return
        # now load all exposures
        self.exposures = []
        self.curvesforcmap = []
        self.curves = []
        self.sendProgress('Loading exposures {}/{}'.format(0, len(self.headers)),
                          total=len(self.headers), current=0)
        qrange = self.qrange
        for i, h in enumerate(self.headers, start=1):
            try:
                ex = self._loader.loadExposure(h.fsn)
                radavg = ex.radial_average(
                    qrange=qrange,
                    errorpropagation=self._errorpropagationtypes.index(self.ierrorprop),
                    abscissa_errorpropagation=self._errorpropagationtypes.index(self.qerrorprop),
                )
                if qrange is None:
                    qrange = radavg.q
                self.curvesforcmap.append(radavg)
                self.curves.append(radavg)
                if self.bigmemorymode:
                    self.exposures.append(ex)
                self.sendProgress('Loading exposures {}/{}'.format(i, len(self.headers)),
                                  total=len(self.headers), current=i)
            except FileNotFoundError as fnfe:
                self.sendError('Cannot find file: {}'.format(fnfe.args[0]))
                return

    def _checkforoutliers(self):
        self.sendProgress('Testing for outliers...', total=0, current=0)
        intensities = np.vstack([c.Intensity for c in self.curvesforcmap]).T
        errors = np.vstack([c.Error for c in self.curvesforcmap]).T
        cmat = correlmatrix_cython(intensities, errors, self.logcmat)
        discrp = np.diagonal(cmat)
        # find outliers
        if self.outliermethod in ['Interquartile Range', 'Tukey_IQR', 'Tukey', 'IQR']:
            bad = outliers.outliers_Tukey_iqr(discrp, self.outliermultiplier)
        elif self.outliermethod in ['Z-score']:
            bad = outliers.outliers_zscore(discrp, self.outliermultiplier)
        elif self.outliermethod in ['Modified Z-score', 'Iglewicz-Hoaglin']:
            bad = outliers.outliers_zscore_mod(discrp, self.outliermultiplier)
        else:
            assert False
        self.badfsns = [h.fsn for i, h in enumerate(self.headers) if i in bad]
        self.correlmatrix = cmat

    def _summarize(self):
        """Calculate average scattering pattern and curve"""

        # summarize 2D and 1D datasets
        # Error propagation types: if y_i are the measured data and e_i are their uncertainties:
        #
        #  1) Weighted:
        #       y = sum_i (1/e_i^2 y_i) / sum_i (1/e_i^2)
        #       e = 1/sqrt(sum_i(1/e_i^2))
        #  2) Average of errors (linear):
        #       y = mean(y_i)    ( simple mean)
        #       e = mean(e_i)
        #  3) Gaussian (squared):
        #       y = mean(y_i)
        #       e = sqrt(sum(e_i^2)/N)
        #  4) Conservative:
        #       y = mean(y_i)
        #       e: either the Gaussian, or that from the standard deviation, take the larger one.

        self.sendProgress('Averaging exposures...', current=0, total=0)
        intensity2D = 0
        intensity2D_squared = 0
        error2D = 0
        mask = None
        # do the 2D averaging first.
        count = 0
        headeravg = None
        for i, header in enumerate(self.headers):
            self.sendProgress('Averaging exposures {}/{}...'.format(i, len(self.headers)),
                              current=i, total=len(self.headers))
            if header.fsn in self.badfsns:
                continue
            if headeravg is None:
                headeravg = header
            if self.exposures:
                ex = self.exposures[i]
            else:
                ex = self._loader.loadExposure(header.fsn)
            if mask is None:
                mask = ex.mask.copy()
            else:
                mask = np.logical_and(ex.mask != 0, mask != 0)
            error = ex.error
            error[error <= 0] = np.nanmin(error[error > 0])  # remove negative and zero values: they can cause troubles
            if self.ierrorprop == 'Weighted':
                # Weighted error propagation, scattering patterns are considered independent samples of the same
                # random variable
                error2D = error2D + 1 / error ** 2
                intensity2D = intensity2D + ex.intensity / error ** 2
            elif self.ierrorprop == 'Average':
                error2D = error2D + error
                intensity2D = intensity2D + ex.intensity
            elif self.ierrorprop == 'Squared (Gaussian)':
                error2D = error2D + error ** 2
                intensity2D = intensity2D + ex.intensity
            elif self.ierrorprop == 'Conservative':
                error2D = error2D + error ** 2
                intensity2D = intensity2D + ex.intensity
                intensity2D_squared = intensity2D_squared + ex.intensity ** 2
            else:
                assert False
            count += 1
        if self.ierrorprop == 'Weighted':
            intensity2D /= error2D
            error2D = (1 / error2D) ** 0.5
        elif self.ierrorprop == 'Average':
            intensity2D /= count
            error2D /= count ** 2
        elif self.ierrorprop == 'Squared (Gaussian)':
            intensity2D /= count
            error2D = error2D ** 0.5 / count
        elif self.ierrorprop == 'Conservative':
            error2D_countingstats = (intensity2D_squared - intensity2D ** 2 / count) / (
                    count - 1) / count ** 0.5 if count > 1 else np.zeros_like(intensity2D)
            error2D_propagated = error2D ** 0.5 / count
            error2D = np.stack((error2D_countingstats, error2D_propagated)).max(axis=0)
            intensity2D /= count
        else:
            assert False
        self.averaged2D = Exposure(intensity2D, error2D, headeravg, mask)
        self.sendProgress('Averaging curves...', total=0, current=0)
        intensity1D = 0
        error1D = 0
        q1D = 0
        qerror1D = 0
        for h,c,i in zip(self.headers, self.curves, range(len(self.headers))):
            self.sendProgress('Averaging curves {}/{}...', total=len(self.headers), current=i)
            if h.fsn in self.badfsns:
                continue
            if self.ierrorprop == 'Weighted':
                pass
            elif self.ierrorprop == 'Average':
                pass
            elif self.ierrorprop == 'Squared (Gaussian)':
                pass
            elif self.ierrorprop == 'Conservative':
                pass
            else:
                assert False
            if self.qerrorprop == 'Weighted':
                pass
            elif self.qerrorprop == 'Average':
                pass
            elif self.qerrorprop == 'Squared (Gaussian)':
                pass
            elif self.qerrorprop == 'Conservative':
                pass
            else:
                assert False

        if self.ierrorprop == 'Weighted':
            pass
        elif self.ierrorprop == 'Average':
            pass
        elif self.ierrorprop == 'Squared (Gaussian)':
            pass
        elif self.ierrorprop == 'Conservative':
            pass
        else:
            assert False
        if self.qerrorprop == 'Weighted':
            pass
        elif self.qerrorprop == 'Average':
            pass
        elif self.qerrorprop == 'Squared (Gaussian)':
            pass
        elif self.qerrorprop == 'Conservative':
            pass
        else:
            assert False
        

        self.averaged1D = Curve(q1D, intensity1D, error1D, qerror1D)
        self.reintegrated1D = self.averaged2D.radial_average(
            self.qrange, errorpropagation=self._errorpropagationtypes.index(self.ierrorprop),
            abscissa_errorpropagation=self._errorpropagationtypes.index(self.qerrorprop)
        )
        # now average the headers, however fool this sounds...
        self.averagedHeader = {}
        for field in ['title', 'distance', 'distancedecrease', 'pixelsizex', 'pixelsizey', 'wavelength']:
            # ensure that these fields are unique
            avg = {getattr(h, field) for h in self.headers if h.fsn not in self.badfsns}
            if len(avg) != 1:
                raise ValueError(
                    'Field {} must be unique. Found the following different values: {}'.format(', '.join(avg)))
            self.averagedHeader[field] = avg.pop()
        for field in ['date', 'startdate']:
            self.averagedHeader[field] = min([getattr(h, field) for h in self.headers if h.fsn not in self.badfsns])
        for field in ['enddate']:
            # take the maximum of these fields
            self.averagedHeader[field] = max([getattr(h, field) for h in self.headers if h.fsn not in self.badfsns])
        for field in ['exposuretime', ]:
            # take the sum of these fields
            self.averagedHeader[field] = sum([getattr(h, field) for h in self.headers if h.fsn not in self.badfsns])
        for field in ['absintfactor', 'beamcenterx', 'beamcentery', 'flux', 'samplex', 'sampley', 'temperature',
                      'thickness', 'transmission', 'vacuum']:
            # take the weighted average of these fields
            values = [getattr(h, field) for h in self.headers if h.fsn not in self.badfsns]
            values = [v for v in values if isinstance(v, float) or isinstance(v, ErrorValue)]
            val = np.array([v.val if isinstance(v, ErrorValue) else v for v in values])
            err = np.array([v.err if isinstance(v, ErrorValue) else np.nan for v in values])
            if np.isfinite(err).sum() == 0:
                err = np.ones_like(val)
            else:
                minposerr = np.nanmin(err[err > 0])
                err[err <= 0] = minposerr
                err[~np.isfinite(err)] = minposerr
            self.averagedHeader[field] = ErrorValue(
                (val / err ** 2).sum() / (1 / err ** 2).sum(),
                1 / (1 / err ** 2).sum() ** 0.5
            )
        for field in ['fsn', 'fsn_absintref', 'fsn_emptybeam', 'maskname', 'project', 'username']:
            # take the first value
            self.averagedHeader[field] = [getattr(h, field) for h in self.headers if h.fsn not in self.badfsns][0]

    def _output(self):
        """Write results in the .h5 file."""
        with h5py.File(self.h5file, mode='a') as h5:  # mode=='a': read/write if exists, create otherwise
            # save all masks
            masks = h5.require_group('masks')
            for name, mask in self._loader.masks.items():
                ds = masks.require_dataset(name, mask.shape, mask.dtype, exact=True)
                ds.value = mask
            # create Samples/<samplename>/<dist> group hierarchy if not exists
            samples = h5.require_group('Samples')
            samplegroup = h5['Samples'].require_group(self.headers[0].title)
            try:
                del samplegroup['{:.2f}'.format(self.headers[0].distance)]
            except KeyError:
                pass
            distgroup = samplegroup.require_group('{:.2f}'.format(self.headers[0].distance))
            # Set attributes of the <dist> group from the averaged header.
            for key, value in self.averagedHeader:
                if isinstance(value, ErrorValue):
                    distgroup.attrs[key] = value.val
                    distgroup.attrs[key + '.err'] = value.err
                elif isinstance(value, datetime):
                    distgroup.attrs[key] = str(value)
                else:
                    distgroup.attrs[key] = value
            # save datasets
            distgroup.create_dataset('image', data=self.averaged2D.intensity, compression=self.h5compression)
            distgroup.create_dataset('image_uncertainty', data=self.averaged2D.error, compression=self.h5compression)
            distgroup.create_dataset('correlmatrix', data=self.correlmatrix, compression=self.h5compression)
            distgroup.create_dataset('mask', data=self.averaged2D.mask, compression=self.h5compression)
            distgroup['badfsns'] = np.array(self.badfsns)
            distgroup.create_dataset('curve_averaged', data=np.vstack(
                (self.averaged1D.q, self.averaged1D.Intensity, self.averaged1D.Error, self.averaged1D.qError)).T,
                                     compression=self.h5compression)
            
            distgroup.create_dataset('curve_reintegrated',
                                     data=np.vstack((self.reintegrated1D.q, self.reintegrated1D.Intensity, 
                                                     self.reintegrated1D.Error, self.reintegrated1D.qError)).T,
                                     compression=self.h5compression)
            distgroup['curve'] = h5py.SoftLink('curve_averaged')
            # save all curves
            try:
                del distgroup['curves']
            except KeyError:
                pass
            curvesgroup = distgroup.require_group('curves')
            for h, c in zip(self.headers, self.curves):
                ds = curvesgroup.create_dataset(str(h.fsn), data=np.vstack((c.q, c.Intensity, c.Error, c.qError)).T,
                                           compression=self.h5compression)
                for field in ['absintfactor', 'beamcenterx', 'beamcentery', 'date', 'distance', 'distancedecrease',
                              'enddate', 'exposuretime', 'flux', 'fsn', 'fsn_absintref', 'fsn_emptybeam', 'maskname',
                              'pixelsizex', 'pixelsizey', 'project', 'samplex', 'samplex_motor',
                              'sampley', 'sampley_motor', 'startdate', 'temperature', 'thickness', 'title', 'transmission',
                              'username', 'vacuum', 'wavelength']:
                    value = getattr(h, field)
                    if isinstance(value, datetime):
                        ds.attrs[field] = str(value)
                    elif isinstance(value, ErrorValue):
                        ds.attrs[field] = value.val
                        ds.attrs[field+'.err'] = value.val
                    elif value is None:
                        ds.attrs[field] = 'None'
                    else:
                        ds.attrs[field] = value
                #ToDo: write correlmat_* fields

    def run(self) -> None:
        self._loadheaders()
        self._loadexposures()
        self._checkforoutliers()
        self._summarize()
        self._output()
