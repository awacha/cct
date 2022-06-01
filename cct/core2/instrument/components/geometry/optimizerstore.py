from typing import Any, List, Iterator, Dict

import numpy as np
from PyQt5 import QtCore


class OptimizerStore(QtCore.QAbstractItemModel):
    _optimizationresults: List[Dict[str, Any]]

    def __init__(self):
        self._optimizationresults = []
        super().__init__()

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        columnlabel = self.headerData(index.column(), QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
        optimizationresult = self._optimizationresults[index.row()]
        if role == QtCore.Qt.UserRole:
            return optimizationresult
        elif columnlabel == 'Intensity':
            if role == QtCore.Qt.DisplayRole:
                return f'{optimizationresult["intensity"]:.0f}'
            elif role == QtCore.Qt.EditRole:
                return optimizationresult["intensity"]
        elif columnlabel == 'Qmin':
            if role == QtCore.Qt.DisplayRole:
                return f'{optimizationresult["qmin"]:.4f}'
            elif role == QtCore.Qt.ToolTipRole:
                return f'Qmin: {optimizationresult["qmin"]:.4f} 1/nm, corresponding to Dmax: {2 * np.pi / optimizationresult["qmin"]:.0f} nm periodic distance and Rgmax {1 / optimizationresult["qmin"]:.0f} nm radius of gyration.'
            elif role == QtCore.Qt.EditRole:
                return optimizationresult["qmin"]
        elif columnlabel == 'Sample':
            if role == QtCore.Qt.DisplayRole:
                return f'{optimizationresult["dbeam_at_sample"]:.2f}'
            elif role == QtCore.Qt.ToolTipRole:
                return f'Beam diameter at sample: {optimizationresult["dbeam_at_sample"]:.2f} mm'
            elif role == QtCore.Qt.EditRole:
                return optimizationresult["dbeam_at_sample"]
        elif columnlabel == 'Beamstop':
            if role == QtCore.Qt.DisplayRole:
                return f'{optimizationresult["beamstop"]:.2f}'
            elif role == QtCore.Qt.EditRole:
                return optimizationresult["beamstop"]
        elif columnlabel == 'PH#1-PH#2':
            if role == QtCore.Qt.DisplayRole:
                return f'{optimizationresult["l1"]:.0f}'
            elif role == QtCore.Qt.ToolTipRole:
                return 'Spacers needed: ' + ' + '.join(
                    [f'{x:.0f} mm' for x in sorted(optimizationresult['l1_elements'])])
            elif role == QtCore.Qt.EditRole:
                return optimizationresult["l1"]
        elif columnlabel == 'PH#2-PH#3':
            if role == QtCore.Qt.DisplayRole:
                return f'{optimizationresult["l2"]:.0f}'
            elif role == QtCore.Qt.ToolTipRole:
                return 'Spacers needed: ' + ' + '.join(
                    [f'{x:.0f} mm' for x in sorted(optimizationresult['l2_elements'])])
            elif role == QtCore.Qt.EditRole:
                return optimizationresult["l2"]
        elif columnlabel == 'S-D':
            if role == QtCore.Qt.DisplayRole:
                return f'{optimizationresult["sd"]:.2f}'
            elif role == QtCore.Qt.ToolTipRole:
                return 'Flight pipes needed: ' + ' + '.join(
                    [f'{x:.0f} mm' for x in sorted(optimizationresult["flightpipes"])])
            elif role == QtCore.Qt.EditRole:
                return optimizationresult["sd"]
        elif columnlabel == 'PH#1':
            if role == QtCore.Qt.DisplayRole:
                return f'{optimizationresult["pinhole_1"]:.0f}'
            elif role == QtCore.Qt.EditRole:
                return optimizationresult["pinhole_1"]
        elif columnlabel == 'PH#2':
            if role == QtCore.Qt.DisplayRole:
                return f'{optimizationresult["pinhole_2"]:.0f}'
            elif role == QtCore.Qt.EditRole:
                return optimizationresult["pinhole_2"]
        elif columnlabel == 'PH#3':
            if role == QtCore.Qt.DisplayRole:
                return f'{optimizationresult["pinhole_3"]:.0f}'
            elif role == QtCore.Qt.EditRole:
                return optimizationresult["pinhole_3"]
        else:
            assert False

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 10

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._optimizationresults)

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def sort(self, column: int, order: QtCore.Qt.SortOrder = ...) -> None:
        columnlabel = self.headerData(column, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
        self.beginResetModel()
        if columnlabel == 'Intensity':
            self._optimizationresults.sort(key=lambda optresult: optresult["intensity"],
                                           reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'Qmin':
            self._optimizationresults.sort(key=lambda optresult: optresult["qmin"],
                                           reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'Sample':
            self._optimizationresults.sort(key=lambda optresult: optresult["dbeam_at_sample"],
                                           reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'Beamstop':
            self._optimizationresults.sort(key=lambda optresult: optresult["beamstop"],
                                           reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'PH#1-PH#2':
            self._optimizationresults.sort(key=lambda optresult: optresult["l1"],
                                           reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'PH#2-PH#3':
            self._optimizationresults.sort(key=lambda optresult: optresult["l2"],
                                           reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'S-D':
            self._optimizationresults.sort(key=lambda optresult: optresult["sd"],
                                           reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'PH#1':
            self._optimizationresults.sort(key=lambda optresult: optresult["pinhole_1"],
                                           reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'PH#2':
            self._optimizationresults.sort(key=lambda optresult: optresult["pinhole_2"],
                                           reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'PH#3':
            self._optimizationresults.sort(key=lambda optresult: optresult["pinhole_3"],
                                           reverse=(order == QtCore.Qt.DescendingOrder))
        else:
            assert False
        self.endResetModel()

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Intensity', 'Qmin', 'Sample', 'Beamstop', 'PH#1-PH#2', 'PH#2-PH#3', 'S-D', 'PH#1', 'PH#2', 'PH#3'][
                section]

    def addOptResult(self, optresult: Dict[str, Any]):
        self.beginInsertRows(QtCore.QModelIndex(), len(self._optimizationresults), len(self._optimizationresults))
        for key in ['l1_elements', 'l2_elements', 'pinhole_1', 'pinhole_2', 'pinhole_3', 'flightpipes', 'beamstop',
                    'l1', 'l2', 'ph3todetector', 'sd', 'dbeam_at_ph3', 'dbeam_at_bs', 'dparasitic_at_bs',
                    'dbeam_at_sample', 'qmin', 'intensity']:
            assert key in optresult
        self._optimizationresults.append(optresult)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self._optimizationresults = []
        self.endResetModel()

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        for result in self._optimizationresults:
            yield result

    def __getitem__(self, item: int) -> Dict[str, Any]:
        return self._optimizationresults[item]

    def __len__(self) -> int:
        return len(self._optimizationresults)
