import logging
import time
from multiprocessing.synchronize import Lock
from typing import List, Union, Dict, Any, Optional

import h5py
import numpy as np
from sastool.classes2 import Curve
from sastool.io.credo_cpth5 import Exposure

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class LockedHDF5File:
    def __init__(self, lock: Lock, filename:str, *args, **kwargs):
        self._lock = lock
        self._filename = filename
        self._args = args
        self._kwargs = kwargs
        self._h5: Optional[h5py.File] = None

    def __enter__(self) -> h5py.File:
        logger.debug('Acquiring HDF5 lock...')
        t0 = time.monotonic()
        self._lock.acquire()
        logger.debug('Acquired HDF5 lock after {:.3f} seconds'.format(time.monotonic() - t0))
        self._h5 = h5py.File(self._filename, *self._args, **self._kwargs)
        return self._h5

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._h5.close()
        logger.debug('Releasing HDF5 lock...')
        self._lock.release()



class H5Reader:
    h5filename: str = None
    h5lock: Lock = None

    def __init__(self, h5filename: str, lock: Lock):
        self.h5filename = h5filename
        self.h5lock = lock

    def samples(self) -> List[str]:
        try:
            with LockedHDF5File(self.h5lock, self.h5filename, 'r', swmr=True) as f:
                return list(f['Samples'].keys())
        except OSError:
            return []

    def distanceKeys(self, sample: str) -> List[str]:
        try:
            with LockedHDF5File(self.h5lock, self.h5filename, 'r', swmr=True) as f:
                return list(f['Samples'][sample].keys())
        except OSError:
            return []

    def averagedImage(self, sample: str, distance: Union[float, str]) -> Exposure:
        with LockedHDF5File(self.h5lock, self.h5filename, 'r', swmr=True) as f:
            return Exposure.new_from_group(
                f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance])

    def averagedCurve(self, sample: str, distance: Union[float, str]) -> Curve:
        with LockedHDF5File(self.h5lock, self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance]
            return Curve(np.array(group['curve'][:, 0]),
                         np.array(group['curve'][:, 1]),
                         np.array(group['curve'][:, 2]),
                         np.array(group['curve'][:, 3]))

    def averagedHeaderDict(self, sample: str, distance: Union[float, str]) -> Dict[str, Any]:
        with LockedHDF5File(self.h5lock, self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance]
            return dict(**group.attrs)

    def allCurves(self, sample: str, distance: Union[float, str]) -> Dict[int, Curve]:
        dic = {}
        with LockedHDF5File(self.h5lock, self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance][
                'curves']
            for fsn in group:
                dic[int(fsn)] = Curve(
                    np.array(group[fsn][:, 0]),
                    np.array(group[fsn][:, 1]),
                    np.array(group[fsn][:, 2]),
                    np.array(group[fsn][:, 3]))
        return dic

    def badFSNs(self, sample: str, distance: Union[float, str]) -> List[int]:
        lis = []
        with LockedHDF5File(self.h5lock, self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance][
                'curves']
            for fsn in group:
                if group[fsn].attrs['correlmat_bad']:
                    lis.append(group[fsn].attrs['fsn'])
        return lis

    def getCurveParameter(self, sample: str, distance: Union[float, str], parname: str) -> Dict[int, Any]:
        dic = {}
        with LockedHDF5File(self.h5lock, self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance][
                'curves']
            for fsn in group:
                dic[group[fsn].attrs['fsn']] = group[fsn].attrs[parname]
        return dic

    def getCorrMat(self, sample: str, distance: Union[float, str]) -> np.ndarray:
        with LockedHDF5File(self.h5lock, self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance]
            return np.array(group['correlmatrix'])

    def getCurve(self, sample: str, distance: Union[float, str], fsn: int) -> Curve:
        with LockedHDF5File(self.h5lock, self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance][
                'curves']
            fsn = str(fsn)
            return Curve(np.array(group[fsn][:, 0]),
                         np.array(group[fsn][:, 1]),
                         np.array(group[fsn][:, 2]),
                         np.array(group[fsn][:, 3]))
