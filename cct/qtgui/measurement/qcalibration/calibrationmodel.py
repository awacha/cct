import logging
import typing

import numpy as np
import scipy.odr
from PyQt5 import QtCore
from sastool.classes2 import Exposure, Curve
from sastool.misc.basicfit import findpeak_multi, findpeak_asymmetric
from sastool.misc.errorvalue import ErrorValue
from sastool.utils2d.centering import findbeam_radialpeak

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class CalibrationModel(QtCore.QAbstractItemModel):
    # columns: fsn, distance, beam center X, beam center Y, exposure, list of peaks

    def __init__(self, pixelsize: ErrorValue, wavelength: ErrorValue, peaksidepoints=10):
        super().__init__(None)
        self._peaksidepoints = peaksidepoints
        self._pixelsize = pixelsize
        self._wavelength = wavelength
        self._data = []
        self._findpeaks_npoints = 4
        self._findpeaks_tolerance = 0
        self._findpeaks_threshold = 0

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return '{:d}'.format(self._data[index.row()][index.column()])
            elif index.column() == 1:
                return '{0.val:.3f} \xb1 {0.err:.3f}'.format(self._data[index.row()][3])
            elif index.column() == 2:
                return '{:.3f}'.format(self._data[index.row()][1])
            elif index.column() == 3:
                return '{:.3f}'.format(self._data[index.row()][2])

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['FSN', 'Shift (mm)', 'Beam X', 'Beam Y'][section]
        else:
            return None

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = ...):
        return False

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 4

    def addExposure(self, fsn: int, exposure: Exposure, shift: ErrorValue, refinebeampos: bool = True,
                    findpeak_npoints: int = 3, findpeak_tolerance: int=0, findpeak_threshold:float = 0.0):
        if refinebeampos:
            rpeak = self._getfirstpeak(exposure.radial_average(pixel=True))
            newy, newx = findbeam_radialpeak(
                exposure.intensity,
                [exposure.header.beamcentery.val, exposure.header.beamcenterx.val],
                exposure.mask,
                rpeak - self._peaksidepoints,
                rpeak + self._peaksidepoints,
            )
            exposure.header.beamcenterx = ErrorValue(newx, 0)
            exposure.header.beamcentery = ErrorValue(newy, 0)
        self.beginInsertRows(QtCore.QModelIndex(), self.rowCount(), self.rowCount() + 1)
        radavg = exposure.radial_average(pixel=True)
        radavg /=np.nanmax(radavg.Intensity)
        self._data.append(
            [fsn, exposure.header.beamcenterx, exposure.header.beamcentery, shift, radavg,
             exposure, []])
        self.endInsertRows()
        self._findpeaks_npoints = findpeak_npoints
        self._findpeaks_tolerance = findpeak_tolerance
        self._findpeaks_threshold = findpeak_threshold
        self.findPeaks(len(self._data) - 1, None, findpeak_npoints, findpeak_tolerance, findpeak_threshold)

    def fsns(self) -> np.ndarray:
        return np.array([d[0] for d in self._data])

    def peaks(self, setindex: int) -> np.ndarray:
        lis = []
        for d in self._data:
            try:
                lis.append(d[6][setindex].val)
            except IndexError:
                lis.append(np.nan)
        return np.array(lis)

    def shifts(self) -> np.ndarray:
        return np.array([d[3].val for d in self._data])

    def dshifts(self) -> np.ndarray:
        return np.array([d[3].err for d in self._data])

    def dpeaks(self, setindex: int) -> np.ndarray:
        lis = []
        for d in self._data:
            try:
                lis.append(d[6][setindex].err)
            except IndexError:
                lis.append(np.nan)
        return np.array(lis)

    def beamposxs(self) -> np.ndarray:
        return np.array([d[5].header.beamcenterx.val for d in self._data])

    def dbeamposxs(self) -> np.ndarray:
        return np.array([d[5].header.beamcenterx.err for d in self._data])

    def beamposys(self) -> np.ndarray:
        return np.array([d[5].header.beamcentery.val for d in self._data])

    def dbeamposys(self) -> np.ndarray:
        return np.array([d[5].header.beamcentery.err for d in self._data])

    @staticmethod
    def _getfirstpeak(curve: Curve, pointsrequiredontheleft: int = 3) -> float:
        firstindex = 0
        try:
            # we need the next loop to get rid of the decreasing starting slope.
            while (curve.Intensity[firstindex:].argmax() < pointsrequiredontheleft):
                firstindex += 1
        except ValueError:
            # this happens when there is no good peak
            raise
        return curve.q[firstindex:][curve.Intensity[firstindex:].argmax()]

    def updateShifts(self, shift: ErrorValue):
        for i, d in enumerate(self._data):
            d[3] = i * shift
        self.dataChanged.emit(self.index(0, 1), self.index(self.rowCount(), 1), [QtCore.Qt.DisplayRole])

    def refineBeamCenter(self):
        for i, d in enumerate(self._data):
            if i == 0:
                bcx, bcy = d[5].header.beamcenterx.val, d[5].header.beamcentery.val
            else:
                bcx, bcy = self._data[i - 1][5].header.beamcenterx.val, self._data[i - 1][5].header.beamcentery.val
            peak = self._getfirstpeak(d[4])
            bcy, bcx = findbeam_radialpeak(d[5].intensity, [bcy, bcx], d[5].mask, peak - self._peaksidepoints,
                                           peak + self._peaksidepoints)
            d[5].header.beamcenterx = ErrorValue(bcx, 0)
            d[5].header.beamcentery = ErrorValue(bcy, 0)
            d[1] = d[5].header.beamcenterx
            d[2] = d[5].header.beamcentery
            radavg = d[5].radial_average(pixel=True)
            d[4] = radavg/np.nanmax(radavg.Intensity)
            self.dataChanged.emit(self.index(i, 1), self.index(i, 2), [QtCore.Qt.DisplayRole])
            self.findPeaks(i, None, self._findpeaks_npoints)

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...):
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._data[row]
        self.endRemoveRows()

    def findPeaks(self, row: int, setindex: typing.Optional[int] = None, Npoints: int = 4, Ntol: int=0, threshold: float=0.0):
        curve = self._data[row][4].sanitize()
        logger.debug('Finding peaks for row {}'.format(row))
        assert isinstance(curve, Curve)
#        positions = [curve.q[x] for x in find_peaks_cwt(curve.Intensity, [Npoints]) if x>Npoints and x<len(curve)-Npoints]
#        logger.debug('Found peaks using scipy.signal.find_peaks_cwt: {}'.format(positions))
#        foundpeaks = []
#        for posguess in positions:
#            logger.debug('Refining peak at {}.'.format(posguess))
#            c = curve.sanitize().trim(posguess - 3, posguess + 3)
#            try:
#                foundpeaks.append(findpeak_asymmetric(c.q, c.Intensity, c.Error)[0])
#            except ValueError as ve:
#                logger.error(ve)
#                foundpeaks.append(ErrorValue(np.nan, np.nan))
#        logger.debug('Refined peaks using findpeak_asymmetric: {}'.format(foundpeaks))
#        self._data[row][6]=foundpeaks
        if row < 2:
            foundpeaks = findpeak_multi(curve.q, curve.Intensity, curve.Error, Npoints, Ntol)[0]
            for p in foundpeaks:
                logger.debug('Peak {}: I {}.'.format(p,np.interp(float(p), curve.q, curve.Intensity)))
            foundpeaks = [p for p in foundpeaks if np.interp(float(p), curve.q, curve.Intensity) > threshold]
            logger.debug('Found {} peaks using the multipeak fitting.'.format(len(self._data[row][6])))
        else:
            foundpeaks = []
            logger.debug('Looking for {} peaks.'.format(len(self._data[0][6])))
            for peakindex in range(len(self._data[0][6])):
                logger.debug('Looking for peak #{}.'.format(peakindex))
                shifts = []
                peaks = []
                for rowindex in range(row):
                    try:
                        peaks.append(self._data[rowindex][6][peakindex].val)
                    except IndexError:
                        continue
                    shifts.append(self._data[rowindex][3].val)
                shifts = np.array(shifts)
                peaks = np.array(peaks)
                valid = np.logical_and(np.isfinite(peaks), np.isfinite(shifts))
                shifts = shifts[valid]
                peaks = peaks[valid]
                results = np.polyfit(shifts, peaks, 1)
                posguess = self._data[row][3].val * results[0] + results[1]
                if posguess > curve.q.max():
                    logger.debug('Guessed position is outside the q range.')
                    foundpeaks.append(ErrorValue(np.nan, np.nan))
                else:
                    c = curve.trim(posguess - 3, posguess + 3)
                    foundpeaks.append(findpeak_asymmetric(c.q, c.Intensity, c.Error)[0])
                    logger.debug('Found peak: {}'.format(foundpeaks[-1]))
        self._data[row][6] = foundpeaks
        if setindex is not None:
            return self._data[row][6][setindex]

    def alpha(self, direction: typing.Optional[str] = None):
        if direction is None:
            direction = 'both'
        if direction.lower() == 'x':
            bc = ErrorValue(self.beamposxs(), self.dbeamposxs())
        elif direction.upper() == 'y':
            bc = ErrorValue(self.beamposys(), self.dbeamposys())
        else:
            bcx = ErrorValue(self.beamposxs(), self.dbeamposxs())
            bcy = ErrorValue(self.beamposys(), self.dbeamposys())
            bc = (bcx ** 2 + bcy ** 2) ** 0.5
        bc = bc * self._pixelsize
        dshifts = self.dshifts()
        if not (dshifts > 0).sum():
            dshifts = np.zeros_like(dshifts) + 0.01
        else:
            dshifts[dshifts <= 0] = np.nanmin(dshifts[dshifts > 0])
        data = scipy.odr.RealData(self.shifts(), bc.val, dshifts, bc.err)
        if len(data.x) < 2:
            raise ValueError
        poly = np.polyfit(data.x, data.y, 1)
        model = scipy.odr.Model(lambda params, x: params[0] * x + params[1])
        odr = scipy.odr.ODR(data, model, [poly[0], poly[1]])
        output = odr.run()
        assert isinstance(output, scipy.odr.Output)
        tgalpha = ErrorValue(output.beta[0], output.sd_beta[0])
        bc0 = ErrorValue(output.beta[1], output.sd_beta[1])
        return tgalpha.arctan()

    def alphay(self):
        return self.alpha('y')

    def alphax(self):
        return self.alpha('x')

    def trueshifts(self):
        return ErrorValue(self.shifts(), self.dshifts())
        return ErrorValue(self.shifts(), self.dshifts()) / self.alpha().cos()

    def calibrate(self, setindex: int):
        shifts = self.trueshifts()
        if not (shifts.err > 0).sum():
            shifts.err = np.zeros_like(shifts.err) + 0.01
        else:
            shifts.err[shifts.err <= 0] = np.nanmin(shifts.err[shifts.err > 0])
        peaks = self.peaks(setindex)
        dpeaks = self.dpeaks(setindex)
        valid = np.logical_and(
            np.logical_and(np.isfinite(shifts.val), np.isfinite(shifts.err)),
            np.logical_and(np.isfinite(peaks), np.isfinite(dpeaks)))
        data = scipy.odr.RealData(shifts.val[valid], peaks[valid], shifts.err[valid], dpeaks[valid])
        if len(data.x) < 2:
            raise ValueError
        model = scipy.odr.Model(lambda params, x: params[0] * x + params[1])
        poly = np.polyfit(data.x, data.y, 1)
        odr = scipy.odr.ODR(data, model, [poly[0], poly[1]])
        output = odr.run()
        a = ErrorValue(output.beta[0], output.sd_beta[0])
        b = ErrorValue(output.beta[1], output.sd_beta[1])
        dist0 = b / a
        q = ((a * self._pixelsize).arctan() * 0.5).sin() * 4 * np.pi / self._wavelength
        return q, dist0

    def exposure(self, index: typing.Union[QtCore.QModelIndex, int]) -> Exposure:
        try:
            index = index.row()
        except AttributeError:
            pass
        return self._data[index][5]

    def curve(self, index: typing.Union[QtCore.QModelIndex, int]) -> Curve:
        try:
            index = index.row()
        except AttributeError:
            pass
        return self._data[index][4]

    def peakClassesCount(self):
        return len(self._data[0][6])

    def clear(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def fsn(self, index: typing.Union[QtCore.QModelIndex, int]) -> int:
        try:
            index = index.row()
        except AttributeError:
            pass
        return self._data[index][0]
