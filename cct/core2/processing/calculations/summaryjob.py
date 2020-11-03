"""A class representing a processing job: for one sample and one sample-to-detector distance"""
import multiprocessing
import time
import traceback
from datetime import datetime
from multiprocessing.synchronize import Lock
from typing import List, Optional, Any

import h5py
import numpy as np
from ...dataclasses import Header, Exposure, Curve

from .outliertest import OutlierMethod, OutlierTest
from ..h5io import ProcessingH5File
from ..loader import Loader
from .backgroundprocess import BackgroundProcess, Results, BackgroundProcessError, UserStopException
from ...algorithms.matrixaverager import MatrixAverager, ErrorPropagationMethod


class SummaryError(BackgroundProcessError):
    pass


class SummaryJobResults(Results):
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
    jobid: Any


class SummaryJob(BackgroundProcess):
    """A separate process for processing (summarizing, azimuthally averaging, finding outliers) of a range
    of exposures belonging to the same sample, measured at the same sample-to-detector distance.
    """
    loader: Loader
    h5io: ProcessingH5File
    badfsns: List[int] = None
    outliermethod: OutlierMethod
    outlierthreshold: float
    cormatLogarithmic: bool
    ierrorprop: ErrorPropagationMethod
    qerrorprop: ErrorPropagationMethod
    fsns: List[int]
    prefix: str
    curves: np.ndarray
    intensities2D: np.ndarray
    uncertainties2D: np.ndarray
    masks2D: np.ndarray
    outliertest: OutlierTest
    averagedHeader: Header
    averagedExposure: Exposure
    averagedCurve: Curve
    reintegratedCurve: Curve

    def __init__(self, jobid: Any, h5file: str, h5lock: Lock,
                 stopEvent: multiprocessing.synchronize.Event, messagequeue: multiprocessing.queues.Queue,
                 rootpath: str, eval2dsubpath: str, masksubpath: str, fsndigits: int,
                 prefix: str, fsnlist: List[int],
                 ierrorprop: ErrorPropagationMethod, qerrorprop: ErrorPropagationMethod,
                 outliermethod: OutlierMethod, outlierthreshold: float, cormatLogarithmic: bool,
                 qrange: Optional[np.ndarray], bigmemorymode: bool = False):
        super().__init__(jobid, h5file, h5lock, stopEvent, messagequeue)
        self.loader = Loader(rootpath, eval2dsubpath, masksubpath, fsndigits)
        self.badfsns = []
        self.ierrorprop = ierrorprop
        self.qerrorprop = qerrorprop
        self.fsns = list(fsnlist)
        self.prefix = prefix
        self.outliermethod = outliermethod
        self.outlierthreshold = outlierthreshold
        self.cormatLogarithmic = cormatLogarithmic
        self.qrange = qrange
        self.bigmemorymode = bigmemorymode
        self.result = SummaryJobResults()
        self.result.jobid = self.jobid

    def _loadheaders(self):
        # first load all header files
        t0 = time.monotonic()
        self.headers = []
        self.sendProgress('Loading headers {}/{}'.format(0, len(self.fsns)),
                          total=len(self.fsns), current=0)
        for i, fsn in enumerate(self.fsns, start=1):
            try:
                h = self.loader.loadHeader(self.prefix, fsn)
                if h.fsn != fsn:
                    raise ValueError('FSN in header ({}) is different than in the filename ({}).'.format(h.fsn, fsn))
                self.headers.append(h)
                self.sendProgress('Loading headers {}/{}'.format(i, len(self.fsns)),
                                  total=len(self.fsns), current=i)
            except FileNotFoundError:
                continue
        # check if all headers correspond to the same sample and distance
        if len({(h.title, float(h.distance)) for h in self.headers}) > 1:
            raise SummaryError('There are more samples/distances!')
        self.result.time_loadheaders = time.monotonic() - t0

    def _loadexposures(self):
        """Load all exposures, i.e. 2D images. Do radial averaging as well."""
        if not self.headers:
            return
        t0 = time.monotonic()
        # now load all exposures
        self.exposures = []
        self.intensities2D = None
        self.uncertainties2D = None
        self.masks2D = None
        self.curvesforcmap = []
        self.fsnsforcmap = []
        self.curves = None
        self.sendProgress('Loading exposures {}/{}'.format(0, len(self.headers)),
                          total=len(self.headers), current=0)
        qrange = self.qrange
        for i, h in enumerate(self.headers, start=1):
            try:
                ex = self.loader.loadExposure(self.prefix, h.fsn)
                radavg = ex.radial_average(
                    qbincenters=qrange,
                    errorprop=self.ierrorprop,
                    qerrorprop=self.qerrorprop,
                )
                if qrange is None:
                    qrange = radavg.q
                curvearray = radavg.asArray()
                if self.curves is None:
                    self.curves = np.empty(curvearray.shape + (len(self.headers),), curvearray.dtype) + np.nan
                self.curves[:, :, i] = curvearray
                if self.bigmemorymode:
                    if self.intensities2D is None:
                        self.intensities2D = np.empty(ex.intensity.shape + (len(self.headers),),
                                                      ex.intensity.dtype) + np.nan
                        self.uncertainties2D = np.empty(ex.intensity.shape + (len(self.headers),),
                                                        ex.intensity.dtype) + np.nan
                        self.masks2D = np.zeros(ex.mask.shape + (len(self.headers),), ex.mask.dtype)
                    self.intensities2D[:, :, i] = ex.intensity
                    self.uncertainties2D[:, :, i] = ex.uncertainty
                    self.masks2D[:, :, i] = ex.mask
                    ex.intensity = self.intensities2D[:, :, i]  # this is only a view, does not take up more space
                    ex.uncertainty = self.uncertainties2D[:, :, i]
                    ex.mask = self.masks2D[:, :, i]
                    self.exposures.append(ex)
                self.sendProgress('Loading exposures {}/{}'.format(i, len(self.headers)),
                                  total=len(self.headers), current=i)
            except FileNotFoundError as fnfe:
                raise SummaryError('Cannot find file: {}'.format(fnfe.args[0]))
        self.result.time_loadexposures = time.monotonic() - t0

    def _checkforoutliers(self):
        t0 = time.monotonic()
        self.sendProgress('Testing for outliers...', total=0, current=0)
        self.outliertest = OutlierTest(self.curves, self.outliermethod, self.outlierthreshold)
        self.badfsns = np.array(self.fsns)[self.outliertest.outlierverdict]
        self.result.time_outlierdetection = time.monotonic() - t0

    def _summarize(self):
        """Calculate average scattering pattern and curve"""

        headers = [h for h in self.headers if h.fsn not in self.badfsns]
        if not headers:
            return  #ToDo

        t0 = time.monotonic()
        # first average the headers, however fool this sounds...
        self.sendProgress('Collecting header data for averaged image...')
        t1 = time.monotonic()
        self.averagedHeader = Header.average(*headers)
        self.result.time_averaging_header = time.monotonic() - t1

        # summarize 2D and 1D datasets
        t1 = time.monotonic()
        self.sendProgress('Averaging exposures...', current=0, total=0)

        def exposureiterator(hs:List[Header], ldr: Loader, prefix: str):
            for i, h in enumerate(hs):
                self.sendProgress('Averaging exposures {}/{}...'.format(i, len(hs)),
                                  current=i, total=len(hs))
                yield ldr.loadExposure(prefix, h.fsn, h)
        self.averagedExposure = Exposure.average(
            self.exposures if self.bigmemorymode else exposureiterator, errorpropagation=self.ierrorprop)
        self.result.time_averaging_exposures = time.monotonic() - t1

        # Average curves
        t1 = time.monotonic()
        self.sendProgress('Averaging curves...', total=0, current=0)
        self.averagedCurve = Curve.average(self.curves, ierrorpropagation=self.ierrorprop, qerrorpropagation=self.qerrorprop)
        self.reintegratedCurve = self.averagedExposure.radial_average(
            self.qrange, errorprop=self.ierrorprop,
            qerrorprop=self.qerrorprop)
        self.result.time_averaging_curves = time.monotonic() - t1
        self.result.time_averaging = time.monotonic() - t0

    def _output(self):
        """Write results in the .h5 file."""
        t0 = time.monotonic()
        self.sendProgress('Waiting for HDF5 writer lock...')
        with self.h5io.writer(f'Samples/{self.headers[0].title}/{self.headers[0].distance:.2f}') as group:
            t1 = time.monotonic()
            self.sendProgress('Writing HDF5 file...')
            # Set attributes of the <dist> group from the averaged header.
            self.h5io.writeHeader(self.averagedHeader, group)
            self.h5io.writeExposure(self.averagedExposure, group)
            group['badfsns'] = np.array(self.badfsns)
            self.h5io.writeCurve(self.averagedCurve, group, 'curve_averaged')
            self.h5io.writeCurve(self.reintegratedCurve, group, 'curve_reintegrated')
            group['curve'] = h5py.SoftLink('curve_averaged')
            group.create_dataset('correlmatrix', data=self.outliertest.correlmatrix, compression='lzf', shuffle=True, fletcher32=True)
            # save all curves
            try:
                del group['curves']
            except KeyError:
                pass
            curvesgroup = group.create_group('curves')
            # we will write outlier results per-curve. Do the common calculations beforehand.

            for i, (h, c, s) in enumerate(zip(self.headers, self.curves, self.outliertest.score)):
                self.h5io.writeCurve(c, curvesgroup, str(h.fsn))
                dataset = curvesgroup[str(h.fsn)]
                self.h5io.writeHeader(h, dataset)
                dataset.attrs['correlmat_bad'] = int(h.fsn in self.badfsns)
                dataset.attrs['correlmat_discrp'] = s
        self.result.time_output_write = time.monotonic() - t1
        self.result.time_output_waitforlock = t1 - t0
        self.result.time_output = time.monotonic() - t0

    def main(self):
        try:
            t0 = time.monotonic()
            self._loadheaders()
            self._loadexposures()
            self._checkforoutliers()
            self._summarize()
            self._output()
            self.result.badfsns = self.badfsns
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
        return self.result
