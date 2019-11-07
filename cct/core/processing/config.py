from collections import namedtuple
from configparser import ConfigParser
from typing import Any

from PyQt5 import QtCore

ConfigItemType = namedtuple('ConfigItemType', ['type', 'default', 'description'])


class Config(QtCore.QObject):
    """This class represents the configuration of the SAXS data post-processing mechanism.

    Main functionalities:
        - the preferences are stored in a ConfigParser object: easy save/load
        - each preferene item has a default value and a type: type coercion will happen
        - distinct get and set methods for each type: int, float, bool, str
        - whenever a preference changes, a PyQt signal will be emitted.

    """
    configItemChanged = QtCore.pyqtSignal(str, str, object)
    cp:ConfigParser
    _configitems = {
        'io': {
            'badfsnsfile': ConfigItemType(str, 'badfsns.txt', 'Bad FSNs file'),
            'hdf5': ConfigItemType(str, 'processing.h5', 'Output HDF5 file'),
            'datadir': ConfigItemType(str, '', 'Data root directory'),
            'fsnranges': ConfigItemType(list, [], 'List of min-max FSN tuples'),
            'projectfilename': ConfigItemType(str, 'processing.cpt', 'Project settings file'),
        },
        'export': {
            'folder': ConfigItemType(str, 'processing', 'Export folder name'),
            'imageformat': ConfigItemType(str, 'png', 'File format for saving graphs'),
            'imageheightunits': ConfigItemType(str, 'inch', 'Image height units (inch or cm)'),
            'imagewidthunits': ConfigItemType(str, 'inch', 'Image width units (inch or cm)'),
            'onedimformat': ConfigItemType(str, 'ASCII (*.txt)', 'File format for saving 1D curves'),
            'imagedpi': ConfigItemType(str, '300', 'DPI resolution of saved graphs'),
            'imageheight': ConfigItemType(str, '4.8', 'Image height'),
            'imagewidth': ConfigItemType(str, '6.4', 'Image width'),
        },
        'headerview': {
            'fields': ConfigItemType(str, 'fsn;title;distance;date;temperature', 'Semicolon-separated list of header fields to show'),
        },
        'processing': {
            'errorpropagation': ConfigItemType(str, 'Conservative', 'Error propagation method'),
            'abscissaerrorpropagation': ConfigItemType(str, 'Conservative', 'Abscissa error propagation method'),
            'std_multiplier': ConfigItemType(float, 1.5, 'Multiplier for the standard deviation in the outlier tests'),
            'cmap_rad_nq': ConfigItemType(int, 200, 'number of q-points in the radial averaging for the cormap test'),
            'customqmax': ConfigItemType(float, 5, 'qmax for the custom q-range'),
            'customqmin': ConfigItemType(float, 0.1, 'qmin for the custom q-range'),
            'customqcount': ConfigItemType(int, 200, 'number of points in the custom q-range'),
            'logcorrelmatrix': ConfigItemType(bool, True, 'the correlation matrix must be calculated from the logarithmic intensities'),
            'sanitizecurves': ConfigItemType(bool, True, 'remove invalid points from the curves'),
            'customqlogscale': ConfigItemType(bool, True, 'use log-spaced points in the custom q-range'),
            'customq': ConfigItemType(bool, False, 'if the custom q-range is to be used'),
            'outliermethod': ConfigItemType(str, 'Interquartile Range', 'Method for finding outliers'),
        },
        'persample': { # parameters for the per-sample views
            'showmeancurve': ConfigItemType(bool, True, 'Show the average curve'),
            'showbadcurves': ConfigItemType(bool, True, 'Show all bad curves'),
            'showgoodcurves': ConfigItemType(bool, True, 'Show the good curves'),
            'logx': ConfigItemType(bool, True, 'Logarithmic X scale'),
            'logy': ConfigItemType(bool, True, 'Logarithmic Y scale'),
            'showmask': ConfigItemType(bool, True, 'Show the mask on the 2D image'),
            'showcenter': ConfigItemType(bool, True, 'Show the center on the 2D image'),
        },
        'curvecmp': { # parameters for the multi-sample views
            'legendformat': ConfigItemType(str, '{title} @{distance:.2f} mm', 'Format of the legend'),
            'plottype': ConfigItemType(str, 'log I vs. log q', 'Plot type'),
            'errorbars': ConfigItemType(bool, True, 'Show error bars'),
            'legend': ConfigItemType(bool, True, 'Show the legend'),
        }
    }

    def __init__(self):
        super().__init__()
        self.cp=ConfigParser()
        # initialize the configuration with the default values.
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
        """Load a configuration file. Already existing config items are either
        updated with new values or kept if there are no corresponding items in
        the config file."""
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

    def __getitem__(self, item:str) -> Any:
        """Get the value of a configuration item"""
        # first see if we can find the item in the description: must be unique
        sections = [section for section in self._configitems
                    if item in self._configitems[section]]
        if not sections:
            # nonexistent
            raise ValueError('Unknown configuration item: {}'.format(item))
        elif len(sections)>1:
            # must be unique
            raise ValueError('Non-unique configuration item: {}'.format(item))
        section = sections[0]

        # there must be such an item in the configparser structure.
        if self._configitems[section][item]['type'] is int:
            return self.getInt(section, item)
        elif self._configitems[section][item]['type'] is str:
            return self.getStr(section, item)
        elif self._configitems[section][item]['type'] is float:
            return self.getFloat(section, item)
        elif self._configitems[section][item]['type'] is bool:
            return self.getBool(section, item)
        else:
            raise ValueError('Invalid type: {}'.format(self._configitems[section][item]['type']))
