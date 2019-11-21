"""A class representing a processing job: for one sample and one sample-to-detector distance"""
import multiprocessing
import time
import traceback
from datetime import datetime
from typing import List, Optional, Any

import h5py
import numpy as np
from sastool import ErrorValue
from sastool.classes2 import Curve
from sastool.io.credo_cct import Header, Exposure

from . import outliers
from .correlmatrix import correlmatrix_cython
from .loader import Loader
from .matrixaverager import MatrixAverager


class ProcessingError(Exception):
    """Exception raised during the processing. Accepts a single string argument."""
    pass


class UserStopException(ProcessingError):
    pass


class ProcessingJobResults:
    time_total: float = 0
    time_loadheaders: float = 0
    time_loadexposures: float = 0
    time_outlierdetection: float = 0
    time_averaging: float = 0
    time_averaging_header: float = 0
    time_averaging_exposures: float = 0
    time_averaging_curves: float = 0
    time_output: float = 0
    time_output_waitforlock: float = 0
    time_output_write: float = 0
    badfsns: List[int] = None
    success: bool = False
    status: str = ''


class Message:
    type_: str
    message: str
    sender: Any = None
    totalcount: Optional[int] = None
    currentcount: Optional[int] = None
    traceback: Optional[str] = None

    def __init__(self, sender: Any, type_: str, message: str, totalcount: int = None, currentcount: int = None,
                 traceback: Optional[str] = None):
        self.type_ = type_
        self.sender = sender
        self.message = message
        self.totalcount = totalcount
        self.currentcount = currentcount
        self.traceback = traceback

    def __str__(self) -> str:
        return 'Message(sender={}, type={}, totalcount={}, currentcount={}, message={}'.format(self.sender, self.type_,
                                                                                               self.totalcount,
                                                                                               self.currentcount,
                                                                                               self.message)


class ProcessingJob:
    """A separate process for processing (summarizing, azimuthally averaging, finding outliers) of a range
    of exposures belonging to the same sample, measured at the same sample-to-detector distance.
    """
    _errorpropagationtypes = ['Weighted', 'Average', 'Squared (Gaussian)', 'Conservative']
    headers: List[Header] = None
    curves: List[Curve] = None
    curvesforcmap: List[Curve] = None
    fsnsforcmap: List[int] = None
    exposures: List[Exposure] = None
    _loader: Loader = None
    bigmemorymode: bool = False
    badfsns: List[int] = None
    initialBadfsns: List[int] = None
    h5compression: Optional[str] = 'gzip'
    killSwitch: multiprocessing.Event = None
    h5WriterLock: multiprocessing.Lock = None
    jobid: Any = None
    result: ProcessingJobResults = None

    def __init__(self, jobid: Any, h5writerLock: multiprocessing.Lock, killswitch: multiprocessing.Event,
                 resultsqueue: multiprocessing.Queue, rootdir: str,
                 fsnlist: List[int], badfsns: List[int], h5file: str,
                 ierrorprop: str, qerrorprop: str, outliermethod: str, outliermultiplier: float, logcmat: bool,
                 qrange: Optional[np.ndarray], bigmemorymode: bool = False):
        self.jobid = jobid
        self.fsnlist = fsnlist
        self._loader = Loader(rootdir)
        self.h5file = h5file
        self.resultsqueue = resultsqueue
        self.killSwitch = killswitch
        self.initialBadfsns = badfsns
        self.badfsns = list(self.initialBadfsns)  # make a copy: we will modify this.
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
        self.h5WriterLock = h5writerLock
        self.result = ProcessingJobResults()

    def sendProgress(self, message: str, total: Optional[int] = None,
                     current: Optional[int] = None):
        self.resultsqueue.put(
            Message(sender=self.jobid, type_='progress', message=message, totalcount=total, currentcount=current))
        if self.killSwitch.is_set():
            raise UserStopException('Stopping on user request.')

    def sendError(self, message: str, traceback: Optional[str] = None):
        self.resultsqueue.put(Message(sender=self.jobid, type_='error', message=message, traceback=traceback))

    def _loadheaders(self):
        # first load all header files
        t0 = time.monotonic()
        self.headers = []
        self.sendProgress('Loading headers {}/{}'.format(0, len(self.fsnlist)),
                          total=len(self.fsnlist), current=0)
        for i, fsn in enumerate(self.fsnlist, start=1):
            try:
                h = self._loader.loadHeader(fsn)
                if h.fsn != fsn:
                    raise ValueError('FSN in header ({}) is different than in the filename ({}).'.format(h.fsn, fsn))
                self.headers.append(h)
                self.sendProgress('Loading headers {}/{}'.format(i, len(self.fsnlist)),
                                  total=len(self.fsnlist), current=i)
            except FileNotFoundError:
                continue
        # check if all headers correspond to the same sample and distance
        if len({(h.title, float(h.distance)) for h in self.headers}) > 1:
            raise ProcessingError('There are more samples/distances!')
        self.result.time_loadheaders = time.monotonic() - t0

    def _loadexposures(self):
        """Load all exposures, i.e. 2D images. Do radial averaging as well."""
        if not self.headers:
            return
        t0 = time.monotonic()
        # now load all exposures
        self.exposures = []
        self.curvesforcmap = []
        self.fsnsforcmap = []
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
                if h.fsn not in self.badfsns:
                    # do not use this curve for correlation matrix analysis
                    self.curvesforcmap.append(radavg)
                    self.fsnsforcmap.append(h.fsn)

                self.curves.append(radavg)
                if self.bigmemorymode:
                    self.exposures.append(ex)
                self.sendProgress('Loading exposures {}/{}'.format(i, len(self.headers)),
                                  total=len(self.headers), current=i)
            except FileNotFoundError as fnfe:
                raise ProcessingError('Cannot find file: {}'.format(fnfe.args[0]))
        self.result.time_loadexposures = time.monotonic() - t0

    def _checkforoutliers(self):
        t0 = time.monotonic()
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
        self.badfsns.extend([self.fsnsforcmap[i] for i in bad])
        self.correlmatrix = cmat
        self.result.time_outlierdetection = time.monotonic() - t0

    def _summarize(self):
        """Calculate average scattering pattern and curve"""

        # first average the headers, however fool this sounds...
        t0 = time.monotonic()
        self.sendProgress('Collecting header data for averaged image...')
        t1 = time.monotonic()
        self.averagedHeader = {}
        for field in ['title', 'distance', 'distancedecrease', 'pixelsizex', 'pixelsizey', 'wavelength',
                      'sample_category']:
            # ensure that these fields are unique
            avg = {getattr(h, field) if not isinstance(getattr(h, field), ErrorValue) else getattr(h, field).val for h
                   in self.headers if h.fsn not in self.badfsns}
            if len(avg) != 1:
                raise ValueError(
                    'Field {} must be unique. Found the following different values: {}'.format(field, ', '.join(avg)))
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
            try:
                values = [getattr(h, field) for h in self.headers if h.fsn not in self.badfsns]
            except KeyError:
                # can happen for absintfactor.
                continue
            values = [v for v in values if isinstance(v, float) or isinstance(v, ErrorValue)]
            val = np.array([v.val if isinstance(v, ErrorValue) else v for v in values])
            err = np.array([v.err if isinstance(v, ErrorValue) else np.nan for v in values])
            if np.isfinite(err).sum() == 0:
                err = np.ones_like(val)
            elif (err > 0).sum() == 0:
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
            try:
                self.averagedHeader[field] = [getattr(h, field) for h in self.headers if h.fsn not in self.badfsns][0]
            except KeyError:
                # can happen e.g. for fsn_emptybeam and fsn_absintref
                continue

        # make a true Header instance
        avgheader = Header()
        for field in self.averagedHeader:
            setattr(avgheader, field, self.averagedHeader[field])
        self.result.time_averaging_header = time.monotonic() - t1

        # summarize 2D and 1D datasets
        t1 = time.monotonic()
        self.sendProgress('Averaging exposures...', current=0, total=0)
        maskavg = None
        avg = MatrixAverager(self.ierrorprop)
        for i, header in enumerate(self.headers):
            self.sendProgress('Averaging exposures {}/{}...'.format(i, len(self.headers)),
                              current=i, total=len(self.headers))
            if header.fsn in self.badfsns:
                continue
            if self.exposures:
                ex = self.exposures[i]
            else:
                ex = self._loader.loadExposure(header.fsn)
            if maskavg is None:
                maskavg = ex.mask.copy()
            else:
                maskavg = np.logical_and(ex.mask != 0, maskavg != 0)
            avg.add(ex.intensity, ex.error)
        avgintensity, avgerr = avg.get()
        self.averaged2D = Exposure(avgintensity, avgerr, avgheader, maskavg)
        self.result.time_averaging_exposures = time.monotonic() - t1

        t1 = time.monotonic()
        self.sendProgress('Averaging curves...', total=0, current=0)
        avgq = MatrixAverager(self.qerrorprop)
        avgi = MatrixAverager(self.ierrorprop)
        for h, c, i in zip(self.headers, self.curves, range(len(self.headers))):
            self.sendProgress('Averaging curves {}/{}...'.format(i, len(self.headers)), total=len(self.headers),
                              current=i)
            if h.fsn in self.badfsns:
                continue
            avgq.add(c.q, c.qError)
            avgi.add(c.Intensity, c.Error)
        qavg, qErravg = avgq.get()
        Iavg, Erravg = avgi.get()
        self.averaged1D = Curve(qavg, Iavg, Erravg, qErravg)
        self.reintegrated1D = self.averaged2D.radial_average(
            self.qrange, errorpropagation=self._errorpropagationtypes.index(self.ierrorprop),
            abscissa_errorpropagation=self._errorpropagationtypes.index(self.qerrorprop)
        )
        self.result.time_averaging_curves = time.monotonic() - t1
        self.result.time_averaging = time.monotonic() - t0

    def _output(self):
        """Write results in the .h5 file."""
        t0 = time.monotonic()
        self.sendProgress('Waiting for HDF5 writer lock...')
        with self.h5WriterLock:
            t1 = time.monotonic()
            self.sendProgress('Writing HDF5 file...')
            with h5py.File(self.h5file, mode='a') as h5:  # mode=='a': read/write if exists, create otherwise
                # save all masks
                masks = h5.require_group('masks')
                for name, mask in self._loader.masks.items():
                    ds = masks.require_dataset(name, mask.shape, mask.dtype, exact=True)
                    ds = mask
                # create Samples/<samplename>/<dist> group hierarchy if not exists
                samples = h5.require_group('Samples')
                samplegroup = h5['Samples'].require_group(self.headers[0].title)
                try:
                    del samplegroup['{:.2f}'.format(float(self.headers[0].distance))]
                except KeyError:
                    pass
                distgroup = samplegroup.create_group('{:.2f}'.format(float(self.headers[0].distance)))
                # Set attributes of the <dist> group from the averaged header.
                for key, value in self.averagedHeader.items():
                    if isinstance(value, ErrorValue):
                        distgroup.attrs[key] = value.val
                        distgroup.attrs[key + '.err'] = value.err
                    elif isinstance(value, datetime):
                        distgroup.attrs[key] = str(value)
                    else:
                        distgroup.attrs[key] = value
                # save datasets
                distgroup.create_dataset('image', data=self.averaged2D.intensity, compression=self.h5compression)
                distgroup.create_dataset('image_uncertainty', data=self.averaged2D.error,
                                         compression=self.h5compression)
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
                curvesgroup = distgroup.create_group('curves')
                # we will write outlier results per-curve. Do the common calculations beforehand.
                diag = np.diagonal(self.correlmatrix)
                zscore = outliers.zscore(diag)
                zscore_mod = outliers.zscore_mod(diag)
                bad_zscore = outliers.outliers_zscore(diag, self.outliermultiplier)
                bad_zscore_mod = outliers.outliers_zscore_mod(diag, self.outliermultiplier)
                bad_iqr = outliers.outliers_Tukey_iqr(diag, self.outliermultiplier)

                for h, c in zip(self.headers, self.curves):
                    self.checkDuplicateFSNs()
                    ds = curvesgroup.create_dataset(str(h.fsn), data=np.vstack((c.q, c.Intensity, c.Error, c.qError)).T,
                                                    compression=self.h5compression)
                    for field in ['absintfactor', 'beamcenterx', 'beamcentery', 'date', 'distance', 'distancedecrease',
                                  'enddate', 'exposuretime', 'flux', 'fsn', 'fsn_absintref', 'fsn_emptybeam',
                                  'maskname',
                                  'pixelsizex', 'pixelsizey', 'project', 'samplex', 'samplex_motor',
                                  'sampley', 'sampley_motor', 'startdate', 'temperature', 'thickness', 'title',
                                  'transmission',
                                  'username', 'vacuum', 'wavelength']:
                        try:
                            value = getattr(h, field)
                        except KeyError:
                            continue
                        if isinstance(value, datetime):
                            ds.attrs[field] = str(value)
                        elif isinstance(value, ErrorValue):
                            ds.attrs[field] = value.val
                            ds.attrs[field + '.err'] = value.err
                        elif value is None:
                            ds.attrs[field] = 'None'
                        else:
                            ds.attrs[field] = value
                    if h.fsn in self.initialBadfsns:
                        ds.attrs['correlmat_bad'] = 1
                        ds.attrs['correlmat_discrp'] = np.nan
                        ds.attrs['correlmat_zscore'] = np.nan
                        ds.attrs['correlmat_zscore_mod'] = np.nan
                        ds.attrs['correlmat_bad_zscore'] = 1
                        ds.attrs['correlmat_bad_zscore_mod'] = 1
                        ds.attrs['correlmat_bad_iqr'] = 1
                    else:
                        idx = self.fsnsforcmap.index(h.fsn)
                        ds.attrs['correlmat_bad'] = int(h.fsn in self.badfsns)
                        ds.attrs['correlmat_discrp'] = diag[idx]
                        ds.attrs['correlmat_zscore'] = zscore[idx]
                        ds.attrs['correlmat_zscore_mod'] = zscore_mod[idx]
                        ds.attrs['correlmat_bad_zscore'] = int(idx in bad_zscore)
                        ds.attrs['correlmat_bad_zscore_mod'] = int(idx in bad_zscore_mod)
                        ds.attrs['correlmat_bad_iqr'] = int(idx in bad_iqr)
        self.result.time_output_write = time.monotonic() - t1
        self.result.time_output_waitforlock = t1 - t0
        self.result.time_output = time.monotonic() - t0

    def checkDuplicateFSNs(self):
        # check if we have duplicate FSNs:
        fsns = sorted([h.fsn for h in self.headers])
        duplicate = [f for f in fsns if fsns.count(f) > 1]
        if duplicate:
            raise ValueError('Duplicate FSN(s) {}'.format(', '.join([str(f) for f in duplicate])))

    def run(self) -> None:
        try:
            t0 = time.monotonic()
            self._loadheaders()
            self._loadexposures()
            self._checkforoutliers()
            self._summarize()
            self._output()
            self.result.badfsns = [b for b in self.badfsns if b not in self.initialBadfsns]
            self.result.success = True
            self.result.time_total = time.monotonic() - t0
        except UserStopException:
            self.result.success = False
            self.result.status = 'User break'
            self.sendError('User stop requested')
        except Exception as exc:
            self.result.success = False
            self.result.status = 'Error'
            self.sendError(str(exc), traceback=traceback.format_exc())
