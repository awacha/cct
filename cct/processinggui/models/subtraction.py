import typing

from PyQt5 import QtCore


class Subtraction:
    ValidMethods = ['None', 'Constant', 'Interval', 'Power-law']
    samplename: str
    backgroundname: typing.Optional[str]
    _scalingmethod: str  # 'None', 'Constant', 'Interval', 'Power-law'
    scalingparameters: typing.Any

    def __init__(self, samplename: str, backgroundname: typing.Optional[str] = None, scalingmethod: str = 'None',
                 scalingparameters: typing.Any = None):
        self.samplename = samplename
        self.backgroundname = backgroundname
        self.scalingmethod = scalingmethod
        self.scalingparameters = scalingparameters

    @property
    def scalingmethod(self) -> str:
        return self._scalingmethod

    @scalingmethod.setter
    def scalingmethod(self, newvalue: str):
        if newvalue not in ['None', 'Constant', 'Interval', 'Power-law']:
            raise ValueError('Invalid scaling method: "{}" (type: {})'.format(newvalue, type(newvalue)))
        self._scalingmethod = newvalue
        if newvalue == 'None':
            self.scalingparameters = None
        elif newvalue == 'Constant':
            self.scalingparameters = 0
        elif newvalue == 'Interval':
            self.scalingparameters = (0, 0)
        elif newvalue == 'Power-law':
            self.scalingparameters = (0, 0)
        else:
            assert False

    def formatParameters(self) -> str:
        if self._scalingmethod == 'None':
            return '--'
        elif self._scalingmethod == 'Constant':
            return '{:.6f}'.format(self.scalingparameters)
        elif self._scalingmethod == 'Interval':
            return '[{:.3f}, {:.3f}]'.format(*self.scalingparameters)
        elif self._scalingmethod == 'Power-law':
            return '[{:.3f}, {:.3f}]'.format(*self.scalingparameters)
        else:
            raise ValueError('Invalid scaling method: {}'.format(self._scalingmethod))


class SubtractionModel(QtCore.QAbstractItemModel):
    _columnnames = ['Sample', 'Background', 'Scaling method', 'Scaling parameters']  # fill this
    _data: typing.List[Subtraction] = None

    def __init__(self):
        super().__init__()
        self._data = []

    def rowCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._columnnames)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> typing.Any:
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return self._data[index.row()].samplename
            elif index.column() == 1:
                return self._data[index.row()].backgroundname if self._data[index.row()].backgroundname is not None else '-- None --'
            elif index.column() == 2:
                return self._data[index.row()].scalingmethod
            elif index.column() == 3:
                return self._data[index.row()].formatParameters()
        elif role == QtCore.Qt.EditRole:
            if index.column() == 3:
                return self._data[index.row()].scalingparameters
        return None

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = None) -> bool:
        if index.column() == 3 and role == QtCore.Qt.EditRole:
            self._data[index.row()].scalingparameters = value
            self.dataChanged.emit(self.index(index.row(), index.column()), self.index(index.row(), index.column()))
            return True
        elif index.column() == 1 and role == QtCore.Qt.EditRole:
            self._data[index.row()].backgroundname = value
            self.dataChanged.emit(self.index(index.row(), index.column()), self.index(index.row(), index.column()))
            return True
        elif index.column() == 2 and role == QtCore.Qt.EditRole:
            self._data[index.row()].scalingmethod = value
            self.dataChanged.emit(self.index(index.row(), index.column()), self.index(index.row(), self.columnCount()))
            return True
        return False

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        # edit this to your needs
        if index.column() == 0:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
        elif index.column() == 1:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled
        elif index.column() == 2:
            if self[index].backgroundname is not None:
                return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled
            else:
                return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable
        elif index.column() == 3:
            if self[index].backgroundname is not None and self[index].scalingmethod != 'None':
                return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEditable
            else:
                return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> typing.Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._columnnames[section]
        return None

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = None) -> QtCore.QModelIndex:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return self.createIndex(row, column, None)

    def removeRow(self, row: int, parent: QtCore.QModelIndex = None) -> bool:
        return self.removeRows(row, 1, parent)

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = None) -> bool:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        self.beginRemoveRows(QtCore.QModelIndex(), row, row + count)
        for i in reversed(range(row, row + count)):
            del self._data[i]
        self.endRemoveRows()
        return True

    def add(self, samplename: str):
        # edit this to your needs
        self.beginInsertRows(QtCore.QModelIndex(), self.rowCount(), self.rowCount() + 1)
        self._data.append(Subtraction(samplename))
        self.endInsertRows()

    def __contains__(self, item:str):
        return bool([d for d in self._data if d.samplename == item])

    def samplenames(self) -> typing.List[str]:
        return sorted(set([d.samplename for d in self._data]))

    def __getitem__(self, item):
        return self._data[item] if not isinstance(item, QtCore.QModelIndex) else self._data[item.row()]