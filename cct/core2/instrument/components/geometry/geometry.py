import logging
from typing import Any, Optional, Final, List, Dict, Union

from PyQt5 import QtCore

from .choices import GeometryChoices
from .preset import GeometryPreset
from ..component import Component

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Geometry(QtCore.QAbstractItemModel, Component):
    """Describes current and possible geometries

    Geometry settings are stored as "presets", this class also presents a flat Qt item model of them. The first preset
    is special: it is always the *current* one, therefore it cannot be deleted, nor its name changed.

    The current values of the geometry settings are stored in config['geometry'], to be accessed there by the rest of
    the program. Additionally, there is an entry in config['geometry']['presets'] for each preset. Activating a preset
    simply means the copying of the values of the desired preset to the corresponding entries in config['geometry'].
    Changing geometry parameters does not update the stored preset values.

    """
    CURRENTPRESETNAME: Final[str] = '-- Current settings --'
    choices: GeometryChoices
    currentPresetChanged = QtCore.pyqtSignal(str, object)
    presets: Dict[str, GeometryPreset]
    currentpreset: GeometryPreset

    def __init__(self, **kwargs):
        self.presets = {}
        super().__init__(**kwargs)  # this implies self.loadFromConfig()
        if 'presets' not in self.config['geometry']:
            self.config['geometry']['presets'] = {}
        self.choices = GeometryChoices(config=self.config)

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self.presets)+1

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 1

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if index.row() == 0:
            # the first preset is special: it is the current preset. It cannot be renamed.
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        else:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable | \
                   QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if (role == QtCore.Qt.DisplayRole) or (role == QtCore.Qt.EditRole):
            if index.row() == 0:
                return self.CURRENTPRESETNAME
            else:
                return sorted(self.presets.keys())[index.row()-1]
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if index.row() == 0:
            raise RuntimeError('Cannot change the name of the current settings.')
        oldname = sorted(self.presets.keys())[index.row()-1]
        self.saveToConfig()
        return self.renamePreset(oldname, value)

    def renamePreset(self, oldname: str, newname: str) -> bool:
        if oldname == newname:
            return False
        if newname in self.presetNames():
            raise ValueError(f'Cannot rename preset "{oldname}" to an already existing name "{newname}"')
        self.beginResetModel()
        data = self.presets[oldname]
        self.presets[str(newname)] = data
        del self.presets[oldname]
        self.endResetModel()
        self.saveToConfig()
        return True

    def savePreset(self, name: str):
        """Save the current settings under a preset name"""
        self.presets[name] = self.currentpreset
        logger.info(f'Saved current geometry preset under name {name}')

    def addPreset(self, name: str, preset: Optional[GeometryPreset] = None) -> str:
        if name in self.presetNames():
            i = 1
            while f'{name}{i}' in self.presets:
                i += 1
            name = f'{name}{i}'
        if preset is None:
            preset = GeometryPreset(self.config)
        self.beginResetModel()
        self.presets[name] = preset
        self.endResetModel()
        logger.info(f'Added a new geometry preset {name}')
        self.saveToConfig()
        return name

    def removePreset(self, name: str):
        if name == self.CURRENTPRESETNAME:
            raise ValueError('Cannot remove current preset')
        if name not in self.presets:
            raise ValueError(f'Cannot remove nonexistent preset {name}')
        self.beginResetModel()
        del self.presets[name]
        self.endResetModel()
        self.saveToConfig()
        logger.info(f'Removed geometry preset {name}.')

    def onConfigChanged(self, path, value):
        if path[:2] == ('geometry', 'presets'):
            self.beginResetModel()
            self.endResetModel()
        logger.debug(path)

    def onCurrentPresetChanged(self, propertyname: str, newvalue: str):
        self.saveToConfig()
        self.currentPresetChanged.emit(propertyname, newvalue)

    def loadFromConfig(self):
        """Load presets and current state from the config"""
        if 'presets' not in self.config['geometry']:
            # initialize 'presets' dictionary if it does not exist.
            self.config['geometry']['presets'] = {}

        # construct the current preset from geometrical data
        currpres = GeometryPreset(
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
            self.config['geometry'].setdefault('description', 'Dummy preset'),
        )

        if hasattr(self, 'currentpreset'):
            # if we already have a current preset, disconnect from it and safely delete.
            self.currentpreset.changed.disconnect(self.onCurrentPresetChanged)
            self.currentpreset.deleteLater()
            del self.currentpreset
        # delete the presets list
        self.presets = {}
        # load the presets
        for name in self.config['geometry']['presets']:
            self.presets[name] = GeometryPreset.fromDict(self.config, self.config['geometry']['presets'][name])
            # check if this is the current preset
            if (self.presets[name] == currpres) and (not hasattr(self, 'currentpreset')):
                self.currentpreset = self.presets[name]
                self.currentpreset.changed.connect(self.onCurrentPresetChanged)
        if not hasattr(self, 'currentpreset'):
            # none of the presets was equal to the current settings
            self.currentpreset = currpres
            self.addPreset('Current', currpres)
            self.currentpreset.changed.connect(self.onCurrentPresetChanged)

    def saveToConfig(self):
        """Save the geometry values of the current preset to the config"""
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
        for preset in self.presets:
            self.config['geometry']['presets'][preset] = self.presets[preset].toDict()
        for name in self.config['geometry']['presets']:
            if name not in self.presets:
                del self.config['geometry']['presets']

    def setCurrentPreset(self, preset: Union[GeometryPreset, str]):
        if isinstance(preset, str):
            preset = self.presets[preset]
        assert isinstance(preset, GeometryPreset)
        self.currentpreset.changed.disconnect(self.onCurrentPresetChanged)
        self.currentpreset = preset
        self.currentpreset.changed.connect(self.onCurrentPresetChanged)
        dic = self.currentpreset.toDict()
        for key in dic:
            self.currentPresetChanged.emit(key, getattr(self.currentpreset, key))
        self.saveToConfig()

    def presetNames(self) -> List[str]:
        return [self.CURRENTPRESETNAME] + list(self.config['geometry']['presets'].keys())
