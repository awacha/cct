from configparser import ConfigParser
from typing import Any

from PyQt5 import QtCore


class Config(QtCore.QObject):
    configItemChanged = QtCore.pyqtSignal(str, str, object)
    cp:ConfigParser
    _configitems = {
        'io': {
            'badfsnsfile': {'type': str, 'default':'badfsns.txt', },
            'hdf5': {'type': str, 'default': 'processing.h5', },
            'datadir': {'type': str, 'default': '', },
            'fsnranges': {'type': list, 'default': '', },
            'projectfilename': {'type': str, 'default': 'processing.cpt', },
        },
        'export': {
            'folder': {'type': str, 'default': 'processing', },
            'imageformat': {'type': str, 'default': 'png', },
            'imageheightunits': {'type': str, 'default': 'inch', },
            'imagewidthunits': {'type': str, 'default': 'inch', },
            'onedimformat': {'type': str, 'default': 'ASCII (*.txt)', },
            'imagedpi': {'type': str, 'default': '300', },
            'imageheight': {'type': str, 'default': '4.8', },
            'imagewidth': {'type': str, 'default': '6.4', },
        },
        'headerview': {
            'fields': {'type': str, 'default': 'fsn;title;distance;date;temperature', },
        },
        'processing': {
            'errorpropagation': {'type': str, 'default': 'Conservative', },
            'abscissaerrorpropagation': {'type': str, 'default': 'Conservative', },
            'std_multiplier': {'type': float, 'default': 1.5, },
            'cmap_rad_nq': {'type':int, 'default':200, },
            'customqmax': {'type': float, 'default': 5, },
            'customqmin': {'type': float, 'default': 0.1, },
            'customqcount': {'type': int, 'default': 200, },
            'logcorrelmatrix': {'type': bool, 'default': True, },
            'sanitizecurves': {'type': bool, 'default': True, },
            'customqlogscale': {'type': bool, 'default': True, },
            'customq': {'type': bool, 'default': False, },
            'corrmatmethod': {'type': str, 'default': 'Interquartile Range', },
        },
        'persample': {
            'showmeancurve': {'type': bool, 'default': True, },
            'showbadcurves': {'type': bool, 'default': True, },
            'showgoodcurves': {'type': bool, 'default': True, },
            'logx': {'type': bool, 'default': True, },
            'logy': {'type': bool, 'default': True, },
            'showmask': {'type': bool, 'default': True, },
            'showcenter': {'type': bool, 'default': True, },
        },
        'curvecmp': {
            'legendformat': {'type': str, 'default': '{title} @{distance:.2f} mm', },
            'plottype': {'type': str, 'default': 'log I vs. log q', },
            'errorbars': {'type': bool, 'default': True, },
            'legend': {'type': bool, 'default': True, },
        }
    }

    def __init__(self):
        super().__init__()
        self.cp=ConfigParser()
        for section in self._configitems:
            for key in self._configitems[section]:
                type_=self._configitems[section][key]['type']
                value=self._configitems[section][key]['default']
                if type_ is bool:
                    self.setBool(section, key, bool(value))
                elif type_ is int:
                    self.setInt(section, key, int(value))
                elif type_ is float:
                    self.setFloat(section, key, float(value))
                elif type_ is str:
                    self.setKey(section, key, value)
                else:
                    raise TypeError(type_)

    def load(self, filename:str):
        self.cp.read([filename])
        for section in self.cp:
            for key in self.cp[section]:
                value = self._configitems[section][key]['type'](self.cp[section][key])
                self.configItemChanged.emit(section, key, value)

    def save(self, filename:str):
        with open(filename, 'wt') as f:
            self.cp.write(f)

    def setKey(self, section:str, key:str, value:Any):
        self.cp[section][key]=str(value)
        self.configItemChanged.emit(section, key, value)

    def getStr(self, section:str, key:str) -> str:
        return str(self.cp[section][key])

    def getFloat(self, section:str, key:str) -> float:
        return float(self.cp[section][key])

    def getInt(self, section:str, key:str) -> int:
        return int(self.cp[section][key])

    def getBool(self, section:str, key:str) -> bool:
        if self.cp[section][key].upper() in ['YES', 'TRUE', '1', 'OK', 'ON']:
            return True
        elif self.cp[section][key].upper() in ['NO', 'FALSE', '0', 'OFF']:
            return False
        else:
            raise ValueError('Invalid bool string: {}'.format(self.cp[section][key]))

    def setBool(self, section:str, key:str, value:bool):
        return self.setKey(section, key, 'True' if value else 'False')

    def setInt(self, section:str, key:str, value:int):
        return self.setKey(section, key, value)

    def setFloat(self, section:str, key:str, value:float):
        return self.setKey(section, key, '{:.20g}'.format(value))


