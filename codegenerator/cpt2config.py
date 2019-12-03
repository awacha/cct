"""Auto-generate the Config class for the processing tool"""
import os
from collections import namedtuple

ConfigItem = namedtuple('ConfigItem', ['typename', 'default', 'description', 'domain'])
ConfigType = namedtuple('ConfigType', ['reader', 'writer', 'typehint'])

configtypes = {'str': ConfigType('str', 'str', 'str'),
               'int': ConfigType('int', 'str', 'int'),
               'float': ConfigType('float', '(lambda x: "{:.20g}".format(x))', 'float'),
               'datetime': ConfigType('dateutil.parser.parse', 'str', 'datetime.datetime'),
               'bool': ConfigType('self._readBool', 'self._writeBool', 'bool'),
               'fsnranges': ConfigType('self._readFSNRanges', 'self._writeFSNRanges', 'List[Tuple[int, int]]'),
               'semicolonseparatedlistofstrings': ConfigType('self._readSemicolonSepStrList',
                                                             'self._writeSemicolonSepStrList', 'List[str]'), }

configitems = {
    'io': {
        'badfsnsfile': ConfigItem('str', 'badfsns.txt', 'Bad FSNs file', None),
        'hdf5': ConfigItem('str', 'processing.h5', 'Output HDF5 file', None),
        'datadir': ConfigItem('str', '', 'Data root directory', None),
        'fsnranges': ConfigItem('fsnranges', [], 'List of min-max FSN tuples', None),
        'projectfilename': ConfigItem('str', 'processing.cpt', 'Project settings file', None),
    },
    'export': {
        'folder': ConfigItem('str', 'processing', 'Export folder name', None),
        'imageformat': ConfigItem('str', 'png', 'File format for saving graphs',
                                  ['eps', 'jpeg', 'pdf', 'png', 'svg', 'tiff']),
        'imageheightunits': ConfigItem('str', 'inch', 'Image height units (inch or cm)',
                                       ['cm', 'mm', 'inch']),
        'imagewidthunits': ConfigItem('str', 'inch', 'Image width units (inch or cm)',
                                      ['cm', 'mm', 'inch']),
        'onedimformat': ConfigItem('str', 'ASCII (*.txt)', 'File format for saving 1D curves',
                                   ['ASCII (*.txt)', 'ASCII (*.dat)', 'ATSAS (*.dat)', 'RSR (*.rsr)',
                                    'Excel 2007- (*.xlsx)', 'PDH (*.pdh)']),
        'twodimformat': ConfigItem('str', 'Numpy (*.npz)', 'File format for saving matrices',
                                   ['ASCII (*.txt)', 'Gzip-ped ASCII (*.txt.gz)', 'Matlab(TM) (*.mat)',
                                    'Numpy (*.npz)']),
        'imagedpi': ConfigItem('int', '300', 'DPI resolution of saved graphs', ('0', '9999999')),
        'imageheight': ConfigItem('float', '4.8', 'Image height', ('0', '99999999')),
        'imagewidth': ConfigItem('float', '6.4', 'Image width', ('0', '99999999')),
    },
    'headerview': {
        'fields': ConfigItem('semicolonseparatedlistofstrings', 'fsn;title;distance;date;temperature',
                             'Semicolon-separated list of header fields to show', None),
    },
    'processing': {
        'maxjobs': ConfigItem('int', '4', 'Maximal number of concurrent processing jobs', ('1', '99999')),
        'errorpropagation': ConfigItem('str', 'Conservative', 'Error propagation method',
                                       ['Weighted', 'Average', 'Squared (Gaussian)', 'Conservative']),
        'abscissaerrorpropagation': ConfigItem('str', 'Conservative', 'Abscissa error propagation method',
                                               ['Weighted', 'Average', 'Squared (Gaussian)', 'Conservative']),
        'std_multiplier': ConfigItem('float', '1.5',
                                     'Multiplier for the standard deviation in the outlier tests',
                                     ('0', '99999')),
        'cmap_rad_nq': ConfigItem('int', '200',
                                  'number of q-points in the radial averaging for the cormap test',
                                  ('2', '9999999')),
        'customqmax': ConfigItem('float', '5', 'qmax for the custom q-range',
                                 ('0', '9999999')),
        'customqmin': ConfigItem('float', '0.1', 'qmin for the custom q-range', ('0', '9999999')),
        'customqcount': ConfigItem('int', '200', 'number of points in the custom q-range',
                                   ('2', '9999999')),
        'logcorrelmatrix': ConfigItem(
            'bool', 'True', 'the correlation matrix must be calculated from the logarithmic intensities',
            None),
        'sanitizecurves': ConfigItem('bool', 'True', 'remove invalid points from the curves', None),
        'customqlogscale': ConfigItem('bool', 'True', 'use log-spaced points in the custom q-range', None),
        'autoq': ConfigItem('bool', 'True', 'if q-range is to be auto-determined', None),
        'outliermethod': ConfigItem('str', 'Interquartile Range', 'Method for finding outliers',
                                    ['Z-score', 'Modified Z-score', 'Interquartile Range']),
    },
    'twodim': {  # parameters for the 2D images
        'showmask': ConfigItem('bool', 'True', 'Show the mask on the 2D image', None),
        'showcenter': ConfigItem('bool', 'True', 'Show the center on the 2D image', None),
        'showcolorbar': ConfigItem('bool', 'True', 'Show the color bar on the 2D image', None),
        'colorpalette': ConfigItem('str', 'viridis', 'Color bar for the 2D images', None),
        'twodimaxisvalues': ConfigItem('str', 'q', 'Values to display on the axes of 2D images',
                                       ['q', 'pixel', 'radius']),
    },
    'onedim': {  # parameters for the curve graphs
        'showmeancurve': ConfigItem('bool', 'True', 'Show the average curve', None),
        'showbadcurves': ConfigItem('bool', 'True', 'Show all bad curves', None),
        'showgoodcurves': ConfigItem('bool', 'True', 'Show the good curves', None),
        'showlines': ConfigItem('bool', 'True', 'Show lines in curves', None),
        'showgrid': ConfigItem('bool', 'True', 'Show grid lines in curves', None),
        'symbolstype': ConfigItem('str', 'Filled symbols', 'Symbol type in curves',
                                  ['No symbols', 'Filled symbols', 'Empty symbols']),
        'logx': ConfigItem('bool', 'True', 'Logarithmic X scale', None),
        'logy': ConfigItem('bool', 'True', 'Logarithmic Y scale', None),
        'legendformat': ConfigItem('str', '{title} @{distance:.2f} mm', 'Format of the legend', None),
        'plottype': ConfigItem('str', 'log I vs. log q', 'Plot type',
                               ['log I vs. log q', 'I vs. log q', 'log I vs. q', 'I vs. q', 'log I vs. q^2',
                                'I*q^2 vs. q', 'I*q^4 vs. q']),
        'showerrorbars': ConfigItem('bool', 'True', 'Show error bars', None),
        'showlegend': ConfigItem('bool', 'True', 'Show the legend', None),
    },
    'cmatplot': {
        'cmatpalette': ConfigItem('str', 'coolwarm', 'Color map for the correlation matrix plots', None),
    }
}


def writeCode():
    with open(os.path.join('cct', 'processinggui', 'config.py'), 'wt') as f:
        f.write('# Auto-generated file, do not edit\n'
                'from PyQt5 import QtCore\n'
                'from typing import List, Tuple\n'
                'from configparser import ConfigParser, DuplicateSectionError\n'
                '# noinspection PyUnresolvedReferences\n'
                'import dateutil.parser\n'
                '# noinspection PyUnresolvedReferences\n'
                'import datetime\n'
                'import appdirs\n'
                'import re\n'
                'import os\n'
                '\n\n'
                'class Config(QtCore.QObject):\n'
                '    """This class represents the configuration of the SAXS data post-processing mechanism.\n\n'
                '    Main functionalities:\n'
                '    - the preferences are stored in a ConfigParser object: easy save/load\n'
                '    - each preferene item has a default value and a type: type coercion will happen\n'
                '    - distinct get and set methods for each type: int, float, bool, str\n'
                '    - whenever a preference changes, a PyQt signal will be emitted.\n'
                '    """\n'
                '    configItemChanged = QtCore.pyqtSignal(str, str, object)\n'
                '    _configparser: ConfigParser = None\n'
                '\n'
                '    def __init__(self):\n'
                '        super().__init__()\n'
                '        self._configparser = ConfigParser()\n'
                '        self.initializeWithDefaults()\n'
                '        self.loadSiteConfig()\n'
                '\n'
                '    def loadSiteConfig(self):\n'
                '        try:\n'
                '            configdir = appdirs.user_config_dir("cpt", "CREDO", roaming=True)\n'
                '            statefile = os.path.join(configdir, "cpt2.ini")\n'
                '            self.load(statefile)\n'
                '        except FileNotFoundError:\n'
                '            pass\n'
                '\n'
                '    def saveSiteConfig(self):\n'
                '        configdir = appdirs.user_config_dir("cpt", "CREDO", roaming=True)\n'
                '        os.makedirs(configdir, exist_ok=True)\n'
                '        self.save(os.path.join(configdir,"cpt2.ini"))\n'
                '\n'
                '    def save(self, filename: str):\n'
                '        with open(filename, "wt") as f:\n'
                '            self._configparser.write(f)\n'
                '        self.saveSiteConfig()\n'
                '\n'
                '    def load(self, filename: str):\n'
                '        self._configparser.read([filename])\n')
        for section in configitems:
            for name in configitems[section]:
                f.write('        self.configItemChanged.emit("{}", "{}", getattr(self, "{}"))\n'.format(section, name,
                                                                                                        name))
        f.write(
            '\n'
            '# Various reader/writer functions\n'
            '    @staticmethod\n'
            '    def _readBool(x: str) -> bool:\n'
            '        if x.upper() in ["Y", "TRUE", "1", "YES", "+", "ON"]:\n'
            '            return True\n'
            '        elif x.upper() in ["N", "FALSE", "0", "NO", "-", "OFF"]:\n'
            '            return False\n'
            '        raise ValueError(x)\n'
            '\n'
            '    @staticmethod\n'
            '    def _writeBool(x: bool) -> str:\n'
            '        assert isinstance(x, bool)\n'
            '        return "True" if bool(x) else "False"\n'
            '\n'
            '    @staticmethod\n'
            '    def _readFSNRanges(x: str) -> List[Tuple[int, int]]:\n'
            '        x = x.strip()\n'
            '        if not (x.startswith("[") and x.endswith("]")):\n'
            '            raise ValueError("Invalid fsn range string")\n'
            '        x = x[1:-1].strip()\n'
            '        ranges = []\n'
            '        for m in re.finditer(r"\(\s*(?P<left>\d+)\s*,\s*(?P<right>\d+)\s*\)", x):\n'
            '            ranges.append((int(m["left"]), int(m["right"])))\n'
            '        return ranges\n'
            '\n'
            '    @staticmethod\n'
            '    def _writeFSNRanges(x: List[Tuple[int, int]]) -> str:\n'
            '        return "["+", ".join(["({:d}, {:d})".format(left, right) for left, right in x])+"]"\n'
            '\n'
            '    @staticmethod\n'
            '    def _readSemicolonSepStrList(x: str) -> List[str]:\n'
            '        return x.split(";")\n'
            '\n'
            '    @staticmethod\n'
            '    def _writeSemicolonSepStrList(x: List[str]) -> str:\n'
            '        return ";".join(x)\n'
        )
        f.write('# properties\n')
        for section in configitems:
            f.write('# Config section {}\n'.format(section))
            for itemname in configitems[section]:
                item = configitems[section][itemname]
                itemtype = configtypes[item.typename]
                f.write('    @property\n'
                        '    def {}(self) -> {}:\n'.format(itemname, itemtype.typehint) +
                        '        """{}"""\n'.format(item.description) +
                        '        value = self._configparser["{}"]["{}"]\n'.format(section, itemname) +
                        '        return {}(value)\n'.format(itemtype.reader) +
                        '\n'
                        )
                f.write('    @{}.setter\n'.format(itemname) +
                        '    def {}(self, value: {}):\n'.format(itemname, itemtype.typehint) +
                        '        """{}"""\n'.format(item.description))
                if item.domain is None:
                    pass  # no domain validation
                elif item.typename in ['int', 'float']:
                    f.write('        if (value < {0[0]}) or (value > {0[1]}):\n'.format(item.domain) +
                            '            raise ValueError("Invalid value for {}")\n'.format(itemname))
                elif item.typename == 'str':
                    f.write(
                        '        if value not in [{}]:\n'.format(', '.join(["\"{}\"".format(x) for x in item.domain])) +
                        '            raise ValueError("Invalid value for {}")\n'.format(itemname))
                f.write('        self._configparser["{}"]["{}"] = {}(value)\n'.format(section, itemname,
                                                                                      itemtype.writer) +
                        '        self.configItemChanged.emit("{}", "{}", self.{})\n'.format(section, itemname,
                                                                                            itemname) +
                        '\n'
                        )
        f.write('    def initializeWithDefaults(self):\n')
        for section in configitems:
            f.write('        try:\n'
                    '            self._configparser.add_section("{}")\n'.format(section) +
                    '        except DuplicateSectionError:\n'
                    '            pass\n'
                    )
            for itemname in configitems[section]:
                item = configitems[section][itemname]
                itemtype = configtypes[item.typename]
                f.write('        self._configparser["{}"]["{}"] = "{}"\n'.format(section, itemname, item.default))
        f.write('\n')
        f.write('    def toDict(self):\n')
        f.write('        return {\n')
        for section in configitems:
            for itemname in configitems[section]:
                f.write('            "{}": self.{},\n'.format(itemname, itemname))
        f.write('        }\n')
        f.write('\n# list of acceptable values\n')
        f.write('    def acceptableValues(self, itemname: str) -> List[str]:\n')
        for section in configitems:
            for itemname in configitems[section]:
                item = configitems[section][itemname]
                if item.typename == 'str' and item.domain is not None:
                    f.write('        if itemname == "{}":\n'.format(itemname))
                    f.write('            return [{}]\n'.format(', '.join(['"{}"'.format(d) for d in item.domain])))
        f.write('        raise ValueError("Invalid item name: {}".format(itemname))\n')
        f.write('\n')

if __name__ == '__main__':
    writeCode()
