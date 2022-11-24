import enum
import logging
from typing import List, Any, Optional

from PyQt5 import QtCore

from ....config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ComponentType(enum.Enum):
    Pinhole = 'pinhole'
    Beamstop = 'beamstop'
    PinholeSpacer = 'spacer'
    FlightPipe = 'flightpipe'


class GeometryChoices(QtCore.QAbstractItemModel):
    """Model to store all possible choices for beamstop, flight pipes, pinholes (in 3 stages) and inter-pinhole spacers.

    The tree hierarchy is like:

    - beamstops
        - 2.6
        - 4
        - ...
    - flightpipes
        - 160
        - 280
        - 1038
        - 1200
        - ...
    - pinholes
        - stage 1
            - 300
            - 600
            - ...
        - stage 2
            - 100
            - 300
            - ...
        - stage 3
            - 750
            - 1200
            - ...
    - spacers
        - 65
        - 65
        - 100
        - 100
        - 100
        - 200
        - ...

    """

    class IndexObject:
        """Class for indexing the choices tree model"""
        def __init__(self, componenttype: ComponentType, index1: Optional[int] = None, index2: Optional[int] = None):
            #            logger.debug(f'Creating indexObject {componenttype=} {index1=} {index=}')
            self.componenttype = componenttype
            self.index1 = index1
            self.index2 = index2
            assert isinstance(self.componenttype, ComponentType)

        @property
        def level(self) -> int:
            if self.index1 is None and self.index2 is None:
                return 1
            elif self.index1 is not None and self.index2 is None:
                return 2
            elif self.index1 is not None and self.index2 is not None:
                return 3
            else:
                raise ValueError(self)

        def __eq__(self, other) -> bool:
            assert isinstance(other, type(self))
            return ((self.componenttype == other.componenttype)
                    and (self.index1 == other.index1)
                    and (self.index2 == other.index2))

        def __ne__(self, other) -> bool:
            return not self.__eq__(other)

        def __str__(self):
            return f'IndexObject({self.componenttype.value=}, {self.index1=}, {self.index2=} {self.level=})'

    pinhole1: List[float]  # list of pinhole apertures in the 1st stage
    pinhole2: List[float]  # list of pinhole apertures in the 2nd stage
    pinhole3: List[float]  # list of pinhole apertures in the 3rd stage
    beamstop: List[float]  # list of possible beam stop diameters
    spacers: List[float]  # list of the lengths of spacers that can be put between pinhole stages. May be repeated
    flightpipes: List[float]  # list of flight pipe lengths to be put between the sample chamber and the beamstop stage
    _indexobjects: List[IndexObject]  # cache of index objects, to avoid garbage collecting them
    config: Config  # the configuration object

    def __init__(self, **kwargs):
        self.pinhole1 = []
        self.pinhole2 = []
        self.pinhole3 = []
        self.beamstop = []
        self.spacers = []
        self.flightpipes = []
        self._indexobjects = []
        self.config = kwargs.pop('config')
        super().__init__(**kwargs)
        self.loadFromConfig()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        ip = parent.internalPointer() if parent.isValid() else None
        assert isinstance(ip, self.IndexObject) or ip is None
        if not parent.isValid():  # root level
            return 4  # pinholes, spacers, beamstops, pipes
        elif ip.level == 1:
            if ip.componenttype == ComponentType.Pinhole:  # the pinhole branch is one level deeper
                return 3
            elif ip.componenttype == ComponentType.Beamstop:
                return len(self.beamstop)
            elif ip.componenttype == ComponentType.PinholeSpacer:
                return len(self.spacers)
            elif ip.componenttype == ComponentType.FlightPipe:
                return len(self.flightpipes)
        elif ip.level == 2:
            if ip.componenttype == ComponentType.Pinhole:
                if ip.index1 == 0:
                    return len(self.pinhole1)
                elif ip.index1 == 1:
                    return len(self.pinhole2)
                elif ip.index1 == 2:
                    return len(self.pinhole3)
                else:
                    raise ValueError(ip.index1)
            else:
                return 0
        elif ip.level == 3:
            assert ip.componenttype == ComponentType.Pinhole
            return 0
        else:
            assert False

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 1

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not child.isValid():
            return QtCore.QModelIndex()
        ip = child.internalPointer()
        assert isinstance(ip, self.IndexObject)
        if ip.level == 1:
            return QtCore.QModelIndex()
        elif ip.level == 2:
            if ip.componenttype == ComponentType.Beamstop:
                return self.index(0, 0, QtCore.QModelIndex())
            elif ip.componenttype == ComponentType.FlightPipe:
                return self.index(1, 0, QtCore.QModelIndex())
            elif ip.componenttype == ComponentType.Pinhole:
                return self.index(2, 0, QtCore.QModelIndex())
            elif ip.componenttype == ComponentType.PinholeSpacer:
                return self.index(3, 0, QtCore.QModelIndex())
            else:
                assert False
        elif ip.level == 3:
            if ip.componenttype == ComponentType.Pinhole:
                return self.createIndex(ip.index1, 0, self.IndexObject(ComponentType.Pinhole, ip.index1, None))
            else:
                assert False
        else:
            assert False

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        if not parent.isValid():
            return self.createIndex(row, column, self.IndexObject(
                [ComponentType.Beamstop, ComponentType.FlightPipe, ComponentType.Pinhole, ComponentType.PinholeSpacer][
                    row], None, None))
        ip = parent.internalPointer()
        assert isinstance(ip, self.IndexObject)
        if ip.level == 1:
            # we need to construct an index for a second-level item.
            return self.createIndex(row, column, self.IndexObject(ip.componenttype, row, None))
        elif (ip.level == 2) and ip.componenttype == ComponentType.Pinhole:
            return self.createIndex(row, column, self.IndexObject(ip.componenttype, ip.index1, row))
        else:
            logger.error(ip)
            assert False

    def createIndex(self, row: int, column: int, object: Any = ...) -> QtCore.QModelIndex:
        try:
            obj = [x for x in self._indexobjects if x == object][0]
        except IndexError:
            self._indexobjects.append(object)
            obj = object
        return super().createIndex(row, column, obj)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if index.isValid():
            ip = index.internalPointer()
            assert isinstance(ip, self.IndexObject)
            if (ip.level == 1) or ((ip.level == 2) and (ip.componenttype == ComponentType.Pinhole)):
                return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
            else:
                return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsEditable
        else:
            return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if not index.isValid():
            return False
        ip = index.internalPointer()
        assert isinstance(ip, self.IndexObject)
        if (role == QtCore.Qt.ItemDataRole.DisplayRole) or (role == QtCore.Qt.ItemDataRole.EditRole):
            if ip.level == 1:
                return ip.componenttype.value.capitalize()
            elif (ip.level == 2) and (ip.componenttype == ComponentType.Pinhole):
                return f'Stage {index.row() + 1}'
            elif (ip.level == 2) and (ip.componenttype == ComponentType.FlightPipe):
                return f'{self.flightpipes[index.row()]:.2f}' if role == QtCore.Qt.ItemDataRole.DisplayRole else self.flightpipes[index.row()]
            elif (ip.level == 2) and (ip.componenttype == ComponentType.Beamstop):
                return f'{self.beamstop[index.row()]:.2f}' if role == QtCore.Qt.ItemDataRole.DisplayRole else self.beamstop[index.row()]
            elif (ip.level == 2) and (ip.componenttype == ComponentType.PinholeSpacer):
                return f'{self.spacers[index.row()]:.2f}' if role == QtCore.Qt.ItemDataRole.DisplayRole else self.spacers[index.row()]
            elif (ip.level == 3) and (ip.componenttype == ComponentType.Pinhole):
                lis = [self.pinhole1, self.pinhole2, self.pinhole3][ip.index1]
                return f'{lis[index.row()]:.2f}' if role == QtCore.Qt.ItemDataRole.DisplayRole else lis[index.row()]
            else:
                assert False
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        logger.debug('setData')
        if not index.isValid():
            return False
        ip = index.internalPointer()
        assert isinstance(ip, self.IndexObject)
        if (ip.level == 2) and (ip.componenttype == ComponentType.PinholeSpacer):
            self.spacers[index.row()] = float(value)
            self.spacers.sort()
        elif (ip.level == 2) and (ip.componenttype == ComponentType.Beamstop):
            self.beamstop[index.row()] = float(value)
            self.beamstop.sort()
        elif (ip.level == 2) and (ip.componenttype == ComponentType.FlightPipe):
            self.flightpipes[index.row()] = float(value)
            self.flightpipes.sort()
        elif (ip.level == 3) and (ip.componenttype == ComponentType.Pinhole):
            lis = [self.pinhole1, self.pinhole2, self.pinhole3][ip.index1]
            lis[index.row()] = float(value)
            lis.sort()
        self.dataChanged.emit(self.index(0, 0, index.parent()),
                              self.index(self.rowCount(index.parent()), self.columnCount(index.parent()), index.parent()))
        self.saveToConfig()
        return True

    def addPinhole(self, stage: int, aperture: float):
        """Add a new pinhole diameter, maintaining increasing order

        After the pinhole is added, the configuration is saved

        :param stage: which stage should it be added (indexing from 0)
        :type stage: integer between 0 and 2
        :param aperture: pinhole diameter
        :type aperture: float
        """
        lis = [self.pinhole1, self.pinhole2, self.pinhole3][stage]
        row = max([i for i, l in enumerate(lis) if l < aperture] + [-1]) + 1
        self.beginInsertRows(self.createIndex(stage, 0, self.IndexObject(ComponentType.Pinhole, stage, None)), row, row)
        lis.insert(row, aperture)
        self.endInsertRows()
        self.saveToConfig()

    def addSpacer(self, length: float):
        """Add a new spacer, maintaining increasing order

        After the spacer length is added, the configuration is saved

        :param length: length of the spacer in mm
        :type length: float
        """
        row = max([i for i, l in enumerate(self.spacers) if l < length] + [-1]) + 1
        self.beginInsertRows(self.index(3, 0, QtCore.QModelIndex()), row, row)
        self.spacers.insert(row, length)
        self.endInsertRows()
        self.saveToConfig()

    def addFlightPipe(self, length: float):
        row = max([i for i, l in enumerate(self.spacers) if l < length] + [-1]) + 1
        self.beginInsertRows(self.index(1, 0, QtCore.QModelIndex()), row, row)
        self.flightpipes.insert(row, length)
        self.endInsertRows()
        self.saveToConfig()

    def addBeamstop(self, diameter: float):
        row = max([i for i, l in enumerate(self.spacers) if l < diameter] + [-1]) + 1
        self.beginInsertRows(self.index(0, 0, QtCore.QModelIndex()), row, row)
        self.beamstop.insert(row, diameter)
        self.endInsertRows()
        self.saveToConfig()

    def loadFromConfig(self):
        self.beginResetModel()
        try:
            self.pinhole1 = self.config['geometry']['choices']['pinholes'][1]
        except KeyError:
            pass
        try:
            self.pinhole2 = self.config['geometry']['choices']['pinholes'][2]
        except KeyError:
            pass
        try:
            self.pinhole3 = self.config['geometry']['choices']['pinholes'][3]
        except KeyError:
            pass
        try:
            self.beamstop = self.config['geometry']['choices']['beamstops']
        except KeyError:
            pass
        try:
            self.spacers = self.config['geometry']['choices']['spacers']
        except KeyError:
            pass
        try:
            self.flightpipes = self.config['geometry']['choices']['flightpipes']
        except KeyError:
            pass
        self.endResetModel()

    def saveToConfig(self):
        """Save the current state to the configuration dictionary"""
        if 'geometry' not in self.config:
            self.config['geometry'] = {}
        if 'choices' not in self.config:
            self.config['geometry']['choices'] = {}
        for listname in ['pinholes', 'spacers', 'flightpipes', 'beamstops']:
            try:
                del self.config['geometry']['choices'][listname]
            except KeyError:
                pass
        self.config['geometry']['choices']['pinholes'] = {1: self.pinhole1, 2: self.pinhole2, 3: self.pinhole3}
        self.config['geometry']['choices']['spacers'] = self.spacers
        self.config['geometry']['choices']['flightpipes'] = self.flightpipes
        self.config['geometry']['choices']['beamstops'] = self.beamstop

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        if not parent.isValid():
            raise ValueError('Cannot remove top-level item')
        ip = parent.internalPointer()
        assert isinstance(ip, self.IndexObject)
        if (ip.componenttype == ComponentType.Beamstop) and (ip.level == 1):
            self.beginRemoveRows(parent, row, row)
            del self.beamstop[row]
            self.endRemoveRows()
        elif (ip.componenttype == ComponentType.FlightPipe) and (ip.level == 1):
            self.beginRemoveRows(parent, row, row)
            del self.flightpipes[row]
            self.endRemoveRows()
        elif (ip.componenttype == ComponentType.PinholeSpacer) and (ip.level == 1):
            self.beginRemoveRows(parent, row, row)
            del self.spacers[row]
            self.endRemoveRows()
        elif (ip.componenttype == ComponentType.Pinhole) and (ip.level == 2) and (ip.index1 == 0):
            self.beginRemoveRows(parent, row, row)
            del self.pinhole1[row]
            self.endRemoveRows()
        elif (ip.componenttype == ComponentType.Pinhole) and (ip.level == 2) and (ip.index1 == 1):
            self.beginRemoveRows(parent, row, row)
            del self.pinhole2[row]
            self.endRemoveRows()
        elif (ip.componenttype == ComponentType.Pinhole) and (ip.level == 2) and (ip.index1 == 2):
            self.beginRemoveRows(parent, row, row)
            del self.pinhole3[row]
            self.endRemoveRows()
        else:
            logger.error(ip)
            raise ValueError('Cannot remove this item')
        self.saveToConfig()
