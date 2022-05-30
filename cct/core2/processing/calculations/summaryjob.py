"""A class representing a processing job: for one sample and one sample-to-detector distance"""
import multiprocessing
import time
import traceback
from multiprocessing.synchronize import Lock
from typing import List, Optional, Any, Set

import h5py
import numpy as np

from .backgroundprocess import BackgroundProcess, Results, BackgroundProcessError, UserStopException
from .outliertest import OutlierMethod, OutlierTest
from ...dataclasses.exposure import QRangeMethod
from ..h5io import ProcessingH5File
from ..loader import Loader, FileNameScheme
from ...algorithms.matrixaverager import ErrorPropagationMethod
from ...dataclasses import Header, Exposure, Curve


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
    badfsns: Set[int] = None
    newbadfsns: Set[int] = None
    jobid: Any

    def __init__(self, jobid: Any):
        super().__init__(jobid)
        self.badfsns = set()
        self.newbadfsns = set()


class SummaryJob(BackgroundProcess):
    """A separate process for processing (summarizing, azimuthally averaging, finding outliers) of a range
    of exposures belonging to the same sample, measured at the same sample-to-detector distance.
    """
    loader: Loader
    outliermethod: OutlierMethod
    outlierthreshold: float
    cormatLogarithmic: bool
    ierrorprop: ErrorPropagationMethod
    qerrorprop: ErrorPropagationMethod
    fsns: List[int]

    curves: np.ndarray
    intensities2D: np.ndarray
    uncertainties2D: np.ndarray
    masks2D: np.ndarray
    goodindex: np.ndarray
    outliertest: OutlierTest
    averagedHeader: Header
    averagedExposure: Exposure
    averagedCurve: Curve
    reintegratedCurve: Curve
    qcount: int
    qrangemethod: QRangeMethod

    result: SummaryJobResults

    def __init__(self, jobid: Any, h5file: str, h5lock: Lock,
                 stopEvent: multiprocessing.synchronize.Event, messagequeue: multiprocessing.queues.Queue,
                 rootpath: str, eval2dsubpath: str, masksubpath: str, fsndigits: int,
                 prefix: str, filenamepattern: str, filenamescheme: FileNameScheme, fsnlist: List[int],
                 ierrorprop: ErrorPropagationMethod, qerrorprop: ErrorPropagationMethod,
                 outliermethod: OutlierMethod, outlierthreshold: float, cormatLogarithmic: bool,
                 qrangemethod: QRangeMethod, qcount: int, bigmemorymode: bool, badfsns: List[int]):
        super().__init__(jobid, h5file, h5lock, stopEvent, messagequeue)
        self.loader = Loader(rootpath, eval2dsubpath, masksubpath, fsndigits, prefix, filenamepattern, filenamescheme)
        self.ierrorprop = ierrorprop
        self.qerrorprop = qerrorprop
        self.fsns = list(fsnlist)
        self.outliermethod = outliermethod
        self.outlierthreshold = outlierthreshold
        self.cormatLogarithmic = cormatLogarithmic
        self.qrangemethod = qrangemethod
        self.qcount = qcount
        self.bigmemorymode = bigmemorymode
        self.result = SummaryJobResults(jobid)
        self.result.badfsns = set(badfsns)

    def _loadheaders(self):
        # first load all header files
        t0 = time.monotonic()
        self.headers = []
        self.sendProgress('Loading headers {}/{}'.format(0, len(self.fsns)),
                          total=len(self.fsns), current=0)
        goodindex = []
        for i, fsn in enumerate(self.fsns, start=1):
            if self.killSwitch.is_set():
                raise BackgroundProcessError('Stop switch is set.')
            try:
                h = self.loader.loadHeader(fsn)
                if h.fsn != fsn:
                    raise ValueError('FSN in header ({}) is different than in the filename ({}).'.format(h.fsn, fsn))
                self.headers.append(h)
                goodindex.append(h.fsn not in self.result.badfsns)
                self.sendProgress('Loading headers {}/{}'.format(i, len(self.fsns)),
                                  total=len(self.fsns), current=i)
            except FileNotFoundError:
                continue
        self.goodindex = np.array(goodindex, dtype=np.bool)
        # check if all headers correspond to the same sample and distance
        self.sendMessage(f'{len(self.headers)} headers loaded in {self.result.time_loadheaders:.2f} seconds')
        if len({(h.title, float(h.distance[0])) for h in self.headers}) > 1:
            raise SummaryError('There are more samples/distances!')
        self.result.time_loadheaders = time.monotonic() - t0

    def _loadexposures(self):
        """Load all exposures, i.e. 2D images. Do radial averaging as well."""
        if not self.headers:
            self.sendMessage('No headers.')
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
        for i, h in enumerate(self.headers, start=0):
            if self.killSwitch.is_set():
                raise BackgroundProcessError('Stop switch is set.')
            try:
                ex = self.loader.loadExposure(h.fsn)
                radavg = ex.radial_average(
                    qbincenters=(self.qrangemethod, self.qcount),
                    errorprop=self.ierrorprop,
                    qerrorprop=self.qerrorprop,
                )
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

        notalreadybadfsns = [h.fsn for h in self.headers if h.fsn not in self.result.badfsns]
        assert len(notalreadybadfsns) == self.goodindex.sum()
        self.outliertest = OutlierTest(
            self.outliermethod, self.outlierthreshold, curves=self.curves[:, :, self.goodindex],
            fsns=notalreadybadfsns)
        self.result.newbadfsns=set(
            np.array(notalreadybadfsns, dtype=np.int)[self.outliertest.outlierverdict])
        self.result.badfsns=self.result.badfsns.union(self.result.newbadfsns)
        self.result.time_outlierdetection = time.monotonic() - t0

    def _summarize(self):
        """Calculate average scattering pattern and curve"""

        goodheaders = [h for h in self.headers if h.fsn not in self.result.badfsns]
        if not goodheaders:
            raise SummaryError('No good exposures found!')

        t0 = time.monotonic()
        # first average the headers, however fool this sounds...
        self.sendProgress('Collecting header data for averaged image...')
        t1 = time.monotonic()
        self.averagedHeader = Header.average(*goodheaders)
        assert self.averagedHeader.exposurecount == len(goodheaders)
        self.result.time_averaging_header = time.monotonic() - t1

        # summarize 2D and 1D datasets
        t1 = time.monotonic()
        self.sendProgress('Averaging exposures...', current=0, total=0)

        def exposureiterator(hs: List[Header], ldr: Loader):
            count=0
            for i, h in enumerate(hs):
                if self.killSwitch.is_set():
                    raise BackgroundProcessError('Stop switch is set.')
                if h.fsn in self.result.badfsns:
                    # do not include bad exposures
                    continue
                self.sendProgress('Averaging exposures {}/{}...'.format(i, len(hs)),
                                  current=i, total=len(hs))
                count+=1
                yield ldr.loadExposure(h.fsn, h)

        self.averagedExposure = Exposure.average(
            [ex for ex in self.exposures if ex.header.fsn not in self.result.badfsns] if self.bigmemorymode
            else exposureiterator(self.headers, self.loader),
            errorpropagation=self.ierrorprop)
        self.result.time_averaging_exposures = time.monotonic() - t1

        # Average curves
        t1 = time.monotonic()
        self.sendProgress('Averaging curves...', total=0, current=0)

        def curveiterator(curvesmatrix: np.ndarray):
            count=0
            for i in range(curvesmatrix.shape[2]):
                if self.killSwitch.is_set():
                    raise BackgroundProcessError('Stop switch is set.')
                yield Curve.fromArray(curvesmatrix[:, :, i])
                count+=1
            self.sendMessage(f'Averaged {count} curves for sample {self.headers[0].title} at {self.headers[0].distance[0]:.2f} mm')

        self.averagedCurve = Curve.average(curveiterator(self.curves[:, :, self.goodindex]),
                                           ierrorpropagation=self.ierrorprop,
                                           qerrorpropagation=self.qerrorprop)
        self.reintegratedCurve = self.averagedExposure.radial_average(
            (self.qrangemethod, self.qcount), errorprop=self.ierrorprop,
            qerrorprop=self.qerrorprop)
        self.result.time_averaging_curves = time.monotonic() - t1
        self.result.time_averaging = time.monotonic() - t0

    def _output(self):
        """Write results in the .h5 file."""
        t0 = time.monotonic()
        self.sendProgress('Waiting for HDF5 writer lock...')
        with self.h5io.writer(f'Samples/{self.headers[0].title}/{self.headers[0].distance[0]:.2f}') as group:
            t1 = time.monotonic()
            self.sendProgress('Writing HDF5 file...')
            # Set attributes of the <dist> group from the averaged header.
            self.h5io.writeHeader(self.averagedHeader, group)
            self.h5io.writeExposure(self.averagedExposure, group)
            try:
                del group['badfsns']
            except KeyError:
                pass
            group['badfsns'] = np.array(sorted(self.result.badfsns), dtype=np.int)
            try:
                del group['goodindex']
            except KeyError:
                pass
            group['goodindex'] = self.goodindex
            self.h5io.writeCurve(self.averagedCurve, group, 'curve_averaged')
            self.h5io.writeCurve(self.reintegratedCurve, group, 'curve_reintegrated')
            try:
                del group['curve']
            except KeyError:
                pass
            group['curve'] = h5py.SoftLink('curve_averaged')
            self.h5io.writeOutlierTest(group.name, self.outliertest)
            # save all curves
            for groupname in ['allcurves', 'curves']:
                try:
                    del group[groupname]
                except KeyError:
                    pass
            curvesgroup = group.create_group('allcurves')
            goodcurvesgroup = group.create_group('curves')
            # we will write outlier results per-curve. Do the common calculations beforehand.
            scoreindex = 0
            for i, (h, isgood) in enumerate(zip(self.headers, self.goodindex)):
                self.h5io.writeCurve(self.curves[:, :, i], curvesgroup, str(h.fsn))
                dataset = curvesgroup[str(h.fsn)]
                self.h5io.writeHeader(h, dataset)
                if isgood:
                    dataset.attrs['correlmat_bad'] = int(h.fsn in self.result.badfsns)
                    dataset.attrs['correlmat_discrp'] = self.outliertest.score[scoreindex]
                    scoreindex += 1
                else:
                    dataset.attrs['correlmat_bad'] = -1
                    dataset.attrs['correlmat_discrp'] = np.nan
                # make links in the 'curves' group to those fsns which were not bad at the beginning of this procedure
                if (h.fsn not in self.result.badfsns) or (h.fsn in self.result.newbadfsns):
                    goodcurvesgroup[str(h.fsn)] = h5py.SoftLink(dataset.name)

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
        finally:
            pass

        return self.result
