from typing import Optional

from PyQt5 import QtCore

from .....core.devices.motor import Motor
from .....core.instrument.instrument import Instrument


class MotorAutoCalibrationModel(QtCore.QAbstractItemModel):
    # columns: name, position, left limit, right limit, pos before, pos after, delta
    def __init__(self, credo:Instrument):
        super().__init__()
        self.credo = credo
        self._rows = []

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        if not isinstance(parent, QtCore.QModelIndex):
            parent = QtCore.QModelIndex()
        if not parent.isValid():
            return 7
        else:
            return 0

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        if not isinstance(parent, QtCore.QModelIndex):
            parent = QtCore.QModelIndex()
        if not parent.isValid():
            return len(self._rows)
        else:
            return 0

    def addMotor(self, name:str):
        mot = self.credo.motors[name]
        assert isinstance(mot, Motor)
        self.beginInsertRows(QtCore.QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append([name, mot.where(), mot.get_variable('softleft'), mot.get_variable('softright'), mot.where(), None, None])
        self.endInsertRows()

    def removeMotor(self, name:str):
        index = [i for i,r in enumerate(self._rows) if r[0]==name][0]
        self.beginRemoveRows(QtCore.QModelIndex(), index, index)
        del self._rows[index]
        self.endRemoveRows()

    def updateMotorPosition(self, name:str, newpos:float):
        index = [i for i,r in enumerate(self._rows) if r[0]==name][0]
        self._rows[index][1] = newpos
        self.dataChanged.emit(self.index(index, 1), self.index(index, 1))

    def updateMotorLeftLimit(self, name:str, leftlimit:float):
        index = [i for i,r in enumerate(self._rows) if r[0]==name][0]
        self._rows[index][2] = leftlimit
        self.dataChanged.emit(self.index(index, 2), self.index(index, 2))

    def updateMotorRightLimit(self, name:str, rightlimit:float):
        index = [i for i,r in enumerate(self._rows) if r[0]==name][0]
        self._rows[index][3] = rightlimit
        self.dataChanged.emit(self.index(index, 3), self.index(index, 3))

    def updateMotorPositionBefore(self, name:str, posbefore:float):
        index = [i for i,r in enumerate(self._rows) if r[0]==name][0]
        self._rows[index][4] = posbefore
        self.dataChanged.emit(self.index(index, 4), self.index(index, 4))

    def updateMotorPositionAfter(self, name:str, posafter: float):
        index = [i for i,r in enumerate(self._rows) if r[0]==name][0]
        self._rows[index][5] = posafter
        self.dataChanged.emit(self.index(index, 5), self.index(index, 5))

    def calculateMotorDelta(self, name:str):
        index = [i for i,r in enumerate(self._rows) if r[0]==name][0]
        before = self._rows[index][4]
        after = self._rows[index][5]
        if before is not None and after is not None:
            self._rows[index][6]=after-before
        else:
            self._rows[index][6]=None
        self.dataChanged.emit(self.index(index, 6), self.index(index, 6))

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role == QtCore.Qt.DisplayRole:
            value=self._rows[index.row()][index.column()]
            if value is None:
                return ''
            elif isinstance(value, float):
                return '{:.04f}'.format(value)
            else:
                return value
        else:
            return None

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        if not isinstance(parent, QtCore.QModelIndex):
            parent = QtCore.QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, None)
        else:
            return QtCore.QModelIndex()

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role==QtCore.Qt.DisplayRole:
            return ['Motor name','Position','Soft left', 'Soft right', 'Position before', 'Position after', 'Delta'][section]
        else:
            return None

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...):
        if not isinstance(parent, QtCore.QModelIndex):
            parent = QtCore.QModelIndex()
        if parent.isValid():
            return None
        else:
            self.beginRemoveRows(parent, row, row)
            del self._rows[row]
            self.endRemoveRows()

    def __contains__(self, item):
        return item in [r[0] for r in self._rows]

    def resetCalibrationData(self, name:Optional[str] = None):
        for r in self._rows:
            if name is not None and r[0]!=name:
                continue
            mot = self.credo.motors[r[0]]
            assert isinstance(mot, Motor)
            r[4]= mot.where()
            r[5]=None
            r[6]=None

    def nextMotor(self):
        for r in self._rows:
            if r[5] is None or r[6] is None:
                return r[0]
        return None
