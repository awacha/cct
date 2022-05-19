import logging
import os
import pathlib
import re

import shutil
from typing import Dict, Tuple, Optional, List, Iterator

import h5py
import numpy as np
from PyQt5 import QtCore
from scipy.io import loadmat

from .component import Component
from ...algorithms.readcbf import readcbf
from ...dataclasses import Exposure, Header
from ...config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def mywalkdir(root: str):
    """A faster version of os.walk().

    Caveat: directory entries containing '.' are assumed to be files!
    """
    logger.debug(f'Entering mywalkdir with root {root}')
    try:
        filelist = os.listdir(root)
    except FileNotFoundError:
        return
    possibledirs = [f for f in filelist if ('.' not in f)]
    dirs = [d for d in possibledirs if os.path.isdir(os.path.join(root, d))]
    files = [f for f in filelist if f not in dirs]
    logger.debug(f'Yielding {root} from mywalkdir')
    yield root, dirs, files
    logger.debug(f'Yielding subdirectories from mywalkdir(root={root})')
    for dir_ in dirs:
        yield from mywalkdir(os.path.join(root, dir_))
    logger.debug(f'Exiting mywalkdir(root={root}')


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

    def startComponent(self):
        self.reindex()
        super().startComponent()

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
        for subdir, extension in [
            ('images', 'cbf'), ('images_local', 'cbf'), ('param', 'pickle'), ('param_override', 'pickle'),
            ('eval2d', 'npz'), ('eval1d', 'txt')]:
            # find all subdirectories in `directory`, including `directory`
            # itself
            directory = self.getSubDir(subdir)
            logger.debug(f'Reindexing subdirectory {directory}')
            filename_regex = re.compile(rf'^(?P<prefix>\w+)_(?P<fsn>\d+)\.{extension}$')
            for folder, subdirs, files in os.walk(str(directory)):
                logger.debug(f'Looking in folder {folder}')
                # find all files
                matchlist = [m for m in [filename_regex.match(f) for f in files] if m is not None]
                # find all file prefixes, like 'crd', 'tst', 'tra', 'scn', etc.
                prefixes = {m.group('prefix') for m in matchlist}
                for prefix in prefixes:
                    logger.debug(f'Checking prefix {prefix}')
                    if prefix not in self._lastfsn:
                        self._lastfsn[prefix] = None
                    # find the highest available FSN of the current prefix in
                    # this directory
                    maxfsn = max([int(m.group('fsn')) for m in matchlist if m.group('prefix') == prefix])
                    logger.debug(f'Maxfsn is {maxfsn}')
                    if self._lastfsn[prefix] is None or (maxfsn > self._lastfsn[prefix]):
                        logger.debug(f'Updating lastfsn for prefix {prefix} to {maxfsn}')
                        self._lastfsn[prefix] = maxfsn
                logger.debug(f'All prefixes done in this folder ({folder})')
            logger.debug('All folders done.')

        logger.debug('Creating empty prefixes')
        # add known prefixes to self._lastfsn if they were not yet added.
        for prefix in self.config['path']['prefixes'].values():
            if prefix not in self._lastfsn:
                self._lastfsn[prefix] = None
            else:
                self.lastFSNChanged.emit(prefix, self._lastfsn[prefix])

        # update self._nextfsn
        logger.debug('Updating nextfsn.')
        for prefix in self._lastfsn:
            self._nextfsn[prefix] = self._lastfsn[prefix] + 1 if self._lastfsn[prefix] is not None else 0
            self.nextFSNChanged.emit(prefix, self._nextfsn[prefix])
        logger.info('Reindexing done.')

    def imageReceived(self, prefix:str, fsn: int):
        if prefix not in self._lastfsn:
            self._lastfsn[prefix] = fsn
            self.lastFSNChanged.emit(prefix, fsn)
        elif (self._lastfsn[prefix] is None) or (self._lastfsn[prefix] < fsn):
            self._lastfsn[prefix] = fsn
            self.lastFSNChanged.emit(prefix, fsn)
        else:
            # sometimes multiple exposures made in short periods can mix up
            logger.warning(
                f'Exposure received for prefix {prefix} with fsn {fsn}, which is smaller than the current '
                f'highest fsn on file: {self._lastfsn[prefix]}')
        if prefix not in self._nextfsn:
            self._nextfsn[prefix] = fsn+1
        elif self._lastfsn[prefix] + 1 > self._nextfsn[prefix]:
            self._nextfsn[prefix] = self._lastfsn[prefix] + 1
        self.nextFSNChanged.emit(prefix, self._nextfsn[prefix])

    def nextfsn(self, prefix: str, checkout: int = 0) -> int:
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
            self._nextfsn[prefix] += checkout
            self.nextFSNChanged.emit(prefix, self._nextfsn[prefix])
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
        yield os.path.join(subdir, f'{prefix}{fsn // 10000}', filename)
        yield os.path.join(subdir, f'{prefix}_{fsn // 10000}', filename)

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
        if not header.maskname:
            # no mask defined: create a dummy mask
            mask = None
        else:
            mask = self.loadMask(header.maskname)
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
                        uncertainty = intensity ** 0.5
                        uncertainty[intensity <= 0] = 1
                        if (subdir == 'images') and raw:
                            # try to copy this image to the images_local directory
                            os.makedirs(os.path.join(self.getSubDir('images_local'), prefix), exist_ok=True)
                            logger.debug(f'Copying {filename} to images_local.')
                            shutil.copy2(filename, os.path.join(self.getSubDir('images_local'), prefix, os.path.split(filename)[-1]))
                    elif filename.lower().endswith('.npz'):
                        data = np.load(filename)
                        intensity = data['Intensity']
                        uncertainty = data['Uncertainty']
                    else:
                        logger.error(filename)
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
            header.beamposrow = (grp.attrs['beamcentery'], grp.attrs['beamcentery.err'])
            header.beamposcol = (grp.attrs['beamcenterx'], grp.attrs['beamcenterx.err'])
            try:
                header.flux = (grp.attrs['flux'], grp.attrs['flux.err'])
            except KeyError:
                header.flux = (0.0, 0.0)
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
            header.distancedecreaase = (
            grp.attrs['distancedecrease'], list(grp['curves'].values())[0].attrs['distancedecrease.err'])
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

    def loadMask(self, maskname: Optional[str]) -> Optional[np.array]:
        """Load a mask

        The 'mask' subdirectory is traversed recursively. The first file with matching name is found.

        A cache of mask matrices is kept; whenever a mask changes on disk, it is reloaded.

        :param maskname: name of the mask (file name with or without extension)
        :type maskname: str
        :return: the mask
        :rtype: np.ndarray (2 dimensions, dtype np.uint8)
        """
        mask = None
        maskname = os.path.split(maskname)[-1]
        if maskname not in self._masks:
            for folder, dirnames, filenames in os.walk(str(self.getSubDir('mask'))):
                logger.debug(f'Looking for mask {maskname=} in folder {folder=}')
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

    def loadFromConfig(self):
        if isinstance(self.config, Config):
            self.config.blockSignals(True)
        try:
            for configpath, defaultvalue in [
                (('path', 'directories', 'log'), 'log'),
                (('path', 'directories', 'images'), 'images'),
                (('path', 'directories', 'images_local'), 'images_local'),
                (('path', 'directories', 'param'), 'param'),
                (('path', 'directories', 'config'), 'config'),
                (('path', 'directories', 'mask'), 'mask'),
                (('path', 'directories', 'nexus'), 'nexus'),
                (('path', 'directories', 'eval1d'), 'eval1d'),
                (('path', 'directories', 'eval2d'), 'eval2d'),
                (('path', 'directories', 'param_override'), 'param_override'),
                (('path', 'directories', 'scan'), 'scan'),
                (('path', 'directories', 'status'), 'status'),
                (('path', 'directories', 'scripts'), 'scripts'),
                (('path', 'directories', 'images_detector'), ['/disk2/images', '/home/det/p2_det/images']),
                (('path', 'fsndigits'), 5),
                (('path', 'prefixes', 'crd'), 'crd'),
                (('path', 'prefixes', 'scn'), 'scn'),
                (('path', 'prefixes', 'tra'), 'tra'),
                (('path', 'prefixes', 'tst'), 'tst'),
                (('path', 'prefixes', 'gsx'), 'gsx'),
                (('path', 'prefixes', 'map'), 'map'),
                (('path', 'varlogfile'), 'varlog.log'),
            ]:
                cnf = self.config
                for pathelement in configpath[:-1]:
                    if pathelement not in cnf:
                        cnf[pathelement] = {}
                    cnf = cnf[pathelement]
                if configpath[-1] not in cnf:
                    cnf[configpath[-1]] = defaultvalue
        finally:
            if isinstance(self.config, Config):
                self.config.blockSignals(False)
