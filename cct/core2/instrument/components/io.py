import logging
import os
import pathlib
import re
import time
from typing import Dict, Tuple, Optional, List, Iterator

import h5py
import numpy as np
from PyQt5 import QtCore
from scipy.io import loadmat

from .component import Component
from ...algorithms.readcbf import readcbf
from ...dataclasses import Exposure, Header

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class IO(QtCore.QObject, Component):
    """I/O subsystem of the instrument, responsible for reading and writing files and maintaining the file sequence.

    File system layout:

    """
    _masks: Dict[str, Tuple[pathlib.Path, np.ndarray, float]]
    _nextfsn: Dict[str, int]
    _lastfsn: Dict[str, Optional[int]]


    nextFSNChanged = QtCore.pyqtSignal(str, int)
    lastFSNChanged = QtCore.pyqtSignal(str, int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._masks = {}
        self._lastfsn = {}
        self._nextfsn = {}
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
            ('images', 'cbf'), ('images_local', 'cbf'), ('param', 'param'), ('param_override', 'param'),
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

    def nextfsn(self, prefix: str, checkout: int=0) -> int:
        """Get the next file sequence number from the desired sequence

        :param prefix: file sequence prefix
        :type prefix: str
        :param checkout: if nonzero, reserve this FSN, and the next `checkout-1` FSNs i.e. an exposure is about to be
                         started.
        :type checkout: int
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

    def iterfilename(self, subdir, prefix, fsn, extension) -> Iterator[str]:
        filename = f'{prefix}_{fsn:0{self.config["path"]["fsndigits"]}d}{extension}'
        yield os.path.join(subdir, prefix, filename)
        yield os.path.join(subdir, filename)
        yield os.path.join(subdir, f'{prefix}{fsn//10000}', filename)
        yield os.path.join(subdir, f'{prefix}_{fsn//10000}')

    ### Loading exposures, headers, masks

    def formatFileName(self, prefix: str, fsn: int, extn: str = '') -> str:
        return f'{prefix}_{fsn:0{self.config["path"]["fsndigits"]}d}{extn}'

    def loadExposure(self, prefix: str, fsn: int, raw: bool = True, check_local: bool = False) -> Exposure:
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
        try:
            mask = self.loadMask(header.maskname)
        except FileNotFoundError:
            mask = self.loadMask(os.path.split(header.maskname)[-1])
        if raw and check_local:
            subdirs = ['images_local', 'images']
        elif raw and not check_local:
            subdirs = ['images']
        elif not raw:
            subdirs = ['eval2d']
        else:
            assert False
        for subdir in subdirs:
            for filename in self.iterfilename(str(self.getSubDir(subdir)), prefix, fsn, '.cbf' if raw else '.npz'):
                try:
                    if filename.lower().endswith('.cbf'):
                        intensity = readcbf(filename)
                        uncertainty = intensity**0.5
                        uncertainty[intensity<=0] = 1
                    elif filename.lower().endswith('.npz'):
                        data = np.load(filename)
                        intensity = data['Intensity']
                        uncertainty = data['Uncertainty']
                    else:
                        assert False
                    return Exposure(intensity, header, uncertainty, mask)
                except FileNotFoundError:
                    pass
        raise FileNotFoundError(expfilename)

    def loadCBF(self, prefix: str, fsn: int, check_local: bool = False) -> np.ndarray:
        """Load a CBF file

        :param prefix: file sequence prefix
        :type prefix: str
        :param fsn: file sequence index
        :type fsn: int
        :return: the exposure
        :rtype: Exposure
        :raises FileNotFoundError: if the file could not be found
        """
        expfilename = self.formatFileName(prefix, fsn, '.cbf')
        for subdir in ['images_local', 'images'] if check_local else ['images']:
            for filename in self.iterfilename(str(self.getSubDir(subdir)), prefix, fsn, '.cbf'):
                try:
                    return readcbf(filename)
                except FileNotFoundError:
                    pass
        raise FileNotFoundError(expfilename)


    @staticmethod
    def loadH5(h5file: str, samplename: str, distkey: str) -> Exposure:
        with h5py.File(h5file, 'r', swmr=True) as h5:
            grp = h5['Samples'][samplename][distkey]
            assert isinstance(grp, h5py.Group)
            header = Header(datadict={})
            header.beamposrow=(grp.attrs['beamcentery'], grp.attrs['beamcentery.err'])
            header.beamposcol=(grp.attrs['beamcenterx'], grp.attrs['beamcenterx.err'])
            header.flux = (grp.attrs['flux'], grp.attrs['flux.err'])
            header.samplex = (grp.attrs['samplex'], grp.attrs['samplex.err'])
            header.sampley = (grp.attrs['sampley'], grp.attrs['sampley.err'])
            header.temperature = (grp.attrs['temperature'], grp.attrs['temperature.err'])
            header.thickness = (grp.attrs['thickness'], grp.attrs['thickness.err'])
            header.transmission = (grp.attrs['transmission'], grp.attrs['transmission.err'])
            header.vacuum = (grp.attrs['vacuum'], grp.attrs['vacuum.err'])
            header.fsn = grp.attrs['fsn']
            header.fsn_absintref = grp.attrs['fsn_absintref']
            header.fsn_emptybeam = grp.attrs['fsn_emptybeam']
            header.maskname = grp.attrs['maskname']
            header.project = grp.attrs['project']
            header.username = grp.attrs['username']
            header.title = grp.attrs['title']
            header.distance = (grp.attrs['distance'], list(grp['curves'].values())[0].attrs['distance.err'])
            header.distancedecreaase = (grp.attrs['distancedecrease'], list(grp['curves'].values())[0].attrs['distancedecrease.err'])
            header.pixelsize = (grp.attrs['pixelsizex'], list(grp['curves'].values())[0].attrs['pixelsizex.err'])
            header.wavelength = (grp.attrs['wavelength'], list(grp['curves'].values())[0].attrs['wavelength.err'])
            header.sample_category = grp.attrs['sample_category']
            header.startdate = grp.attrs['startdate']
            header.enddate = grp.attrs['enddate']
            header.exposuretime = (grp.attrs['exposuretime'], grp.attrs['exposuretime.err'])
            header.absintfactor = (grp.attrs['absintfactor'], grp.attrs['absintfactor.err'])
            intensity = np.array(grp['image'], dtype=np.double)
            uncertainty = np.array(grp['image_uncertainty'], dtype=np.double)
            mask = np.array(grp['mask'], dtype=np.uint8)
            return Exposure(intensity, header, uncertainty, mask)

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
        for subdir in ['param_override', 'param'] if raw else ['eval2d']:
            for filename in self.iterfilename(str(self.getSubDir(subdir)), prefix, fsn, '.pickle'):
                logger.debug(f'Trying path {filename}')
                try:
                    return Header(filename=filename)
                except FileNotFoundError:
                    pass
        raise FileNotFoundError(self.formatFileName(prefix, fsn, '.pickle'))

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
                logger.debug(f'Mask file for name {maskname} loaded from {maskfile}')
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
        return self._masks[maskname][1]

    def invalidateMaskCache(self):
        self._masks = {}

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
