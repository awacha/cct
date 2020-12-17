import configparser
import logging
import numbers
import multiprocessing.synchronize, multiprocessing.managers, multiprocessing
import os
import re
from typing import Optional, Set, Iterable, List, Tuple, Final, Iterator, Union, Sequence

import numpy as np

from .calculations.outliertest import OutlierMethod
from .h5io import ProcessingH5File
from ..algorithms.matrixaverager import ErrorPropagationMethod

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ProcessingSettings:
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
    _h5io: Optional[ProcessingH5File] = None

    _manager: multiprocessing.managers.SyncManager
    _modified: bool=False

    def __init__(self, filename: str):
        self.filename = filename
        self.rootpath = os.getcwd()
        self._manager = multiprocessing.Manager()
        self.h5lock = self._manager.RLock()
        self.badfsns = set()
        self.fsnranges = []
        self.load(filename)

    def addBadFSNs(self, badfsns: Iterable[int]):
        newbadfsns = [b for b in badfsns if b not in self.badfsns]
        logger.debug(f'New bad fsns: {newbadfsns}')
        logger.debug(f'Old bad fsns: {self.badfsns}')
        self.badfsns = self.badfsns.union(newbadfsns)
        self.saveBadFSNs()

    def markAsBad(self, fsn: Union[int, Iterable[int]]):
        if isinstance(fsn, numbers.Number):
            fsn = [fsn]
        self.badfsns = self.badfsns.union(fsn)
        self.saveBadFSNs()

    def markAsGood(self, fsn: Union[int, Iterable[int]]):
        if isinstance(fsn, numbers.Number):
            fsn = [fsn]
        self.badfsns = self.badfsns.difference(fsn)
        self.saveBadFSNs()

    def saveBadFSNs(self):
        with self.h5io.writer('cptsettings') as grp:
            try:
                del grp['badfsns']
            except KeyError:
                pass
            grp.create_dataset('badfsns', data=np.array(sorted(self.badfsns)), dtype=np.int)
        logger.debug('BadFSNs list saved to HDF5 file.')

    def loadBadFSNs(self, filename: Optional[str]=None):
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
        return self.badfsns

    def load(self, filename: str):
        if filename.lower().endswith('.cpt') or filename.lower().endswith('.cpt2'):
            cp = configparser.ConfigParser()
            cp.read([filename])

            def parsefsnranges(s) -> List[Tuple[int,int]]:
                if not (m := re.match(r'\[(\(\d+\s*,\s*\d+\))(?:,\s*(\(\d+\s*,\s*\d+\)))*\]', s)):
                    raise ValueError(f'Invalid FSN range designation: {s}.')
                logger.debug(str(m.groups()))
                return [tuple([int(g1) for g1 in re.match(r'\((\d+),\s*(\d+)\)', g).groups()]) for g in m.groups() if g is not None]

            for attr, section, option, typeconversion in [
                ('filename', 'io', 'hdf5', lambda s:os.path.split(s)[-1]),
                ('rootpath', 'io', 'datadir', str),
                ('eval2dsubpath', 'io', 'eval2dsubpath', str),
                ('masksubpath', 'io', 'masksubpath', str),
                ('fsndigits', 'io', 'fsndigits', str),
                ('ierrorprop', 'processing', 'errorpropagation', lambda val: [ep for ep, s in self._errorprop2str if s==val][0]),
                ('qerrorprop', 'processing', 'abscissaerrorpropagation', lambda val: [ep for ep, s in self._errorprop2str if s==val][0]),
                ('outliermethod', 'processing', 'outliermethod', OutlierMethod),
                ('outlierthreshold', 'processing', 'std_multiplier', float),
                ('outlierlogcormat', 'processing', 'logcorrelmatrix', lambda val: val.upper().strip()=='TRUE'),
                ('fsnranges', 'io', 'fsnranges', parsefsnranges),
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
            isinstance(self.h5io, ProcessingH5File)  # ensure the h5io is reconstructed with the new file name. Don't use assert, it can be disabled!
            try:
                with self.h5io.reader('cptsettings') as grp:
                    identity = lambda a:a
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
        with self.h5io.writer('cptsettings') as grp:
            iogrp = grp.require_group('io')
            iogrp.attrs['datadir'] = self.rootpath
            iogrp.attrs['eval2dsubpath'] = self.eval2dsubpath
            iogrp.attrs['masksubpath'] = self.masksubpath
            iogrp.attrs['fsndigits'] = self.fsndigits
            iogrp.attrs['prefix'] = self.prefix
            iogrp.attrs['bigmemorymode'] = self.bigmemorymode
            try:
                del iogrp['fsnranges']
            except KeyError:
                pass
            iogrp.create_dataset('fsnranges', data=np.vstack(self.fsnranges))
            processinggrp = grp.require_group('processing')
            processinggrp.attrs['errorpropagation'] = self.ierrorprop.value
            processinggrp.attrs['qerrorpropagation'] = self.qerrorprop.value
            processinggrp.attrs['outliermethod'] = self.outliermethod.value
            processinggrp.attrs['outlierthreshold'] = self.outlierthreshold
            processinggrp.attrs['logcorrelmatrix'] = self.outlierlogcormat
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
            yield from range(fmin, fmax)