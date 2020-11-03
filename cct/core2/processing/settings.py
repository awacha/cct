import re
import configparser
import multiprocessing
import os
from typing import Optional, Set, Iterable, List, Tuple, Final, Dict

import numpy as np

from .calculations.outliertest import OutlierMethod
from ..algorithms.matrixaverager import ErrorPropagationMethod


class ProcessingSettings:

    _errorprop2str: Final[List[Tuple[ErrorPropagationMethod, str]]] = {
        (ErrorPropagationMethod.Conservative, 'Conservative'),
        (ErrorPropagationMethod.Linear, 'Average'),
        (ErrorPropagationMethod.Gaussian, 'Squared (Gaussian)'),
        (ErrorPropagationMethod.Weighted, 'Weighted'),
    }
    rootpath: str
    eval2dsubpath: str = 'eval2d'
    masksubpath: str = 'mask'
    fsndigits: int = 5
    prefix: str = 'crd'
    h5filename: str
    badfsnsfile: str
    ierrorprop: ErrorPropagationMethod = ErrorPropagationMethod.Conservative
    qerrorprop: ErrorPropagationMethod = ErrorPropagationMethod.Conservative
    outliermethod: OutlierMethod = OutlierMethod.IQR
    outlierthreshold: float = 1.5
    outlierlogcormat: bool = True
    bigmemorymode: bool = True
    h5lock: multiprocessing.synchronize.Lock
    badfsns: Set[int]
    qrange: Optional[np.ndarray] = None
    fsnranges: List[Tuple[int, int]]

    filename: Optional[str] = None

    def __init__(self):
        self.rootpath = os.getcwd()
        self.h5lock = multiprocessing.Lock()
        self.badfsns = set()
        self.fsnranges = []

    def addBadFSNs(self, badfsns: Iterable[int]):
        self.badfsns.union(badfsns)
        self.saveBadFSNs()

    def markAsBad(self, fsn: int):
        self.badfsns.add(fsn)
        self.saveBadFSNs()

    def markAsGood(self, fsn: int):
        try:
            self.badfsns.remove(fsn)
        except KeyError:
            return
        self.saveBadFSNs()

    def saveBadFSNs(self):
        with open(self.badfsnsfile, 'wt') as f:
            for fsn in sorted(self.badfsns):
                f.write(f'{fsn}\n')

    def loadBadFSNs(self):
        badfsns = np.loadtxt(self.badfsnsfile).astype(np.int)
        self.badfsns = set(badfsns)

    def load(self, filename: str) -> configparser.ConfigParser:
        cp = configparser.ConfigParser()
        cp.set('io', 'eval2dsubpath', 'eval2d')
        cp.set('io', 'masksubpath', 'mask')
        cp.set('io', 'fsndigits', 5)
        cp.read([filename])
        self.badfsnsfile = cp['io']['badfsnsfile']
        self.h5filename = cp['io']['hdf5']
        self.rootpath = cp.get('io', 'datadir')
        self.eval2dsubpath = cp.get('io', 'eval2dsubpath')
        self.masksubpath = cp.get('io', 'masksubpath')
        self.fsndigits = cp.getint('io', 'fsndigits')
        self.ierrorprop=[ep for ep, s in self._errorprop2str if s==cp.get('processing', 'errorpropagation')][0]
        self.qerrorprop=[ep for ep, s in self._errorprop2str if s==cp.get('processing', 'abscissaerrorpropagation')][0]
        self.outliermethod = OutlierMethod(cp.get('processing', 'outliermethod'))
        self.outlierthreshold = cp.getfloat('processing', 'std_multiplier')
        self.outlierlogcormat = cp.getboolean('processing', 'logcorrelmatrix')
        s = cp.get('io', 'fsnranges').strip()
        if not (m := re.match(r'\[(\(\d+\s*,\s*\d+\))(?:,\s*(\(\d+\s*,\s*\d+\)))*\]', s)):
            raise ValueError(f'Invalid FSN range designation: {s}.')
        self.fsnranges = [tuple([int(g1) for g1 in re.match(r'\((\d+),\s*(\d+)\)', g).groups()]) for g in m.groups()]
        return cp

    def save(self, filename: str):
        cp = configparser.ConfigParser()
        cp.set('io', 'badfsnsfile', self.badfsnsfile)
        cp.set('io', 'hdf5', self.h5filename)
        cp.set('io', 'datadir', self.rootpath)
        cp.set('io', 'eval2dsubpath', self.eval2dsubpath)
        cp.set('io', 'masksubpath', self.masksubpath)
        cp.set('io', 'fsnranges', str(self.fsnranges))
        cp.set('processing', 'errorpropagation', [s for ep, s in self._errorprop2str if ep == self.ierrorprop][0])
        cp.set('processing', 'abscissaerrorpropagation', [s for ep, s in self._errorprop2str if ep == self.qerrorprop][0])
        cp.set('processing', 'std_multiplier', str(self.outlierthreshold))
        cp.set('processing', 'logcorrelmatrix', str(self.outlierlogcormat))
        cp.set('processing', 'outliermethod', self.outliermethod.value)
        cp.set('processing', 'subtraction')



        with open(filename, 'wt') as f:
            cp.write(f)
