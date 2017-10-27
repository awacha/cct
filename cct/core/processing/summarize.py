import os
from typing import Iterable, List, Optional

import h5py
import numpy as np
from sastool.classes2 import Curve
from sastool.io.credo_cct import Header, Exposure
from sastool.misc.errorvalue import ErrorValue
from scipy.io import loadmat


def correlmatrix(grp: h5py.Group, std_multiplier: Optional[float] = None, logarithmic: bool = True):
    cm = np.zeros((len(grp), len(grp)), np.double)
    sortedkeys = sorted(grp.keys(), key=lambda x: int(x))
    for i in range(len(grp)):
        for j in range(i + 1, len(grp)):
            ds1 = grp[sortedkeys[i]]
            ds2 = grp[sortedkeys[j]]
            if logarithmic:
                idx = np.logical_and(np.logical_and(ds1[:, 2] > 0, ds2[:, 2] > 0),
                                     np.logical_and(ds1[:, 1] > 0, ds2[:, 1] > 0))
                if idx.sum() == 0:
                    cm[i, j] = cm[j, i] = np.nan
                    continue
                w = (ds1[idx, 2] / ds1[idx, 1]) ** 2 + (ds2[idx, 2] / ds2[idx, 1]) ** 2
                cm[i, j] = cm[j, i] = ((np.log(ds1[idx, 1]) - np.log(ds2[idx, 1])) ** 2 / w).sum() / (1 / w).sum()
            else:
                idx = np.logical_and(ds1[:, 2] > 0, ds2[:, 2] > 0)
                if idx.sum() == 0:
                    cm[i, j] = cm[j, i] = np.nan
                w = (ds1[idx, 2] ** 2 + ds2[idx, 2] ** 2)
                cm[i, j] = cm[j, i] = ((ds1[idx, 1] - ds2[idx, 1]) ** 2 / w).sum() / (1 / w).sum()
    rowavg = np.nanmean(cm, axis=0)
    for i in range(len(rowavg)):
        grp[sortedkeys[i]].attrs['correlmat_discrp'] = rowavg[i]
        grp[sortedkeys[i]].attrs['correlmat_rel_discrp'] = (rowavg[i] - np.median(rowavg)) / rowavg.std()
        grp[sortedkeys[i]].attrs['correlmat_bad'] = (rowavg[i] - np.median(rowavg)) > std_multiplier * rowavg.std()
    cm = cm + np.diagflat(rowavg)
    return cm


class Summarizer(object):
    def __init__(
            self, fsns: Iterable[int], exppath: Iterable[str],
            parampath: Iterable[str], maskpath: Iterable[str],
            outputfile: str, prefix: str = 'crd', ndigits: int = 5,
            errorpropagation: int = 3, abscissaerrorpropagation: int = 3,
            sanitize_curves: bool = True, logarithmic_correlmatrix: bool = True,
            std_multiplier: float = 2.7, qrange: Optional[np.ndarray] = None,
    ):
        self.fsns = fsns
        self.exppath = exppath
        self.parampath = parampath
        self.maskpath = maskpath
        self.outputfile = outputfile
        self.qrange = qrange
        self.prefix = prefix
        self.ndigits = ndigits
        self.errorpropagation = errorpropagation
        self.abscissaerrorpropagation = abscissaerrorpropagation
        self.sanitize_curves = sanitize_curves
        self.logarithmic_correlmatrix = logarithmic_correlmatrix
        self.std_multiplier = std_multiplier
        self._headers = []
        self._masks = {}

    def load_headers(self, yield_messages=False, logger=None):
        self._headers = []
        for f in self.fsns:
            for p in self.parampath:
                try:
                    self._headers.append(Header.new_from_file(
                        os.path.join(
                            p,
                            '{{}}_{{:0{:d}d}}.pickle'.format(self.ndigits).format(self.prefix, f))
                    ))
                    if yield_messages:
                        if logger is not None:
                            logger.debug('Header loaded for prefix {}, fsn {}'.format(self.prefix, f))
                        yield '__header_loaded__', f
                    break
                except FileNotFoundError:
                    pass
            else:
                if logger is not None:
                    logger.error('No header found for prefix {}, fsn {}.'.format(self.prefix, f))
                if yield_messages:
                    yield '__header_notfound__', f
        return None

    def get_mask(self, maskname: str, logger=None):
        try:
            return self._masks[maskname]
        except KeyError:
            pass
        for p in self.maskpath:
            try:
                m = loadmat(os.path.join(p, maskname))
            except FileNotFoundError:
                try:
                    m = loadmat(os.path.join(p, maskname + '.mat'))
                except FileNotFoundError:
                    continue
            self._masks[maskname] = m[[x for x in m.keys() if not x.startswith('_')][0]]
            return self._masks[maskname]
        else:
            if logger is not None:
                logger.error('Mask file {} not found.'.format(maskname))
            raise FileNotFoundError('Mask {} not found'.format(maskname))

    def load_exposure(self, fsn: int, logger=None) -> Exposure:
        header = [h for h in self._headers if h.fsn == fsn][0]
        mask = self.get_mask(header.maskname, logger=logger)
        for p in self.exppath:
            try:
                ex = Exposure.new_from_file(
                    os.path.join(
                        p,
                        '{{}}_{{:0{:d}d}}.npz'.format(self.ndigits).format(self.prefix, fsn)),
                    header, mask
                )
                return ex
            except FileNotFoundError:
                continue
        raise FileNotFoundError(fsn)

    def allsamplenames(self) -> List[str]:
        return sorted(set([h.title for h in self._headers]))

    def distances(self, samplename: str) -> List[int]:
        dists = set([float(h.distance) for h in self._headers if h.title == samplename])
        distances = []
        for d in dists:
            if not any([abs(d - d_) < 0.01 for d_ in distances]):
                distances.append(d)
        return distances

    def collect_exposures(self, samplename: str, distance: float, hdf5: h5py.File, yield_messages: bool = False,
                          logger=None):
        grp = hdf5.require_group('Samples/{}/{:.2f}'.format(samplename, distance))
        headers = [h for h in self._headers if
                   h.title == samplename and abs(float(h.distance) - float(distance)) < 0.01]
        group1d = grp.require_group('curves')
        dataset2d = None
        error2d = None
        curve = None
        yield '__init_collect_exposures__', len(headers)
        for h in sorted(headers, key=lambda h: h.fsn):
            assert isinstance(h, Header)
            yield '__ce_debug__', h.fsn
            try:
                ex = self.load_exposure(h.fsn, logger=logger)
                if yield_messages:
                    yield '__exposure_loaded__', h.fsn
            except FileNotFoundError:
                if yield_messages:
                    yield '__exposure_notfound__', h.fsn
                continue
            if dataset2d is None:
                dataset2d = ex.intensity
                error2d = ex.error ** 2
            else:
                dataset2d += ex.intensity
                error2d += ex.error ** 2
            if ex.header.maskname not in hdf5.require_group('masks'):
                hdf5.require_group('masks').create_dataset(ex.header.maskname, data=ex.mask)
            try:
                grp['mask'] = h5py.SoftLink('/masks/{}'.format(ex.header.maskname))
            except RuntimeError:
                pass
            curve = ex.radial_average(self.qrange,
                                      abscissa_errorpropagation=self.abscissaerrorpropagation,
                                      errorpropagation=self.errorpropagation)
            if self.sanitize_curves:
                curve = curve.sanitize()
            ds = group1d.create_dataset(
                '{{:0{:d}d}}'.format(self.ndigits).format(h.fsn),
                shape=(len(curve), 4), dtype=np.double)
            ds[:, 0] = curve.q
            ds[:, 1] = curve.Intensity
            ds[:, 2] = curve.Error
            ds[:, 3] = curve.qError
            for attr in ['beamcenterx', 'beamcentery', 'distance', 'pixelsizex', 'pixelsizey',
                         'wavelength', 'fsn', 'exposuretime', 'transmission', 'thickness', 'maskname',
                         'absintfactor', 'flux', 'date', 'distancedecrease', 'fsn_absintref',
                         'fsn_emptybeam', 'project', 'samplex', 'sampley', 'temperature', 'title', 'username',
                         'vacuum']:
                try:
                    a = getattr(h, attr)
                except (AttributeError, KeyError):
                    if logger is not None:
                        logger.warning('Missing attribute {} from header.'.format(attr))
                    continue
                if isinstance(a, ErrorValue):
                    ds.attrs[attr] = a.val
                    ds.attrs[attr + '.err'] = a.err
                elif isinstance(a, (float, int, bool, str)):
                    ds.attrs[attr] = a
                else:
                    ds.attrs[attr] = str(a)
        # copy parameters
        for attr in ['title', 'project', 'maskname', 'samplex', 'sampley', 'username']:
            for dsname in group1d:
                try:
                    grp.attrs[attr] = group1d[dsname].attrs[attr]
                    break
                except KeyError:
                    continue
            else:
                grp.attrs[attr] = None
        # average parameters
        for attr in ['beamcenterx', 'beamcentery', 'distance', 'pixelsizex', 'pixelsizey', 'wavelength',
                     'transmission', 'thickness', 'absintfactor', 'flux', 'distancedecrease']:
            try:
                grp.attrs[attr] = np.mean([group1d[dsname].attrs[attr] for dsname in group1d.keys()])
            except KeyError:
                pass
        # sum parameters
        for attr in ['exposuretime']:
            grp.attrs[attr] = np.sum([group1d[dsname].attrs[attr] for dsname in group1d.keys()])
        if curve is None:
            # no files have been loaded
            return
        grp.create_dataset('image', data=dataset2d / len(group1d))
        grp.create_dataset('image_uncertainty', data=(error2d / len(group1d)) ** 0.5)
        cavg = Curve.average(
            *[Curve(group1d[ds][:, 0], group1d[ds][:, 1], group1d[ds][:, 2], group1d[ds][:, 3]) for ds in
              group1d]).sanitize()
        dsavg = grp.create_dataset('curve_averaged', shape=(len(cavg), 4), dtype=np.double)
        dsavg[:, 0], dsavg[:, 1], dsavg[:, 2], dsavg[:, 3] = (cavg.q, cavg.Intensity, cavg.Error, cavg.qError)
        radavg = Exposure(np.array(grp['image']), np.array(grp['image_uncertainty']), headers[0],
                          np.array(grp['mask'])).radial_average(
            qrange=self.qrange, abscissa_errorpropagation=self.abscissaerrorpropagation,
            errorpropagation=self.errorpropagation).sanitize()
        dsradavg = grp.create_dataset('curve_reintegrated', shape=(len(radavg), 4), dtype=np.double)
        dsradavg[:, 0], dsradavg[:, 1], dsradavg[:, 2], dsradavg[:, 3] = (
        radavg.q, radavg.Intensity, radavg.Error, radavg.qError)
        grp['curve'] = h5py.SoftLink('curve_reintegrated')
        hdf5['images']['{}_{:.2f}'.format(samplename, distance)] = h5py.SoftLink(
            '/Samples/{}/{:.2f}/image'.format(samplename, distance))
        hdf5['curves']['{}_{:.2f}'.format(samplename, distance)] = h5py.SoftLink(
            '/Samples/{}/{:.2f}/curve'.format(samplename, distance))

    def stabilityassessment(self, samplename: str, distance: float, hdf5: h5py.File):
        cmatrix = correlmatrix(
            hdf5.require_group('Samples/{}/{:.2f}/curves'.format(samplename, distance)),
            self.std_multiplier, self.logarithmic_correlmatrix
        )
        grp = hdf5.require_group('Samples/{}/{:.2f}'.format(samplename, distance))
        grp.create_dataset('correlmatrix', data=cmatrix, shape=cmatrix.shape, dtype=cmatrix.dtype)
        hdf5['correlmatrix']['{}_{:.2f}'.format(samplename, distance)] = h5py.SoftLink(
            '/Samples/{}/{:.2f}/correlmatrix')

    def summarize(self, overwrite_results=True, yield_messages=False, logger=None):
        if overwrite_results:
            filemode = 'w'
        else:
            filemode = 'a'
        with h5py.File(self.outputfile, filemode) as hdf5:
            for groupname in ['Samples', 'masks', 'images', 'curves', 'correlmatrix', '_meta_']:
                hdf5.require_group(groupname)
            num = sum([len(self.distances(sn)) for sn in self.allsamplenames()])
            if yield_messages:
                yield '__init_summarize__', num
            for sn in self.allsamplenames():
                if logger is not None:
                    logger.info('Sample name: {}'.format(sn))
                for dist in self.distances(sn):
                    yield sn, dist
                    if logger is not None:
                        logger.info('Distance: {:.2f} mm (sample {})'.format(dist, sn))
                    for msg in self.collect_exposures(sn, dist, hdf5, yield_messages=yield_messages, logger=logger):
                        yield msg
                    if yield_messages:
                        yield '__init_stabilityassessment__', 0
                    self.stabilityassessment(sn, dist, hdf5)
        return None