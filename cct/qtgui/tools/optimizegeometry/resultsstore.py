from typing import List

from PyQt5 import QtCore

from .pinholeconfiguration import PinholeConfiguration


class PinholeConfigurationStore(QtCore.QAbstractItemModel):
    def __init__(self, *args):
        super().__init__(*args)
        self._list = []

    def parent(self, parent: QtCore.QModelIndex = None):
        return QtCore.QModelIndex()

    def columnCount(self, parent=None, *args, **kwargs):
        return 18

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._list)

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable

    def index(self, row, column, parent=None, *args, **kwargs):
        return self.createIndex(row, column, None)

    def data(self, index: QtCore.QModelIndex, role=None):
        if role == QtCore.Qt.DisplayRole:
            pc = self._list[index.row()]
            assert isinstance(pc, PinholeConfiguration)
            if index.column() == 0:
                return ', '.join([str(x) for x in pc.l1_elements])
            elif index.column() == 1:
                return ', '.join([str(x) for x in pc.l2_elements])
            elif index.column() == 2:
                return pc.D1
            elif index.column() == 3:
                return pc.D2
            elif index.column() == 4:
                return pc.D3
            elif index.column() == 5:
                return self.suggestPinholeSize(pc)
            elif index.column() == 6:
                return pc.intensity
            elif index.column() == 7:
                return pc.Dsample
            elif index.column() == 8:
                return pc.rbs_parasitic1(self.suggestPinholeSize(pc)*0.5e-3)*2
            elif index.column() == 9:
                return pc.l1
            elif index.column() == 10:
                return pc.l2
            elif index.column() == 11:
                return pc.sd
            elif index.column() == 12:
                return pc.alpha * 1000
            elif index.column() == 13:
                return pc.qmin
            elif index.column() == 14:
                return pc.dmax
            elif index.column() == 15:
                return 1 / pc.qmin
            elif index.column() == 16:
                return pc.dspheremax
            elif index.column() == 17:
                return pc.dominant_constraint
            else:
                return None

    def addConfiguration(self, phc: PinholeConfiguration):
        self.beginInsertRows(QtCore.QModelIndex(), self.rowCount(), self.rowCount() + 1)
        self._list.append(phc)
        self.endInsertRows()

    def addConfigurations(self, phcs: List[PinholeConfiguration]):
        self.beginInsertRows(QtCore.QModelIndex(), self.rowCount(), self.rowCount() + len(phcs))
        self._list.extend(phcs)
        self.endInsertRows()

    def getConfiguration(self, index: int) -> PinholeConfiguration:
        return self._list[index]

    def clear(self):
        self.beginResetModel()
        self._list = []
        self.endResetModel()

    def headerData(self, i, orientation, role=None):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            # headertext = ['<i>l<sub>1</sub></i> parts (mm)',
            #         '<i>l<sub>2</sub></i> parts (mm)',
            #         '1<sup>st</sup> aperture (\u03bcm)',
            #         '2<sup>nd</sup> aperture (\u03bcm)',
            #         '3<sup>rd</sup> aperture (\u03bcm)',
            #         'Intensity (\u03bcm<sup>4</sup>mm<sup>-2</sup>)',
            #         'Sample size (mm)',
            #         'Beamstop size (mm)',
            #         '<i>l<sub>1</sub></i> (mm)',
            #         '<i>l<sub>2</sub></i> (mm)',
            #         'S-D distance (mm)',
            #         'Divergence (mrad)',
            #         'Smallest <i>q</i> (nm<sup>-1</sup>)',
            #         'Largest <i>d</i> (mm)',
            #         'Largest <i>R<sub>g</sub></i> (mm)',
            #         'Largest sphere size (nm)',
            #         'Dominant constraint'][i]
            headertext = ['L1 parts (mm)',
                          'L2 parts (mm)',
                          '1st aperture (\u03bcm)',
                          '2nd aperture (\u03bcm)',
                          '3rd aperture (\u03bcm)',
                          'Suggested 3rd aperture (\u03bcm)',
                          'Intensity (\u03bcm^4/mm^2)',
                          'Sample size (mm)',
                          'Beamstop size (mm)',
                          'L1 (mm)',
                          'L2 (mm)',
                          'S-D distance (mm)',
                          'Divergence (mrad)',
                          'Smallest q (1/nm)',
                          'Largest d (nm)',
                          'Largest Rg (nm)',
                          'Largest sphere size (nm)',
                          'Dominant constraint'][i]
            return headertext
        else:
            return None

    def setPinholeSizes(self, sizes=List[float]) -> None:
        self._pinholesizes = sizes

    def suggestPinholeSize(self, pc:PinholeConfiguration) -> float:
        return sorted([p for p in self._pinholesizes if pc.D3<p], key=lambda x:x-pc.D3)[0]

