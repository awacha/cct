import logging
import multiprocessing.synchronize
from typing import List, Optional, Final

import dateutil.parser
import h5py
import numpy as np

from ..dataclasses import Exposure, Header, Curve

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ProcessingH5File:
    filename: str
    lock: multiprocessing.synchronize.Lock
    handle: h5py.File
    groupname: Optional[str] = None

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
                     group: Optional[str] = None):
            self.filename = filename
            self.lock = lock
            self.writable = writable
            self.handle = None
            self.groupname = group

        def __enter__(self) -> h5py.File:
            try:
                if self.writable:
                    self.lock.acquire()
                    self.handle = h5py.File(self.filename, 'w')
                    self.handle.swmr_mode = True
                else:
                    self.handle = h5py.File(self.filename, 'r', swmr=True)
                return self.handle if self.groupname is None else self.handle.require_group(self.groupname)
            except:
                try:
                    self.handle.close()
                finally:
                    self.handle = None
                    if self.writable:
                        self.lock.release()
                raise

        def __exit__(self, exc_type, exc_val, exc_tb):
            try:
                self.handle.close()
            finally:
                self.handle = None
                if self.writable:
                    self.lock.release()

    def __init__(self, filename: str, lock: Optional[multiprocessing.synchronize.Lock] = None):
        self.filename = filename
        self.lock = multiprocessing.Lock() if lock is None else lock

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
        with self.reader() as h5file:
            try:
                lis = []
                for g in h5file[f'Samples/{samplename}']:
                    try:
                        lis.append(float(g))
                    except ValueError:
                        pass
                return lis
            except KeyError:
                return []

    def addDistance(self, samplename: str, distance: float):
        with self.writer() as h5file:
            h5file.require_group(f'Samples/{samplename}/{distance:.2f}')

    def removeDistance(self, samplename: str, distance: float):
        with self.writer() as h5file:
            try:
                del h5file[f'Samples/{samplename}/{distance:.2f}']
            except KeyError:
                pass

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
        ds = maskgroup.create_dataset(exposure.header.maskname, exposure.mask.shape, exposure.mask.dtype, exposure.mask,
                                      compression='lzf', fletcher32=True, shuffle=True)
        group['mask'] = h5py.SoftLink(f'/masks/{exposure.header.maskname}')
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
        })
        for attribute in self._value_and_error_header_fields:
            try:
                group.attrs[attribute] = getattr(header, attribute)[0]
                group.attrs[f'{attribute}.err'] = getattr(header, attribute)[1]
            except KeyError as ke:
                logger.debug(f'Cannot write attribute {attribute} because of KeyError {ke}')
        for attribute in self._datetime_header_fields:
            group.attrs[attribute] = str(getattr(header, attribute))
        for attribute in self._as_is_header_fields:
            try:
                group.attrs[attribute] = getattr(header, attribute)
            except KeyError:
                logger.debug(f'Cannot write attribute {attribute} because of KeyError {ke}')

    def writeCurve(self, curve: Curve, group: h5py.Group, name: str):
        try:
            del group[name]
        except KeyError:
            pass
        array = curve.asArray()
        group.create_dataset(name, array.shape, array.dtype, array)

    def readCurve(self, path: str) -> Curve:
        with self.reader(path) as grp:
            assert isinstance(grp, h5py.Dataset)
            return Curve.fromArray(np.array(grp))

    def readHeader(self, group: str) -> Header:
        with self.reader(group) as grp:
            assert isinstance(grp, h5py.Group)
            header = Header(datadict={})
            for attribute in self._as_is_header_fields:
                try:
                    setattr(header, attribute, grp.attrs[attribute])
                except KeyError:
                    pass
            for attribute in self._datetime_header_fields:
                try:
                    setattr(header, attribute, dateutil.parser.parse(grp.attrs[attribute]))
                except (dateutil.parser.InvalidDatetimeError, KeyError):
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

            header.beamposrow = (grp.attrs['beamcentery'], grp.attrs['beamcentery.err'])
            header.beamposcol = (grp.attrs['beamcenterx'], grp.attrs['beamcenterx.err'])
            header.pixelsize = (grp.attrs['pixelsizex'], grp.attrs['pixelsizex.err'])
            return header

    def readExposure(self, group: str) -> Exposure:
        header = self.readHeader(group)
        with self.reader(group) as grp:
            intensity = np.array(grp['image'])
            unc = np.array(grp['image_uncertainty'])
            mask = np.array(grp['mask'])
            return Exposure(intensity, header, unc, mask)
