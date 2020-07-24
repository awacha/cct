import logging
import os
import pathlib
import re
import time
from typing import Dict, Tuple, Optional, List

import numpy as np
from PyQt5 import QtCore
from sastool.io.credo_cct import Exposure, Header
from scipy.io import loadmat

from .component import Component

logger = logging.getLogger(__name__)


class IO(QtCore.QObject, Component):
    """I/O subsystem of the instrument, responsible for reading and writing files and maintaining the file sequence.

    File system layout:

    """
    _masks: Dict[str, Tuple[pathlib.Path, np.ndarray, float]]
    _nextfsn: Dict[str, int]
    _lastfsn: Dict[str, Optional[int]]
    _lastscan: Optional[int] = None
    _nextscan: int = 0

    nextFSNChanged = QtCore.pyqtSignal(str, int)
    lastFSNChanged = QtCore.pyqtSignal(str, int)
    nextscanchanged = QtCore.pyqtSignal(int)
    lastscanchanged = QtCore.pyqtSignal(int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._masks = {}
        self._lastfsn = {}
        self._nextfsn = {}
        self._lastscan = None
        self._nextscan = 0
        self.reindex()

    def getSubDir(self, subdir: str) -> pathlib.Path:
        return pathlib.Path.cwd() / self.config['path']['directories'][subdir]

    ### Nextfsn / Lastfsn list maintenance

    def reindex(self):
        """Update lastfsn and nextfsn values.

        As we need to traverse the full directory structure, this can take much time. So use it sparingly, typically at
        the start of the program.
        """
        # check raw detector images
        logger.info('Reindexing already present exposures...')
        t0 = time.monotonic()
        for subdir, extension in [
            ('images', 'cbf'), ('param', 'param'), ('param_override', 'param'),
            ('eval2d', 'npz'), ('eval1d', 'txt')]:
            # find all subdirectories in `directory`, including `directory`
            # itself
            directory = self.getSubDir(subdir)
            logger.debug(f'Looking in directory {directory}')
            filename_regex = re.compile(rf'^(?P<prefix>\w+)_(?P<fsn>\d+)\.{extension}$')
            for folder, subdirs, files in os.walk(str(directory)):
                # find all files
                matchlist = [m for m in [filename_regex.match(f) for f in files] if m is not None]
                # find all file prefixes, like 'crd', 'tst', 'tra', 'scn', etc.
                for prefix in {m.group('prefix') for m in matchlist}:
                    logger.debug(f'Treating prefix {prefix}')
                    if prefix not in self._lastfsn:
                        logger.debug(f'New prefix: {prefix}.')
                        self._lastfsn[prefix] = None
                    # find the highest available FSN of the current prefix in
                    # this directory
                    maxfsn = max([int(m.group('fsn')) for m in matchlist if m.group('prefix') == prefix])
                    logger.debug(f'Maxfsn for prefix {prefix} in directory {directory}: {maxfsn}')
                    if self._lastfsn[prefix] is None or (maxfsn > self._lastfsn[prefix]):
                        self._lastfsn[prefix] = maxfsn

        # add known prefixes to self._lastfsn if they were not yet added.
        for prefix in self.config['path']['prefixes'].values():
            if prefix not in self._lastfsn:
                logger.debug(f'Adding not found prefix to _lastfsn: {prefix}')
                self._lastfsn[prefix] = None

        # update self._nextfsn
        for prefix in self._lastfsn:
            self._nextfsn[prefix] = self._lastfsn[prefix] + 1 if self._lastfsn[prefix] is not None else 0

        # reload scan file table of contents.

    def reindexScanfile(self):
        with open(os.path.join(self.config['path']['directories']['scan'],
                               self.config['scan']['scanfile']), 'rt') as f:
            maxscan = -np.inf
            for line in f:
                lss = line.strip().split()
                if not lss:
                    continue
                if lss[0] == '#S':
                    if int(lss[1]) > maxscan:
                        maxscan = int(lss[1])
            self._lastscan = maxscan
            self._nextscan = maxscan + 1

    def nextfsn(self, prefix: str, checkout: bool = True) -> int:
        """Get the next file sequence number from the desired sequence

        :param prefix: file sequence prefix
        :type prefix: str
        :param checkout: if True, reserve this FSN, i.e. an exposure is about to be started.
        :type checkout: bool
        :return: the file sequence number
        :rtype: int
        """
        try:
            nextfsn = self._nextfsn[prefix]
        except KeyError:
            self._nextfsn[prefix] = 0
            nextfsn = self._nextfsn[prefix]
        if checkout:
            self._nextfsn[prefix] += 1
        return nextfsn

    def lastfsn(self, prefix: str) -> Optional[int]:
        """Return the last file sequence number for which an exposure exists

        :param prefix: file sequence prefix
        :type prefix: str
        :return: the sequence number or None if no exposures exist in that sequence
        :rtype: int or None
        """
        try:
            return self._lastfsn[prefix]
        except KeyError:
            self._lastfsn[prefix] = None
            return None

    @property
    def prefixes(self) -> List[str]:
        """Get the known file sequence prefixes"""
        return list(self._lastfsn.keys())

    ### Loading exposures, headers, masks

    def formatFileName(self, prefix: str, fsn: int, extn: str = '') -> str:
        return f'{prefix}_{fsn:0{self.config["path"]["fsndigits"]}d}{extn}'

    def loadExposure(self, prefix: str, fsn: int, raw: bool = True) -> Exposure:
        """Load an exposure

        :param prefix: file sequence prefix
        :type prefix: str
        :param fsn: file sequence index
        :type fsn: int
        :param raw: load raw (True) or processed (False) data
        :type raw: bool
        :return: the exposure
        :rtype: Exposure
        :raises FileNotFoundError: if the file could not be found
        """
        expfilename = self.formatFileName(prefix, fsn, '.cbf' if raw else '.npz')
        header = self.loadHeader(prefix, fsn, raw)
        mask = self.loadMask(header.maskname)
        for folder, dirs, files in os.walk(str(self.getSubDir('images' if raw else 'eval2d'))):
            if expfilename in files:
                return Exposure.new_from_file(os.path.join(folder, expfilename), header, mask)
        raise FileNotFoundError(expfilename)

    def loadHeader(self, prefix: str, fsn: int, raw: bool = True) -> Header:
        """Load a metadata file (.pickle)

        :param prefix: file sequence prefix
        :type prefix: str
        :param fsn: file sequence index
        :type fsn: int
        :param raw: load raw (True) or processed (False) data
        :type raw: bool
        :return: the metadata
        :rtype: Header
        :raises FileNotFoundError: if the file could not be found
        """
        filename = self.formatFileName(prefix, fsn, '.pickle')
        for subdir in ['param_override', 'param'] if raw else ['eval2d']:
            for folder, dirs, files in os.walk(str(self.getSubDir(subdir))):
                if filename in files:
                    return Header.new_from_file(os.path.join(folder, filename))
        raise FileNotFoundError(filename)

    def loadMask(self, maskname: str) -> np.array:
        """Load a mask

        The 'mask' subdirectory is traversed recursively. The first file with matching name is found.

        A cache of mask matrices is kept; whenever a mask changes on disk, it is reloaded.

        :param maskname: name of the mask (file name with or without extension)
        :type maskname: str
        :return: the mask
        :rtype: np.ndarray (2 dimensions, dtype np.uint8)
        """
        mask = None
        if maskname not in self._masks:
            for folder, dirnames, filenames in os.walk(str(self.getSubDir('mask'))):
                for extn in ['', '.npy', '.mat']:
                    if maskname + extn in filenames:
                        maskfile = pathlib.Path(folder, maskname + extn)
                        try:
                            mask = self._loadmask(maskfile)
                            break
                        except ValueError:
                            # probably because of an unknown extension. Try further.
                            continue
                else:
                    # no extension matched, continue with the next subfolder
                    continue
                # we have a mask file loaded.
                break
            else:
                raise FileNotFoundError(maskname)
            if mask is None:
                raise FileNotFoundError(maskname)
            self._masks[maskname] = (maskfile, mask, maskfile.stat().st_mtime)
        else:
            maskfile, mask, mtime = self._masks[maskname]
            if maskfile.stat().st_mtime > mtime:
                # the file has changed, reload
                self._masks[maskname] = (maskfile, self._loadmask(maskfile), maskfile.stat().st_mtime)

    @staticmethod
    def _loadmask(filename: os.PathLike) -> np.ndarray:
        """Load a mask from a Matlab(R) or a Numpy file

        :param filename: file name to load mask from
        :type filename: str
        :return: the mask
        :rtype: np.ndarray (2 dimensions, dtype np.uint8)
        """
        if str(filename).lower().endswith('.mat'):
            return IO._loadmask_mat(filename)
        elif str(filename).lower().endswith('.npy'):
            return IO._loadmask_npy(filename)
        else:
            raise ValueError(f'Unknown file extension encountered on mask file {filename}')

    @staticmethod
    def _loadmask_mat(filename: os.PathLike) -> np.ndarray:
        """Load a mask from a Matlab(R) file

        :param filename: file name to load mask from
        :type filename: str
        :return: the mask
        :rtype: np.ndarray (2 dimensions, dtype np.uint8)
        """
        mask = loadmat(str(filename))
        maskkey = [k for k in mask if not k.startswith('_')][0]
        return mask[maskkey]

    @staticmethod
    def _loadmask_npy(filename: os.PathLike) -> np.ndarray:
        """Load a mask from a Numpy file

        :param filename: file name to load mask from
        :type filename: str
        :return: the mask
        :rtype: np.ndarray (2 dimensions, dtype np.uint8)
        """
        return np.load(str(filename)).astype(np.uint8)

    ### Creating new files: metadata, scans etc.

    def saveMetaData(self):
        raise NotImplementedError

    def startNewScan(self):
        raise NotImplementedError

    def addScanPoint(self):
        raise NotImplementedError

    def startNewSpecFile(self):
        raise NotImplementedError

    def onConfigChanged(self, path, value):
        if path == ('scan', 'scanfile'):
            self.reindexScanfile()
        elif path[:2] == ('path', 'directories'):
            self.reindex()

