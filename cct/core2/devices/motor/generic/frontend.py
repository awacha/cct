import logging
import os
from typing import Tuple, Any, List, Optional

import h5py
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from ...device.frontend import DeviceFrontend, DeviceType

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MotorController(DeviceFrontend):
    Naxes: int
    moveStarted = Signal(int, float)
    moveEnded = Signal(int, bool, float)
    devicetype = DeviceType.MotorController
    devicename = ''

    def __init__(self, name: str, host: str, port: int):
        self._backendkwargs = {'positionfile': os.path.join('config', f'{name}.motorpos')}

        super().__init__(name, host, port)
        self.Naxes = self.backendclass.Naxes

    def moveTo(self, motor: int, position: float):
        if position < self[f'softleft${motor}'] or position > self[f'softright${motor}']:
            raise self.DeviceError(f'Cannot move motor {motor}: position outside limits.')
        if self[f'moving${motor}']:
            raise self.DeviceError(f'Cannot move motor {motor}: already in motion.')
        self.issueCommand('moveto', motor, position)

    def moveRel(self, motor: int, position: float):
#        logger.debug(f'Moving motor {motor} relatively by {position}')
        if (self[f'actualposition${motor}'] + position < self[f'softleft${motor}']) or \
                (self[f'actualposition${motor}'] + position > self[f'softright${motor}']):
            #logger.debug('Position outside limits!')
            raise self.DeviceError(f'Cannot move motor {motor}: position outside limits.')
        if self[f'moving${motor}']:
            #logger.debug('Motor is moving!')
            raise self.DeviceError(f'Cannot move motor {motor}: already in motion.')
        self.issueCommand('moverel', motor, position)
        #logger.debug(f'Moverel issued successfully')

    def stopMotor(self, motor: int):
        self.issueCommand('stop', motor)

    def setPosition(self, motor: int, position: float):
        self.issueCommand('setposition', motor, position)

    def setLimits(self, motor: int, left: float, right: float):
        self.issueCommand('setlimits', motor, (left, right))

    def getLimits(self, motor: int) -> Tuple[float, float]:
        return self[f'softleft${motor}'], self[f'softright${motor}']

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        row = [i for i, (name, isperaxis) in enumerate(self._variablebasenames()) if name == variablename.split('$')[0]][0]
        self.dataChanged.emit(
            self.index(row, 0, QtCore.QModelIndex()),
            self.index(row, self.columnCount(), QtCore.QModelIndex()),
        )
        if variablename == '__status__':
            self.stateChanged.emit(newvalue)
        varbasename = variablename.split('$')[0]
        if varbasename == 'moving':
            axis = int(variablename.split('$')[-1])
            try:
                if newvalue:
                    self.moveStarted.emit(axis, self[f'movestartposition${axis}'])
                else:
                    self.moveEnded.emit(axis, self[f'lastmovewassuccessful${axis}'], self[f'actualposition${axis}'])
            except self.DeviceError:
                # this error is normal if not all variables have been updated.
                if self.ready:
                    raise

    def _variablebasenames(self) -> List[Tuple[str, bool]]:
        by_axis_variables = sorted({v.name.split('$')[0] for v in self._variables if '$' in v.name})
        global_variables = sorted([v.name for v in self._variables if '$' not in v.name])
        return [(v, False) for v in global_variables] + \
               [(v, True) for v in by_axis_variables]

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._variablebasenames())

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 1+self.Naxes

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        basename, isperaxis = self._variablebasenames()[index.row()]
        if index.column() >= 1:
            var = self.getVariable(f'{basename}${index.column() - 1}' if isperaxis else basename)
        else:
            var = self.getVariable(f'{basename}$0' if isperaxis else basename)
        if (index.column() == 0) and (role == QtCore.Qt.DisplayRole):
            return basename
        elif (index.column() >= 1) and (role == QtCore.Qt.DisplayRole):
            return f'{var.value}' if isperaxis or index.column() == 1 else '--'
        else:
            return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return (['Variable'] + [f'Motor #{i}' for i in range(self.Naxes)])[section]
        else:
            return None

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        """"""
        # the NeXus specification does not have a base class for multi-axis motor controllers (as of June 2022)
        return grp
