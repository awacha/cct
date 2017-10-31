import logging
import typing

import numpy as np
import scipy.odr
from PyQt5 import QtCore
from sastool.classes2 import Exposure, Curve
from sastool.misc.basicfit import findpeak_multi, findpeak_single
from sastool.misc.errorvalue import ErrorValue
from sastool.utils2d.centering import findbeam_radialpeak

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class CalibrationModel(QtCore.QAbstractItemModel):
    # columns: fsn, distance, beam center X, beam center Y

    def __init__(self, pixelsize: ErrorValue, wavelength: ErrorValue, peaksidepoints=10):
        super().__init__(None)
        self._peaksidepoints = peaksidepoints
        self._pixelsize = pixelsize
        self._wavelength = wavelength
        self._data = []

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
                    findpeak_npoints: int = 3):
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
        self._data.append(
            [fsn, exposure.header.beamcenterx, exposure.header.beamcentery, shift, exposure.radial_average(pixel=True),
             exposure, []])
        self.endInsertRows()
        self.findPeaks(len(self._data) - 1, 0, findpeak_npoints)

    def fsns(self) -> np.ndarray:
        return np.array([d[0] for d in self._data])

    def peaks(self, setindex: int) -> np.ndarray:
        return np.array([d[6][setindex].val for d in self._data])

    def shifts(self) -> np.ndarray:
        return np.array([d[3].val for d in self._data])

    def dshifts(self) -> np.ndarray:
        return np.array([d[3].err for d in self._data])

    def dpeaks(self, setindex: int) -> np.ndarray:
        return np.array([d[6][setindex].err for d in self._data])

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
            d[1] = bcx
            d[2] = bcy
            d[4] = d[5].radial_average(pixel=True)
            self.dataChanged.emit(self.index(i, 1), self.index(i, 2), [QtCore.Qt.DisplayRole])

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...):
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._data[row]
        self.endRemoveRows()

    def findPeaks(self, row: int, setindex: typing.Optional[int] = None, Npoints: int = 4):
        curve = self._data[row][4]
        assert isinstance(curve, Curve)
        if row < 2:
            self._data[row][6] = findpeak_multi(curve.q, curve.Intensity, curve.Error, Npoints, 0)[0]
        else:
            foundpeaks = []
            for peakindex in range(len(self._data[0][6])):
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
                    foundpeaks.append(ErrorValue(np.nan, np.nan))
                else:
                    c = curve.trim(posguess - 10, posguess + 10)
                    foundpeaks.append(findpeak_single(c.q, c.Intensity, c.Error, posguess, signs=(1,))[0])
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
