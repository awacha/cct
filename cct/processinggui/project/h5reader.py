from typing import List, Union, Dict, Any

import h5py
import numpy as np
from sastool.classes2 import Curve
from sastool.io.credo_cpth5 import Exposure


class H5Reader:
    h5filename: str = None

    def __init__(self, h5filename: str):
        self.h5filename = h5filename

    def samples(self) -> List[str]:
        try:
            with h5py.File(self.h5filename, 'r', swmr=True) as f:
                return list(f['Samples'].keys())
        except OSError:
            return []

    def distanceKeys(self, sample: str) -> List[str]:
        try:
            with h5py.File(self.h5filename, 'r', swmr=True) as f:
                return list(f['Samples'][sample].keys())
        except OSError:
            return []

    def averagedImage(self, sample: str, distance: Union[float, str]) -> Exposure:
        with h5py.File(self.h5filename, 'r', swmr=True) as f:
            return Exposure.new_from_group(
                f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance])

    def averagedCurve(self, sample: str, distance: Union[float, str]) -> Curve:
        with h5py.File(self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance]
            return Curve(np.array(group['curve'][:, 0]),
                         np.array(group['curve'][:, 1]),
                         np.array(group['curve'][:, 2]),
                         np.array(group['curve'][:, 3]))

    def allCurves(self, sample: str, distance: Union[float, str]) -> Dict[int, Curve]:
        dic = {}
        with h5py.File(self.h5filename, 'r', swmr=True) as f:
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
        with h5py.File(self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance][
                'curves']
            for fsn in group:
                if group[fsn].attrs['correlmat_bad']:
                    lis.append(group[fsn].attrs['fsn'])
        return lis

    def getCurveParameter(self, sample: str, distance: Union[float, str], parname: str) -> Dict[int, Any]:
        dic = {}
        with h5py.File(self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance][
                'curves']
            for fsn in group:
                dic[group[fsn].attrs['fsn']] = group[fsn].attrs[parname]
        return dic

    def getCorrMat(self, sample: str, distance: Union[float, str]) -> np.ndarray:
        with h5py.File(self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance]
            return np.array(group['correlmatrix'])

    def getCurve(self, sample: str, distance: Union[float, str], fsn: int) -> Curve:
        with h5py.File(self.h5filename, 'r', swmr=True) as f:
            group = f['Samples'][sample]['{:.2f}'.format(distance) if isinstance(distance, float) else distance][
                'curves']
            fsn = str(fsn)
            return Curve(np.array(group[fsn][:, 0]),
                         np.array(group[fsn][:, 1]),
                         np.array(group[fsn][:, 2]),
                         np.array(group[fsn][:, 3]))
