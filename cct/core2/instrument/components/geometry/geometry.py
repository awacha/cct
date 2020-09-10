import logging
from typing import Any, Optional

from PyQt5 import QtCore

from .choices import GeometryChoices
from .preset import GeometryPreset
from ..component import Component

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Geometry(QtCore.QAbstractItemModel, Component):
    currentpreset: Optional[GeometryPreset] = None
    choices: GeometryChoices
    currentPresetChanged = QtCore.pyqtSignal(str, object)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'presets' not in self.config['geometry']:
            self.config['geometry']['presets'] = {}
        self.choices = GeometryChoices(config=self.config)
        self.loadFromConfig()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self.config['geometry']['presets'])

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 1

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable | \
               QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if (role == QtCore.Qt.DisplayRole) or (role == QtCore.Qt.EditRole):
            return sorted(self.config['geometry']['presets'].keys())[index.row()]
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        oldname = sorted(self.config['geometry']['presets'].keys())[index.row()]
        self.config.inhibitAutoSave()
        self.beginResetModel()
        try:
            data = self.config['geometry']['presets'][oldname]
            self.config['geometry']['presets'][str(value)] = data
            del self.config['geometry']['presets'][oldname]
        finally:
            self.config.enableAutoSave()
        self.endResetModel()
        return True

    def loadPreset(self, name: str):
        self.setCurrentPreset(GeometryPreset.fromDict(self.config, self.config['geometry']['presets'][name].asdict()))
        logger.info(f'Loaded geometry preset {name}')

    def savePreset(self, name: str):
        self.config['geometry']['presets'][name] = self.currentpreset.toDict()
        logger.info(f'Saved current geometry preset under name {name}')

    def addPreset(self, name: str):
        if name in self.config['geometry']['presets']:
            i = 1
            while f'{name}{i}' in self.config['geometry']['presets']:
                i += 1
            name = f'{name}{i}'
        self.config['geometry']['presets'][name] = GeometryPreset(self.config).toDict()
        logger.info(f'Added a new geometry preset {name}')

    def removePreset(self, name: str):
        del self.config['geometry']['presets'][name]
        logger.info(f'Removed geometry preset {name}.')

    def onConfigChanged(self, path, value):
        if path[:2] == ('geometry', 'presets'):
            self.beginResetModel()
            self.endResetModel()
        logger.debug(path)

    def loadFromConfig(self):
        self.setCurrentPreset(GeometryPreset(
            self.config,
            self.config['geometry'].setdefault('l1_elements', []),
            self.config['geometry'].setdefault('l2_elements', []),
            self.config['geometry'].setdefault('pinhole_1', 0.0),
            self.config['geometry'].setdefault('pinhole_2', 0.0),
            self.config['geometry'].setdefault('pinhole_3', 0.0),
            self.config['geometry'].setdefault('flightpipes', []),
            self.config['geometry'].setdefault('beamstop', 0.0),
            (self.config['geometry'].setdefault('dist_sample_det', 0.0),
             self.config['geometry'].setdefault('dist_sample_det.err', 0.0)),
            (self.config['geometry'].setdefault('beamposx', 0.0),
             self.config['geometry'].setdefault('beamposx.err', 0.0)),
            (self.config['geometry'].setdefault('beamposy', 0.0),
             self.config['geometry'].setdefault('beamposy.err', 0.0)),
            self.config['geometry'].setdefault('mask', ''),
            self.config['geometry'].setdefault('description', ''),
        ))

    def onCurrentPresetChanged(self, propertyname: str, newvalue: str):
        self.saveToConfig()
        self.currentPresetChanged.emit(propertyname, newvalue)

    def saveToConfig(self):
        self.config.inhibitAutoSave()
        try:
            self.config['geometry']['l1_elements'] = tuple(self.currentpreset.l1_elements)
            self.config['geometry']['l2_elements'] = tuple(self.currentpreset.l2_elements)
            self.config['geometry']['flightpipes'] = tuple(self.currentpreset.flightpipes)
            self.config['geometry']['pinhole_1'] = self.currentpreset.pinhole1
            self.config['geometry']['pinhole_2'] = self.currentpreset.pinhole2
            self.config['geometry']['pinhole_3'] = self.currentpreset.pinhole3
            self.config['geometry']['beamstop'] = self.currentpreset.beamstop
            self.config['geometry']['dist_sample_det'] = self.currentpreset.sd[0]
            self.config['geometry']['dist_sample_det.err'] = self.currentpreset.sd[1]
            self.config['geometry']['beamposx'] = self.currentpreset.beamposx[0]
            self.config['geometry']['beamposx.err'] = self.currentpreset.beamposx[1]
            self.config['geometry']['beamposy'] = self.currentpreset.beamposy[0]
            self.config['geometry']['beamposy.err'] = self.currentpreset.beamposy[1]
            self.config['geometry']['mask'] = self.currentpreset.mask
            self.config['geometry']['description'] = self.currentpreset.description
        finally:
            self.config.enableAutoSave()

    def setCurrentPreset(self, preset: GeometryPreset):
        if self.currentpreset is not None:
            olddict = self.currentpreset.toDict()
            newdict = preset.toDict()
            changedkeys = [k for k in olddict if olddict[k] != newdict[k]]
            self.currentpreset.changed.disconnect(self.onCurrentPresetChanged)
        else:
            changedkeys = list(preset.toDict().keys())
        self.currentpreset = preset
        for k in changedkeys:
            self.currentPresetChanged.emit(k, getattr(self.currentpreset, k))
        self.currentpreset.changed.connect(self.onCurrentPresetChanged)

