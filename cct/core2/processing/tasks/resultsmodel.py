from configparser import ConfigParser
from typing import Any, List, Tuple
import logging

from PyQt5 import QtCore, QtGui
from .task import ProcessingTask
from ...dataclasses import Header
from ..calculations.resultsentry import SampleDistanceEntry, SampleDistanceEntryType

import numpy as np

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ResultsModel(ProcessingTask):
    _data: List[SampleDistanceEntry]

    def __init__(self, *args, **kwargs):
        self._data = []
        super().__init__(*args, **kwargs)
        self.reload()
    
    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 9
    
    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        sde = self._data[index.row()]
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return sde.samplename
            elif index.column() == 1:
                return sde.distancekey
            elif index.column() == 2:
                return sde.header.sample_category
            elif index.column() == 3:
                return str(sde.header.exposurecount)
            elif index.column() == 4:
                hours = sde.header.exposuretime[0] // 3600
                minutes = (sde.header.exposuretime[0] - hours*3600) // 60
                seconds = (sde.header.exposuretime[0] - hours*3600 - minutes*60)
                return f'{hours:02.0f}:{minutes:02.0f}:{seconds:04.1f}'
            elif index.column() == 5:
                if sde.isDerived():
                    return '--'
                try:
                    return f'{sde.outliertest.shapiroTest().pvalue:.3g}'
                except (AttributeError, ValueError, TypeError) as ve:
                    return str(ve)
            elif index.column() == 6:
                if sde.isDerived():
                    return '--'
                try:
                    return f'{sde.outliertest.schillingTest().pvalue:.3g}'
                except (AttributeError, ValueError, TypeError) as ve:
                    return str(ve)
            elif index.column() == 7:
                if sde.isDerived():
                    return '--'
                try:
                    return f'{sde.outliertest.FtestQuadraticVsConstant().pvalue:.3g}'
                except (AttributeError, ValueError, TypeError) as ve:
                    return str(ve)
            elif index.column() == 8:
                if sde.isDerived():
                    return '--'
                try:
                    return f'{sde.outliertest.FtestLinearVsConstant().pvalue:.3g}'
                except (AttributeError, ValueError, TypeError) as ve:
                    return str(ve)
        elif role == QtCore.Qt.ToolTipRole:
            return self.headerData(index.column(), QtCore.Qt.Horizontal, QtCore.Qt.ToolTipRole)
        elif role == QtCore.Qt.UserRole:
            return sde
        elif role == QtCore.Qt.BackgroundColorRole:
            if (index.column() in [5,6]) and sde.isDerived():
                return None
            if index.column() == 5:
                try:
                    return QtGui.QColor('red') if sde.outliertest.shapiroTest().pvalue < 0.05 else QtGui.QColor('lightgreen')
                except:
                    return QtGui.QColor('orange')
            elif index.column() == 6:
                try:
                    return QtGui.QColor('red') if sde.outliertest.schillingTest().pvalue < 0.05 else QtGui.QColor('lightgreen')
                except:
                    return QtGui.QColor('orange')
            elif index.column() == 7:
                try:
                    return QtGui.QColor('red') if sde.outliertest.FtestQuadraticVsConstant().pvalue < 0.05 else QtGui.QColor('lightgreen')
                except:
                    return QtGui.QColor('orange')
            elif index.column() == 8:
                try:
                    return QtGui.QColor('red') if sde.outliertest.FtestLinearVsConstant().pvalue < 0.05 else QtGui.QColor('lightgreen')
                except:
                    return QtGui.QColor('orange')
        elif role == QtCore.Qt.TextColorRole:
            if (index.column() in [5,6]) and sde.isDerived():
                return None
            if (index.column() == 5) or (index.column() == 6):
                return QtGui.QColor('black')
            else:
                return None

        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Sample', 'Distance', 'Category', 'Count', 'Total time', 'Shapiro test', 'Schilling test', 'Quadratic vs. const F-test', 'Linear vs. const F-test'][section]
        elif (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.ToolTipRole):
            return [
                'The name of the sample',
                'Sample-to-detector distance (or other designation, e.g. "merged")',
                'Curve type (sample measurement, subtracted measurement etc.)',
                'Number of exposures which make up the averaged result',
                'Total exposure time (only "good" exposures are counted)',
                'Shapiro-Wilk test for normality of the average difference scores of exposures. '
                'Rejection of the 0-hypothesis might point towards some instability over the course '
                'of the experiment.',
                'Schilling\' coin-toss test for the "randomness" of the average difference scores of '
                'the exposures. If the variation of the difference score around the mean is not random '
                '(too long runs occur of larger/smaller than mean values), it indicates a change in the '
                'scattering curves over time.',
                'Result of an F-test, assessing if the variation of the average difference score over '
                'time can be significantly better fitted by a quadratic function than a simple constant. '
                'In cases where both the instrument and the sample is stable over time, the average '
                'difference score of the exposures oscillates around a constant value, deviations are '
                'only due to random statistical fluctuations. But if there is some systematic change '
                'over time, exposures at the beginning and the end will have larger average difference '
                'scores than those in the middle, resulting in a convex curve.',
                'Result of an F-test, assessing if the variation of the average difference score over '
                'time can be significantly better fitted by a linear function than a simple constant. '
                'The rationale of this test is similar as of the F-test comparing the quadratic fit to '
                'the constant.'
            ]

    def reload(self):
        self.beginResetModel()
        try:
            self._data=[]
            for samplename in self.settings.h5io.samplenames():
                logger.debug(f'Reading sample {samplename}')
                for dist in self.settings.h5io.distancekeys(samplename, onlynumeric=False):
                    logger.debug(f'Reading distance {dist}')
                    self._data.append(SampleDistanceEntry(samplename, dist, self.processing.settings.h5io))
        except OSError:
            logger.warning('Cannot open HDF5 file.')
            # when the HDF5 file cannot be opened.
            pass
        finally:
            self.endResetModel()

    def start(self):
        pass

    def get(self, samplename: str, distkey: str) -> SampleDistanceEntry:
        return [sde for sde in self._data if sde.samplename == samplename and sde.distancekey == distkey][0]

    def remove(self, samplename:str, distancekey:str):
        rows = [i for i, sde in enumerate(self._data) if sde.samplename == samplename and sde.distancekey == distancekey]
        if not rows:
            raise ValueError(f'Cannot remove {samplename}@{distancekey}: no such measurement')
        assert len(rows) == 1
        row = rows[0]
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        self.settings.h5io.removeDistance(samplename, distancekey)

    def __contains__(self, item: Tuple[str, str]) -> bool:
        return item in self.settings.h5io

