import logging
import os
from typing import List, Dict

import numpy as np
from sastool.io.credo_cct import Header, Exposure
from scipy.io import loadmat

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Loader:
    """Transparent loading of headers, exposures and masks"""
    rootdir: str   # data root directory
    fsndigits: int=5 # number of digits in the FSN part of the filename
    masks: Dict[str, np.ndarray] # mask cache
    prefix: str # file prefix, e.g. 'crd'
    filenameformat: str # file name format string: constructed from the prefix and the number of FSN digits
    subsubdircount: int # number of sub-subdirectories to search for
    subsubdirs: Dict[str, List[str]] # existing 2nd level subdirectories in dataroot for each subdir

    def __init__(self, rootdir: str, prefix: str='crd', fsndigits:int=5, subsubdircount:int=30):
        self.rootdir = rootdir
        self.masks = {}
        self.prefix=prefix
        self.subsubdircount=subsubdircount
        self.fsndigits=fsndigits
        self.filenameformat='{}_{{:0{}d}}'.format(self.prefix, self.fsndigits)
        self.regenerateSubSubdirList()

    def regenerateSubSubdirList(self):
        self.subsubdirs = {}
        logger.debug('Re-generating subsubdir lists. Root directory: "{}"'.format(self.rootdir))
        for subdir in ['eval2d', 'images', 'param']:
            subsubdirs=['', self.prefix] + \
                       [self.prefix+'_'+str(i) for i in range(self.subsubdircount)] + \
                       [self.prefix+str(i) for i in range(self.subsubdircount)]
            self.subsubdirs[subdir] = [d for d in subsubdirs if os.path.isdir(os.path.join(self.rootdir, subdir, d))]
            logger.debug('SubSubdirs for subdir {}: {}'.format(subdir, ', '.join(['"{}"'.format(x) for x in self.subsubdirs[subdir]])))

    def loadMask(self, maskname: str, forceReload: bool = False) -> np.ndarray:
        """Load a mask from a file"""
        logger.debug('Loading mask for {}'.format(maskname))
        try:
            if forceReload:
                raise KeyError()
            return self.masks[maskname]
        except KeyError:
            logger.debug('Mask not found in cache.')
            for dirpath, dirnames, filenames in os.walk(os.path.join(self.rootdir, 'mask')):
                try:
                    filename = os.path.join(
                        dirpath, [f for f in filenames if
                                  (f == maskname) or (f.upper() + '.MAT' == maskname.upper())][0])
                    break
                except IndexError:
                    pass
            else:
                raise FileNotFoundError(maskname)
            maskfile = loadmat(filename)
            logger.debug('Mask {} found in file {}'.format(maskname, maskfile))
            maskkey = [k for k in maskfile if not (k.startswith('_') or k.endswith('_'))][0]
            logger.debug('Mask key is {}'.format(maskkey))
            self.masks[maskname] = maskfile[maskkey]
            return self.masks[maskname]

    def loadHeader(self, fsn:int) -> Header:
        logger.debug('Loading header {}'.format(fsn))
        for extn in ['.pickle', '.pickle.gz']:
            filename = self.filenameformat.format(fsn)+extn
            for sd in self.subsubdirs['eval2d']:
                logger.debug('  - Trying subdir "{}"\n'.format(os.path.join(self.rootdir, 'eval2d', sd)))
                try:
                    return Header.new_from_file(os.path.join(self.rootdir, 'eval2d', sd, filename))
                except FileNotFoundError:
                    continue
        raise FileNotFoundError(self.filenameformat.format(fsn)+'.pickle')

    def loadExposure(self, fsn:int) -> Exposure:
        filename = self.filenameformat.format(fsn)+'.npz'
        logger.debug('Loading exposure {}'.format(fsn))
        header = self.loadHeader(fsn)
        mask = self.loadMask(header.maskname)
        logger.debug('Starting the actual loading of the exposure')
        for sd in self.subsubdirs['eval2d']:
            logger.debug('  - Trying subdir "{}"\n'.format(os.path.join(self.rootdir, 'eval2d', sd)))
            try:
                return Exposure.new_from_file(os.path.join(self.rootdir, 'eval2d', sd, filename), header, mask)
            except FileNotFoundError:
                continue
        raise FileNotFoundError(filename)
