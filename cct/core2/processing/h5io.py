import logging
import multiprocessing.synchronize
import os
from typing import List, Optional, Final, Union, Tuple, Dict, Any

import dateutil.parser
import h5py
import numpy as np

from ..dataclasses import Exposure, Header, Curve
from .calculations.outliertest import OutlierTest, OutlierMethod

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ProcessingH5File:
    filename: str
    lock: multiprocessing.synchronize.Lock
    handle: h5py.File
    groupname: Optional[str] = None
    swmr: bool = False

    _value_and_error_header_fields: Final[List[str]] = \
        ['distance', 'distancedecrease', 'dark_cps', 'wavelength', 'exposuretime', 'absintfactor',
         'beamposrow', 'beamposcol', 'flux', 'samplex', 'sampley', 'temperature', 'thickness',
         'transmission', 'vacuum']

    _as_is_header_fields: Final[List[str]] = [
        'title', 'sample_category', 'fsn', 'fsn_absintref', 'fsn_dark', 'fsn_emptybeam', 'maskname', 'username',
        'project', 'prefix', 'absintqmin', 'absintqmax', 'absintdof', 'absintchi2']

    _datetime_header_fields: Final[List[str]] = ['date', 'startdate', 'enddate']

    class Handler:
        def __init__(self, filename: str, lock: multiprocessing.synchronize.Lock, writable: bool = True,
                     group: Optional[str] = None, swmr: bool=False):
            self.swmr = swmr
            self.filename = filename
            self.lock = lock
            self.writable = writable
            self.handle = None
            self.groupname = group

        def __enter__(self) -> h5py.File:
            try:
                self.lock.acquire()
                if self.writable:
                    self.handle = h5py.File(self.filename, 'a')
                    if self.swmr:
                        self.handle.swmr_mode = True
                else:
                    self.handle = h5py.File(self.filename, 'r', swmr=self.swmr)
                if self.groupname is None:
                    return self.handle
                elif self.writable:
                    self.handle.require_group(self.groupname)
                return self.handle[self.groupname]
            except:
                try:
                    if self.handle is not None:
                        self.handle.close()
                finally:
                    self.handle = None
                    self.lock.release()
                raise

        def __exit__(self, exc_type, exc_val, exc_tb):
            try:
                if self.handle is not None:
                    self.handle.close()
            finally:
                self.handle = None
                self.lock.release()

    def __init__(self, filename: str, lock: Optional[multiprocessing.synchronize.Lock] = None):
        self.filename = filename
        self.lock = multiprocessing.Lock() if lock is None else lock
        with self.lock:
            with h5py.File(filename, 'a') as h5:
                # ensure that the file is present.
                h5.require_group('Samples')

    def writer(self, group: Optional[str] = None):
        return self.Handler(self.filename, self.lock, writable=True, group=group)

    def reader(self, group: Optional[str] = None):
        return self.Handler(self.filename, self.lock, writable=False, group=group)

    def samplenames(self) -> List[str]:
        with self.reader() as h5file:
            if 'Samples' not in h5file:
                return []
            return list(h5file['Samples'].keys())

    def addSample(self, samplename: str):
        with self.writer() as h5file:
            h5file.require_group('Samples')
            h5file['Samples'].require_group(samplename)

    def removeSample(self, samplename: str):
        with self.writer() as h5file:
            h5file.require_group('Samples')
            del h5file['Samples'][samplename]

    def distances(self, samplename: str) -> List[float]:
        return [float(x) for x in self.distancekeys(samplename)]

    def distancekeys(self, samplename: str, onlynumeric: bool=True) -> List[str]:
        with self.reader() as h5file:
            try:
                lis = []
                for g in h5file[f'Samples/{samplename}']:
                    try:
                        logger.debug(f'Distance key: {g}')
                        if onlynumeric:
                            float(g)
                        lis.append(g)
                    except ValueError:
                        pass
                return lis
            except KeyError:
                return []

    def addDistance(self, samplename: str, distance: Union[float, str]) -> Tuple[str, str]:
        if isinstance(distance, float):
            distance = f'{distance:.2f}'
        with self.writer() as h5file:
            h5file.require_group(f'Samples/{samplename}/{distance}')
        return (samplename, distance)

    def removeDistance(self, samplename: str, distance: Union[float, str]):
        if isinstance(distance, float):
            distance = f'{distance:.2f}'
        with self.writer() as h5file:
            try:
                del h5file[f'Samples/{samplename}/{distance}']
            except KeyError:
                pass

    def pruneSamplesWithNoDistances(self):
        for samplename in self.samplenames():
            if not self.distancekeys(samplename):
                self.removeSample(samplename)

    def writeExposure(self, exposure: Exposure, group: h5py.Group):
        for key in ['image', 'image_uncertainty']:
            try:
                del group[key]
            except KeyError:
                pass
        group.create_dataset(
            'image',
            exposure.intensity.shape,
            exposure.intensity.dtype,
            exposure.intensity, compression='lzf', fletcher32=True, shuffle=True)
        group.create_dataset(
            'image_uncertainty',
            exposure.uncertainty.shape,
            exposure.uncertainty.dtype,
            exposure.uncertainty, compression='lzf', fletcher32=True, shuffle=True
        )
        maskgroup = group.file.require_group('masks')
        try:
            del maskgroup[exposure.header.maskname]
        except KeyError:
            pass
        dsname = os.path.split(exposure.header.maskname)[-1]
        if dsname not in maskgroup:
            maskgroup.create_dataset(os.path.split(exposure.header.maskname)[-1],
                                     exposure.mask.shape, exposure.mask.dtype, exposure.mask,
                                     compression='lzf', fletcher32=True, shuffle=True)
        else:
            # the mask is already present
            # ToDo: check if it the same as the current one.
            pass
        if 'mask' in group:
            del group['mask']
        group['mask'] = h5py.SoftLink(f'/masks/{os.path.split(exposure.header.maskname)[-1]}')
        self.writeHeader(exposure.header, group)

    def writeHeader(self, header: Header, group: h5py.Group):
        group.attrs.update({
            'pixelsizex': header.pixelsize[0],
            'pixelsizey': header.pixelsize[0],
            'pixelsizex.err': header.pixelsize[1],
            'pixelsizey.err': header.pixelsize[1],
            'beamcenterx': header.beamposcol[0],
            'beamcentery': header.beamposrow[0],
            'beamcenterx.err': header.beamposcol[1],
            'beamcentery.err': header.beamposrow[1],
            'exposurecount': header.exposurecount,
        })
        for attribute in self._value_and_error_header_fields:
            try:
                group.attrs[attribute] = getattr(header, attribute)[0]
                group.attrs[f'{attribute}.err'] = getattr(header, attribute)[1]
            except KeyError as ke:
                logger.warning(f'Cannot write attribute {attribute} because of KeyError {ke}')
        for attribute in self._datetime_header_fields:
            group.attrs[attribute] = str(getattr(header, attribute))
        for attribute in self._as_is_header_fields:
            try:
                group.attrs[attribute] = getattr(header, attribute)
            except KeyError:
                logger.warning(f'Cannot write attribute {attribute} because of KeyError {ke}')

    def writeCurve(self, curve: Union[Curve, np.ndarray], group: h5py.Group, name: str):
        try:
            del group[name]
        except KeyError:
            pass
        if isinstance(curve, Curve):
            array = curve.asArray()
        else:
            array = curve
        group.create_dataset(name, shape=array.shape, dtype=array.dtype, data=array)

    def readCurve(self, path: str) -> Curve:
        logger.debug(f'Reading curve from {path=}')
        with self.reader(path) as grp:
            assert isinstance(grp, h5py.Dataset)
            return Curve.fromArray(np.array(grp))

    def readHeader(self, group: str) -> Header:
        with self.reader(group) as grp:
            #assert isinstance(grp, h5py.Group)
            header = Header(datadict={})
            for attribute in self._as_is_header_fields:
                try:
                    setattr(header, attribute, grp.attrs[attribute])
                except KeyError:
                    pass
            for attribute in self._datetime_header_fields:
                try:
                    s = grp.attrs[attribute]
                    if isinstance(s, str):
                        setattr(header, attribute, dateutil.parser.parse(grp.attrs[attribute]))
                    else:
                        raise ValueError(s, type(s))
                except (dateutil.parser.ParserError, KeyError):
                    pass
            for attribute in self._value_and_error_header_fields:
                try:
                    val = float(grp.attrs[attribute])
                except (KeyError, ValueError):
                    continue
                try:
                    unc = float(grp.attrs[attribute + '.err'])
                except (KeyError, ValueError):
                    unc = 0.0
                setattr(header, attribute, (val, unc))
            try:
                header.exposurecount = grp.attrs['exposurecount']
            except KeyError:
                try:
                    header.exposurecount = len(grp['curves'])
                except KeyError:
                    header.exposurecount = 1

            def getattr_failsafe(grp, name, default: Any):
                """grp.attrs.setdefault() does not work on read-only H5 files."""
                try:
                    return grp.attrs[name]
                except KeyError:
                    return default

            header.beamposrow = (
                getattr_failsafe(grp, 'beamcentery', np.nan),
                getattr_failsafe(grp, 'beamcentery.err', 0.0))
            header.beamposcol = (
                getattr_failsafe(grp, 'beamcenterx', np.nan),
                getattr_failsafe(grp, 'beamcenterx.err', 0.0))
            header.pixelsize = (
                getattr_failsafe(grp, 'pixelsizex', np.nan),
                getattr_failsafe(grp, 'pixelsizex.err', 0.0))
            return header

    def readExposure(self, group: str) -> Exposure:
        header = self.readHeader(group)
        with self.reader(group) as grp:
            intensity = np.array(grp['image'])
            unc = np.array(grp['image_uncertainty'])
            mask = np.array(grp['mask'])
            return Exposure(intensity, header, unc, mask)

    def readOutlierTest(self, group: str) -> OutlierTest:
        with self.reader(group) as grp:
            cmat = np.array(grp['correlmatrix'])
            try:
                method = OutlierMethod(grp['correlmatrix'].attrs['method'])
            except KeyError:
                method = OutlierMethod.IQR
            try:
                threshold = float(grp['correlmatrix'].attrs['threshold'])
            except KeyError:
                threshold = 1.5
            fsns = sorted([int(s) for s in grp['curves']])
            return OutlierTest(method=method, threshold=threshold, correlmatrix=cmat, fsns=fsns)

    def writeOutlierTest(self, group: str, ot: OutlierTest):
        with self.writer(group) as grp:
            if 'correlmatrix' in grp:
                del grp['correlmatrix']
            ds = grp.create_dataset('correlmatrix', data=ot.correlmatrix, compression='lzf', shuffle=True, fletcher32=True)
            ds.attrs['method'] = ot.method.value
            ds.attrs['threshold'] = ot.threshold

    def items(self) -> List[Tuple[str, str]]:
        lis = []
        with self.reader('Samples') as grp:
            for sn in grp:
                for dist in grp[sn]:
                    lis.append((sn, dist))
        return lis

    def readCurves(self, group: str, readall: bool=False) -> Dict[int, Curve]:
        dic={}
        with self.reader(group) as grp:
            for fsn in grp['allcurves' if readall else 'curves']:
                dic[int(fsn)] = Curve.fromArray(np.array(grp[f'{"allcurves" if readall else "curves"}/{fsn}']))
        return dic

    def readHeaders(self, group: str, readall: bool=False) -> Dict[int, Header]:
        dic={}
        with self.reader(group) as grp:
            for fsn in grp['allcurves' if readall else 'curves']:
                dic[int(fsn)] = self.readHeader(f'{grp.name}/{"allcurves" if readall else "curves"}/{fsn}')
        return dic

    def readHeaderDict(self, group: str) -> Dict[str, Any]:
        with self.reader(group) as grp:
            return dict(**grp.attrs)

    def clear(self):
        for sample in self.samplenames():
            self.removeSample(sample)

    def __contains__(self, item: Tuple[str, str]) -> bool:
        with self.reader('Samples') as grp:
            return (item[0] in grp) and (item[1] in grp[item[0]])
