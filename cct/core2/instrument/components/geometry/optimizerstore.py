from typing import Any, List, Iterator, Dict

import numpy as np
from PyQt5 import QtCore


class OptimizerStore(QtCore.QAbstractItemModel):
    _presets: List[Dict[str, Any]]

    def __init__(self):
        self._presets = []
        super().__init__()

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        columnlabel = self.headerData(index.column(), QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
        preset = self._presets[index.row()]
        if columnlabel == 'Intensity':
            if role == QtCore.Qt.DisplayRole:
                return f'{preset["intensity"]:.0f}'
        elif columnlabel == 'Qmin':
            if role == QtCore.Qt.DisplayRole:
                return f'{preset["qmin"]:.4f}'
            elif role == QtCore.Qt.ToolTipRole:
                return f'Qmin: {preset["qmin"]:.4f} 1/nm, corresponding to Dmax: {2 * np.pi / preset.qmin:.0f} nm periodic distance and Rgmax {1 / preset["qmin"]:.0f} nm radius of gyration.'
        elif columnlabel == 'Sample':
            if role == QtCore.Qt.DisplayRole:
                return f'{preset["dbeam_at_sample"]:.2f}'
            elif role == QtCore.Qt.ToolTipRole:
                return f'Beam diameter at sample: {preset["dbeam_at_sample"]:.2f} mm'
        elif columnlabel == 'Beamstop':
            if role == QtCore.Qt.DisplayRole:
                return f'{preset["beamstop"]:.2f}'
        elif columnlabel == 'PH#1-PH#2':
            if role == QtCore.Qt.DisplayRole:
                return f'{preset["l1"]:.0f}'
            elif role == QtCore.Qt.ToolTipRole:
                return 'Spacers needed: ' + ' + '.join([f'{x:.0f} mm' for x in sorted(preset['l1_elements'])])
        elif columnlabel == 'PH#2-PH#3':
            if role == QtCore.Qt.DisplayRole:
                return f'{preset["l2"]:.0f}'
            elif role == QtCore.Qt.ToolTipRole:
                return 'Spacers needed: ' + ' + '.join([f'{x:.0f} mm' for x in sorted(preset['l2_elements'])])
        elif columnlabel == 'S-D':
            if role == QtCore.Qt.DisplayRole:
                return f'{preset["sd"]:.2f}'
            elif role == QtCore.Qt.ToolTipRole:
                return 'Flight pipes needed: ' + ' + '.join([f'{x:.0f} mm' for x in sorted(preset["flightpipes"])])
        elif columnlabel == 'PH#1':
            if role == QtCore.Qt.DisplayRole:
                return f'{preset["pinhole_1"]:.0f}'
        elif columnlabel == 'PH#2':
            if role == QtCore.Qt.DisplayRole:
                return f'{preset["pinhole_2"]:.0f}'
        elif columnlabel == 'PH#3':
            if role == QtCore.Qt.DisplayRole:
                return f'{preset["pinhole_3"]:.0f}'
        else:
            assert False

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 10

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._presets)

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def sort(self, column: int, order: QtCore.Qt.SortOrder = ...) -> None:
        columnlabel = self.headerData(column, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
        self.beginResetModel()
        if columnlabel == 'Intensity':
            self._presets.sort(key=lambda preset: preset["intensity"], reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'Qmin':
            self._presets.sort(key=lambda preset: preset["qmin"], reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'Sample':
            self._presets.sort(key=lambda preset: preset["dbeam_at_sample"], reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'Beamstop':
            self._presets.sort(key=lambda preset: preset["beamstop"], reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'PH#1-PH#2':
            self._presets.sort(key=lambda preset: preset["l1"], reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'PH#2-PH#3':
            self._presets.sort(key=lambda preset: preset["l2"], reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'S-D':
            self._presets.sort(key=lambda preset: preset["sd"], reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'PH#1':
            self._presets.sort(key=lambda preset: preset["pinhole_1"], reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'PH#2':
            self._presets.sort(key=lambda preset: preset["pinhole_2"], reverse=(order == QtCore.Qt.DescendingOrder))
        elif columnlabel == 'PH#3':
            self._presets.sort(key=lambda preset: preset["pinhole_3"], reverse=(order == QtCore.Qt.DescendingOrder))
        else:
            assert False
        self.endResetModel()

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Intensity', 'Qmin', 'Sample', 'Beamstop', 'PH#1-PH#2', 'PH#2-PH#3', 'S-D', 'PH#1', 'PH#2', 'PH#3'][
                section]

    def addOptResult(self, optresult: Dict[str, Any]):
        self.beginInsertRows(QtCore.QModelIndex(), len(self._presets), len(self._presets))
        for key in ['l1_elements', 'l2_elements', 'pinhole_1', 'pinhole_2', 'pinhole_3', 'flightpipes', 'beamstop', 'l1', 'l2', 'ph3todetector', 'sd', 'dbeam_at_ph3', 'dbeam_at_bs', 'dparasitic_at_bs', 'dbeam_at_sample', 'qmin', 'intensity']:
            assert key in optresult
        self._presets.append(optresult)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self._presets = []
        self.endResetModel()

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        for preset in self._presets:
            yield preset

    def __getitem__(self, item: int) -> Dict[str, Any]:
        return self._presets[item]

    def __len__(self) -> int:
        return len(self._presets)
