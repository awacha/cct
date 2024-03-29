import configparser
import logging
import multiprocessing
import multiprocessing.managers
import multiprocessing.synchronize
import numbers
import os
import re
import enum
from typing import Optional, Set, Iterable, List, Tuple, Final, Iterator, Union

import appdirs
import numpy as np
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from .calculations.outliertest import OutlierMethod
from .h5io import ProcessingH5File
from .loader import Loader, FileNameScheme
from ..algorithms.matrixaverager import ErrorPropagationMethod
from ..dataclasses.exposure import QRangeMethod

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)



class ProcessingSettings(QtCore.QObject):
    _errorprop2str: Final[List[Tuple[ErrorPropagationMethod, str]]] = {
        (ErrorPropagationMethod.Conservative, 'Conservative'),
        (ErrorPropagationMethod.Linear, 'Average'),
        (ErrorPropagationMethod.Gaussian, 'Squared (Gaussian)'),
        (ErrorPropagationMethod.Weighted, 'Weighted'),
    }
    rootpath: str = '.'
    eval2dsubpath: str = 'eval2d'
    masksubpath: str = 'mask'
    fsndigits: int = 5
    prefix: str = 'crd'
    ierrorprop: ErrorPropagationMethod = ErrorPropagationMethod.Gaussian
    qerrorprop: ErrorPropagationMethod = ErrorPropagationMethod.Gaussian
    outliermethod: OutlierMethod = OutlierMethod.IQR
    outlierthreshold: float = 1.5
    outlierlogcormat: bool = True
    bigmemorymode: bool = False
    h5lock: multiprocessing.synchronize.RLock
    badfsns: Set[int]
    fsnranges: List[Tuple[int, int]]
    qrangemethod: QRangeMethod = QRangeMethod.Linear
    qcount: int = 0  # 0 means the same number as pixels
    filenamescheme: FileNameScheme = FileNameScheme.Parts
    filenamepattern: str = "crd_%05d"

    settingsChanged = Signal()
    badfsnsChanged = Signal()
    _h5io: Optional[ProcessingH5File] = None

    _manager: multiprocessing.managers.SyncManager
    _modified: bool = False
    _loader: Optional[Loader] = None

    def __init__(self, filename: str):
        super().__init__()
        self.loadDefaults()
        self.filename = filename
        self.rootpath = os.getcwd()
        self._manager = multiprocessing.Manager()
        self.h5lock = self._manager.RLock()
        self.badfsns = set()
        self.fsnranges = []
        self.load(filename)

    def loadDefaults(self):
        cp = configparser.ConfigParser(interpolation=None)
        cp.read([os.path.join(appdirs.user_config_dir('cct'), 'cpt4.conf')])
        cp['DEFAULT'] = {'eval2dsubpath': 'eval2d',
                         'masksubpath': 'mask',
                         'fsndigits': '5',
                         'prefix': 'crd',
                         'ierrorprop': ErrorPropagationMethod.Conservative.name,
                         'qerrorprop': ErrorPropagationMethod.Conservative.name,
                         'outliermethod': OutlierMethod.IQR.value,
                         'outlierthreshold': '1.5',
                         'logcorrmat': 'yes',
                         'bigmemorymode': 'no',
                         'qrangemethod': QRangeMethod.Linear.name,
                         'qrangecount': 0,
                         'filenamepattern': 'crd_%05d',
                         'filenamescheme': FileNameScheme.Parts.value,
                         }
        if not cp.has_section('cpt4'):
            cp.add_section('cpt4')
        cpt4section = cp['cpt4']
        self.eval2dsubpath = cpt4section.get('eval2dsubpath')
        self.masksubpath = cpt4section.get('masksubpath')
        self.fsndigits = cpt4section.getint('fsndigits')
        self.prefix = cpt4section.get('prefix')
        self.ierrorprop = ErrorPropagationMethod[cpt4section.get('ierrorprop')]
        self.qerrorprop = ErrorPropagationMethod[cpt4section.get('qerrorprop')]
        self.outliermethod = OutlierMethod(cpt4section.get('outliermethod'))
        self.outlierthreshold = cpt4section.getfloat('outlierthreshold')
        self.outlierlogcormat = cpt4section.getboolean('logcorrmat')
        self.bigmemorymode = cpt4section.getboolean('bigmemorymode')
        self.qrangemethod = QRangeMethod[cpt4section.get('qrangemethod')]
        self.qcount = cpt4section.getint('qrangecount')
        self.filenamescheme = FileNameScheme(cpt4section.get('filenamescheme'))
        self.filenamepattern = cpt4section.get('filenamepattern')

    def saveDefaults(self):
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(os.path.join(appdirs.user_config_dir('cct'), 'cpt4.conf'))
        if not cp.has_section('cpt4'):
            cp.add_section('cpt4')
        cpt4section = cp['cpt4']
        cpt4section['eval2dsubpath'] = self.eval2dsubpath
        cpt4section['masksubpath'] = self.masksubpath
        cpt4section['fsndigits'] = str(self.fsndigits)
        cpt4section['prefix'] = self.prefix
        cpt4section['ierrorprop'] = self.ierrorprop.name
        cpt4section['qerrorprop'] = self.qerrorprop.name
        cpt4section['outliermethod'] = self.outliermethod.value
        cpt4section['outlierthreshold'] = str(self.outlierthreshold)
        cpt4section['logcorrmat'] = 'yes' if self.outlierlogcormat else 'no'
        cpt4section['bigmemorymode'] = 'yes' if self.bigmemorymode else 'no'
        cpt4section['qrangecount'] = str(self.qcount)
        cpt4section['qrangemethod'] = self.qrangemethod.name
        cpt4section['filenamepattern'] = self.filenamepattern
        cpt4section['filenamescheme'] = self.filenamescheme.value
        os.makedirs(appdirs.user_config_dir('cct'), exist_ok=True)
        with open(os.path.join(appdirs.user_config_dir('cct'), 'cpt4.conf'), 'wt') as f:
            cp.write(f)

    def addBadFSNs(self, badfsns: Iterable[int]):
        newbadfsns = [b for b in badfsns if b not in self.badfsns]
        logger.debug(f'New bad fsns: {newbadfsns}')
        logger.debug(f'Old bad fsns: {self.badfsns}')
        self.badfsns = self.badfsns.union(newbadfsns)
        self.saveBadFSNs()
        self.badfsnsChanged.emit()

    def markAsBad(self, fsn: Union[int, Iterable[int]]):
        if isinstance(fsn, numbers.Number):
            fsn = [fsn]
        self.badfsns = self.badfsns.union(fsn)
        self.saveBadFSNs()
        self.badfsnsChanged.emit()

    def markAsGood(self, fsn: Union[int, Iterable[int]]):
        if isinstance(fsn, numbers.Number):
            fsn = [fsn]
        self.badfsns = self.badfsns.difference(fsn)
        self.saveBadFSNs()
        self.badfsnsChanged.emit()

    def saveBadFSNs(self):
        with self.h5io.writer('cptsettings') as grp:
            try:
                del grp['badfsns']
            except KeyError:
                pass
            grp.create_dataset('badfsns', data=np.array(sorted(self.badfsns)), dtype=np.int)
        logger.debug('BadFSNs list saved to HDF5 file.')

    def loadBadFSNs(self, filename: Optional[str] = None):
        try:
            with self.h5io.reader('cptsettings') as grp:
                badfsns = set(np.array(grp['badfsns']).tolist())
        except:
            logger.warning('Cannot read badFSNS list from H5 file, trying to load it from the badfsns file instead.')
            if filename is not None:
                try:
                    badfsns = np.loadtxt(filename).astype(np.int)
                except IOError:
                    logger.warning(f'Could not open badfsns file {filename}')
                    return
            else:
                badfsns = []
        self.badfsns = set(badfsns)
        self.badfsnsChanged.emit()
        return self.badfsns

    def load(self, filename: str):
        if filename.lower().endswith('.cpt') or filename.lower().endswith('.cpt2'):
            cp = configparser.ConfigParser(interpolation=None)
            cp.read([filename])

            def parsefsnranges(s) -> List[Tuple[int, int]]:
                if not (m := re.match(r'\[(\(\d+\s*,\s*\d+\))(?:,\s*(\(\d+\s*,\s*\d+\)))*\]', s)):
                    raise ValueError(f'Invalid FSN range designation: {s}.')
                logger.debug(str(m.groups()))
                return [tuple([int(g1) for g1 in re.match(r'\((\d+),\s*(\d+)\)', g).groups()]) for g in m.groups() if
                        g is not None]

            for attr, section, option, typeconversion in [
                ('filename', 'io', 'hdf5', lambda s: os.path.split(s)[-1]),
                ('rootpath', 'io', 'datadir', str),
                ('eval2dsubpath', 'io', 'eval2dsubpath', str),
                ('masksubpath', 'io', 'masksubpath', str),
                ('fsndigits', 'io', 'fsndigits', str),
                ('ierrorprop', 'processing', 'errorpropagation',
                 lambda val: [ep for ep, s in self._errorprop2str if s == val][0]),
                ('qerrorprop', 'processing', 'abscissaerrorpropagation',
                 lambda val: [ep for ep, s in self._errorprop2str if s == val][0]),
                ('outliermethod', 'processing', 'outliermethod', OutlierMethod),
                ('outlierthreshold', 'processing', 'std_multiplier', float),
                ('outlierlogcormat', 'processing', 'logcorrelmatrix', lambda val: val.upper().strip() == 'TRUE'),
                ('fsnranges', 'io', 'fsnranges', parsefsnranges),
                ('qrangemethod', 'processing', 'qrangemethod', lambda x: QRangeMethod[x]),
                ('qcount', 'processing', 'qrangecount', int),
                ('badfsns', 'io', 'badfsnsfile', self.loadBadFSNs),
            ]:
                try:
                    setattr(self, attr, typeconversion(cp[section][option]))
                except KeyError:
                    logger.debug(f'Cannot read attribute from ini file: {attr}')
                    continue
            try:
                re_int = r'[+-]?\d+'
                re_float = r'[+-]?(\d*\.\d+|\d+\.\d*)([eE][+-]?\d+)?'
                re_number = f'({re_float}|{re_int})'
                for record in cp['processing']['subtraction'].split(';'):
                    if (m := re.match(r"SubtractionJobRecord\s*\("
                                      r"\s*sample\s*=\s*'(?P<samplename>[^']+)'\s*,"
                                      r"\s*background\s*=\s*'(?P<background>[^']+)'\s*,"
                                      r"\s*mode\s*=\s*'(?P<scalingmode>(None|Constant|Interval|Power-law))'\s*,"
                                      rf"\s*params\s*=\s*'\((?P<params>(\s*{re_number}\s*(\s*,\s*{re_number}\s*)*)?)\)'\)",
                                      record.strip())) is None:
                        raise ValueError(f'Cannot parse string {record.strip()}')
                    with self.h5io.writer(group='Samples') as grp:
                        g = grp.require_group(f'{m["samplename"]}-{m["background"]}')
                        g.attrs['subtraction_samplename'] = m["samplename"]
                        g.attrs['subtraction_background'] = m["background"]
                        g.attrs['subtraction_mode'] = m['scalingmode']
                        if not m['params']:
                            g.attrs['subtraction_factor'] = 1.0
                            g.attrs['subtraction_factor_unc'] = 0.0
                            g.attrs['subtraction_qmin'] = 0
                            g.attrs['subtraction_qmax'] = 1000
                            g.attrs['subtraction_qcount'] = 100
                        elif m['params'].count(',') == 0:
                            g.attrs['subtraction_factor'] = float(m['params'])
                            g.attrs['subtraction_factor_unc'] = 0.0
                            g.attrs['subtraction_qmin'] = 0
                            g.attrs['subtraction_qmax'] = 1000
                            g.attrs['subtraction_qcount'] = 100
                        elif m['params'].count(',') == 2:
                            qmin, qmax, qcount = m['params'].split(',')
                            g.attrs['subtraction_factor'] = 1.0
                            g.attrs['subtraction_factor_unc'] = 0.0
                            g.attrs['subtraction_qmin'] = float(qmin)
                            g.attrs['subtraction_qmax'] = float(qmax)
                            g.attrs['subtraction_qcount'] = int(qcount)
                        else:
                            logger.warning(f'Cannot parse subtraction parameters: {m["params"]}')
                            g.attrs['subtraction_factor'] = 1.0
                            g.attrs['subtraction_factor_unc'] = 0.0
                            g.attrs['subtraction_qmin'] = 0
                            g.attrs['subtraction_qmax'] = 1000
                            g.attrs['subtraction_qcount'] = 100
            except KeyError:
                pass
            logger.debug(f'Loaded settings from ini file {filename}')
            return cp
        elif (filename.lower().endswith('.h5')) or (filename.lower().endswith('.cpt4')):
            self.filename = filename
            # ensure the h5io is reconstructed with the new file name. Don't use assert, it can be disabled!
            isinstance(self.h5io, ProcessingH5File)
            try:
                with self.h5io.reader('cptsettings') as grp:
                    identity = lambda a: a
                    for attrname, grpname, h5attrname, typeconversion in [
                        ('filename', 'io', 'hdf5', identity),
                        ('rootpath', 'io', 'datadir', identity),
                        ('eval2dsubpath', 'io', 'eval2dsubpath', identity),
                        ('masksubpath', 'io', 'masksubpath', identity),
                        ('fsndigits', 'io', 'fsndigits', identity),
                        ('ierrorprop', 'processing', 'errorpropagation', ErrorPropagationMethod),
                        ('qerrorprop', 'processing', 'qerrorpropagation', ErrorPropagationMethod),
                        ('outliermethod', 'processing', 'outliermethod', OutlierMethod),
                        ('outlierthreshold', 'processing', 'outlierthreshold', identity),
                        ('outlierlogcormat', 'processing', 'logcorrelmatrix', identity),
                        ('qrangemethod', 'processing', 'qrangemethod', lambda x: QRangeMethod[x]),
                        ('count', 'processing', 'qrangecount', int),
                        ('filenamepattern', 'io', 'filenamepattern', str),
                        ('filenamescheme', 'io', 'filenamescheme', FileNameScheme)
                    ]:
                        try:
                            setattr(self, attrname, typeconversion(grp[grpname].attrs[h5attrname]))
                        except KeyError:
                            logger.debug(f'Cannot read attribute from h5 file: {attrname}')
                            continue
                    fsnrangesdata = grp['io']['fsnranges']
                    self.fsnranges = [(fsnrangesdata[i, 0], fsnrangesdata[i, 1]) for i in range(fsnrangesdata.shape[0])]
                    self.loadBadFSNs()
                logger.info(f'Loaded config from H5 file {filename}')
            except (OSError, KeyError):
                logger.warning(f'Could not load config from H5 file {filename}')
        else:
            raise ValueError('Unknown file format.')

    def save(self, filename: Optional[str] = None):
        self.saveDefaults()
        with self.h5io.writer('cptsettings') as grp:
            iogrp = grp.require_group('io')
            iogrp.attrs['datadir'] = self.rootpath
            iogrp.attrs['eval2dsubpath'] = self.eval2dsubpath
            iogrp.attrs['masksubpath'] = self.masksubpath
            iogrp.attrs['fsndigits'] = self.fsndigits
            iogrp.attrs['prefix'] = self.prefix
            iogrp.attrs['bigmemorymode'] = self.bigmemorymode
            iogrp.attrs['filenamescheme'] = self.filenamescheme.value
            iogrp.attrs['filenamepattern'] = self.filenamepattern
            try:
                del iogrp['fsnranges']
            except KeyError:
                pass
            if self.fsnranges:
                iogrp.create_dataset('fsnranges', data=np.vstack(self.fsnranges))
            else:
                iogrp.create_dataset('fsnranges', data=np.array([]))

            processinggrp = grp.require_group('processing')
            processinggrp.attrs['errorpropagation'] = self.ierrorprop.value
            processinggrp.attrs['qerrorpropagation'] = self.qerrorprop.value
            processinggrp.attrs['outliermethod'] = self.outliermethod.value
            processinggrp.attrs['outlierthreshold'] = self.outlierthreshold
            processinggrp.attrs['logcorrelmatrix'] = self.outlierlogcormat
            processinggrp.attrs['qrangemethod'] = self.qrangemethod.name
            processinggrp.attrs['qrangecount'] = self.qcount
        logger.info(f'Saved settings to h5 file {self.h5io.filename}')

    @property
    def lockManager(self) -> multiprocessing.managers.SyncManager:
        return self._manager

    @property
    def h5io(self) -> ProcessingH5File:
        if (self._h5io is None) or (self._h5io.filename != self.filename):
            with self.h5lock:
                self._h5io = ProcessingH5File(self.filename, self.h5lock)
        return self._h5io

    def fsns(self) -> Iterator[int]:
        for fmin, fmax in self.fsnranges:
            yield from range(fmin, fmax + 1)

    def emitSettingsChanged(self):
        self.save()
        self.settingsChanged.emit()

    def loader(self) -> Loader:
        if self._loader is None:
            return Loader(self.rootpath, self.eval2dsubpath, self.masksubpath, self.fsndigits, self.prefix, self.filenamepattern, self.filenamescheme)
        elif (self._loader.rootpath != self.rootpath) or (self._loader.eval2dsubpath != self.eval2dsubpath) or \
                (self._loader.masksubpath != self.masksubpath) or (self._loader.fsndigits != self.fsndigits) or \
                (self._loader.prefix != self.prefix) or (self._loader.filenamepattern != self.filenamepattern) or \
                (self._loader.filenamescheme != self.filenamescheme):
            del self._loader
            self._loader = None
            return self.loader()
        else:
            return self._loader
