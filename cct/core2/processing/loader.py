import logging
import enum
import os
import time
from typing import Tuple, Dict, Final, Optional, List

import numpy as np
import scipy.io

from ..dataclasses import Exposure, Header

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class FileNameScheme(enum.Enum):
    Parts = "Filename parts"
    Pattern = "Filename pattern"


class Loader:
    _cachetimeout: Final[float] = 300.
    rootpath: str
    eval2dsubpath: str
    masksubpath: str
    fsndigits: int
    prefix: str
    filenamescheme: FileNameScheme
    filenamepattern: str
    _maskcache: Dict[str, Tuple[np.ndarray, float, str]]

    def __init__(self, rootpath: str, eval2dsubpath: str = 'eval2d', masksubpath: str = 'mask', fsndigits: int = 5,
                 prefix: str = 'crd_', filenamepattern: str = 'crd_%05d',
                 filenamescheme: FileNameScheme = FileNameScheme.Parts):
        self.rootpath = rootpath
        self.eval2dsubpath = eval2dsubpath
        self.masksubpath = masksubpath
        self.fsndigits = fsndigits
        self.prefix = prefix
        self.filenamepattern = filenamepattern
        self.filenamescheme = filenamescheme
        self._maskcache = {}

    def _findfile(self, filename: str, directory: str, arbitraryextension: bool = True,
                  quicksubdirs: Optional[List[str]] = None):
        # first try to read the file from the directory
        if os.path.isfile(os.path.join(directory, filename)):
            return os.path.join(directory, filename)
        # next, try each subdirectory supplied in the `quicksubdirs` argument
        if quicksubdirs is not None:
            for sd in quicksubdirs:
                if os.path.isfile(os.path.join(directory, sd, filename)):
                    return os.path.join(directory, filename)
        #
        filenames = os.listdir(directory)
        folders = [fn for fn in filenames if os.path.isdir(os.path.join(directory, fn))]
        for fn in [fn for fn in filenames if fn not in folders]:
            if fn == filename or (arbitraryextension and (os.path.splitext(fn)[0] == filename)):
                return os.path.join(directory, fn)
        for f in folders:
            try:
                return self._findfile(filename, os.path.join(directory, f), arbitraryextension)
            except FileNotFoundError:
                pass
        raise FileNotFoundError(filename)

    def loadMask(self, maskname: str) -> np.ndarray:
        maskname = os.path.split(maskname)[-1]
        try:
            mask, mtime, filename = self._maskcache[maskname]
            if time.time() > mtime + self._cachetimeout:
                # mask cache timeout
                raise KeyError(maskname)
            elif os.stat(filename).st_mtime > mtime:
                # mask file changed on disk
                raise KeyError(maskname)
            else:
                return mask
        except KeyError:
            # mask not found in the cache or out of date
            maskfile = self._findfile(maskname, os.path.join(self.rootpath, self.masksubpath))
            if maskfile.lower().endswith('.mat'):
                matfile = scipy.io.loadmat(maskfile)
                maskkey = [k for k in matfile.keys() if not (k.startswith('_') or k.endswith('_'))][0]
                mask = matfile[maskkey]
            elif maskfile.lower().endswith('.npy'):
                mask = np.load(maskfile)
            else:
                raise ValueError(f'Unknown mask file type: {maskfile}: neither .mat, nor .npy.')
            self._maskcache[maskname] = mask, os.stat(maskfile).st_mtime, maskfile
            return mask

    def loadExposure(self, fsn: int, header: Optional[Header] = None) -> Exposure:
        if header is None:
            header = self.loadHeader(fsn)
        filename = self.filebasename(fsn) + '.npz'
        npzfile = np.load(self._findfile(filename, os.path.join(self.rootpath, self.eval2dsubpath),
                                         quicksubdirs=[self.prefix] if self.prefix is not None else [],
                                         arbitraryextension=False))
        if 'mask' not in npzfile:
            mask = self.loadMask(header.maskname)
        else:
            mask = npzfile['mask']
        try:
            return Exposure(npzfile['Intensity'], header, npzfile['Error'], mask)
        except:
            raise ValueError(f'Cannot load exposure {fsn=}')

    def loadHeader(self, fsn: int) -> Header:
        filename = self.filebasename(fsn) + '.pickle'
        return Header(
            self._findfile(filename, os.path.join(self.rootpath, self.eval2dsubpath), arbitraryextension=False,
                           quicksubdirs=[self.prefix] if self.prefix is not None else []))

    def filebasename(self, fsn: int) -> str:
        if self.filenamescheme == FileNameScheme.Parts:
            return f'{self.prefix}_{fsn:0{self.fsndigits}}'
        elif self.filenamescheme == FileNameScheme.Pattern:
            return self.filenamepattern % fsn
