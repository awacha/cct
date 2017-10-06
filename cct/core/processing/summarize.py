import logging
import os
from typing import Iterable, List, Optional

import h5py
import numpy as np
from sastool.io.credo_cct import Header, Exposure
from scipy.io import loadmat

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def correlmatrix(grp:h5py.Group, std_multiplier:Optional[float]=None, logarithmic:bool=True):
    cm=np.zeros((len(grp),len(grp)),np.double)
    sortedkeys=sorted(grp.keys(), key=lambda x:int(x))
    for i in range(len(grp)):
        for j in range(i+1,len(grp)):
            ds1=grp[sortedkeys[i]]
            ds2=grp[sortedkeys[j]]
            if logarithmic:
                idx=np.logical_and(np.logical_and(ds1[:,2]>0,ds2[:,2]>0),np.logical_and(ds1[:,1]>0,ds2[:,1]>0))
                w=(ds1[idx,2]/ds1[idx,1])**2+(ds2[idx,2]/ds2[idx,1])**2
                cm[i,j]=cm[j,i]=((np.log(ds1[idx,1])-np.log(ds2[idx,1]))**2/w).sum()/(1/w).sum()
            else:
                idx=np.logical_and(ds1[:,2]>0,ds2[:,2]>0)
                w=(ds1[idx,2]**2+ds2[idx,2]**2)
                cm[i,j]=cm[j,i]=((ds1[idx,1]-ds2[idx,1])**2/w).sum()/(1/w).sum()
    rowavg=cm.sum(axis=0)/(len(grp)-1)
    for i in range(len(rowavg)):
        grp[sortedkeys[i]].attrs['correlmat_discrp']=rowavg[i]
        grp[sortedkeys[i]].attrs['correlmat_rel_discrp']=(rowavg[i]-np.median(rowavg))/rowavg.std()
        grp[sortedkeys[i]].attrs['correlmat_bad']=(rowavg[i]-np.median(rowavg))>std_multiplier*rowavg.std()
    cm=cm+np.diagflat(rowavg)
    return cm


class Summarizer(object):
    def __init__(
            self, fsns:Iterable[int], exppath:Iterable[str],
            parampath:Iterable[str], maskpath:Iterable[str],
            outputfile:str, prefix:str='crd', ndigits:int=5,
            errorpropagation:int=3, abscissaerrorpropagation:int=3,
            sanitize_curves:bool=True, logarithmic_correlmatrix:bool=True,
            std_multiplier:float=2.7,
    ):
        self.fsns=fsns
        self.exppath=exppath
        self.parampath=parampath
        self.maskpath = maskpath
        self.outputfile=outputfile
        self.prefix = prefix
        self.ndigits = ndigits
        self.errorpropagation = errorpropagation
        self.abscissaerrorpropagation = abscissaerrorpropagation
        self.sanitize_curves=sanitize_curves
        self.logarithmic_correlmatrix=logarithmic_correlmatrix
        self.std_multiplier = std_multiplier
        self._headers = []
        self._masks = {}

    def load_headers(self, yield_messages=False):
        self._headers = []
        for f in self.fsns:
            for p in self.parampath:
                try:
                    self._headers.append(Header.new_from_file(
                        os.path.join(
                            p,
                            '{{}}_{{:0{:d}d}}.pickle'.format(self.ndigits).format(self.prefix,f))
                    ))
                    if yield_messages:
                        yield '__header_loaded__', f
                    break
                except FileNotFoundError:
                    pass
            else:
                logger.error('No header found for prefix {}, fsn {}.'.format(self.prefix, f))
                if yield_messages:
                    yield '__header_notfound__', f
        return None

    def get_mask(self, maskname:str):
        try:
            return self._masks[maskname]
        except KeyError:
            pass
        for p in self.maskpath:
            try:
                m=loadmat(os.path.join(p,maskname))
            except FileNotFoundError:
                try:
                    m=loadmat(os.path.join(p,maskname+'.mat'))
                except FileNotFoundError:
                    continue
            self._masks[maskname]=m[[x for x in m.keys() if not x.startswith('_')][0]]
            return self._masks[maskname]
        else:
            logger.error('Mask file {} not found.'.format(maskname))
            raise FileNotFoundError('Mask {} not found'.format(maskname))

    def load_exposure(self, fsn:int) -> Exposure:
        header = [h for h in self._headers if h.fsn==fsn][0]
        mask = self.get_mask(header.maskname)
        for p in self.exppath:
            try:
                ex=Exposure.new_from_file(
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

    def distances(self, samplename:str) ->List[int]:
        dists=set([float(h.distance) for h in self._headers if h.title==samplename])
        distances = []
        for d in dists:
            if not any([abs(d-d_)<0.01 for d_ in distances]):
                distances.append(d)
        return distances

    def collect_exposures(self, samplename:str, distance:float, hdf5:h5py.File, yield_messages:bool=False):
        grp=hdf5.require_group('Samples/{}/{:.2f}'.format(samplename, distance))
        headers = [h for h in self._headers if h.title==samplename and abs(float(h.distance)-float(distance))<0.01]
        group1d=grp.require_group('curves')
        dataset2d=None
        error2d=None
        curve = None
        yield '__init_collect_exposures__', len(headers)
        for h in sorted(headers, key=lambda h:h.fsn):
            yield '__ce_debug__',h.fsn
            try:
                ex = self.load_exposure(h.fsn)
                if yield_messages:
                    yield '__exposure_loaded__', h.fsn
            except FileNotFoundError:
                if yield_messages:
                    yield '__exposure_notfound__', h.fsn
                continue
            if dataset2d is None:
                dataset2d=grp.create_dataset('image',data=ex.intensity)
                error2d=grp.create_dataset('image_uncertainty', data=ex.error**2)
            else:
                dataset2d+=ex.intensity
                error2d+=ex.error**2
            if ex.header.maskname not in hdf5.require_group('masks'):
                hdf5.require_group('masks').create_dataset(ex.header.maskname, data=ex.mask)
            curve = ex.radial_average(
                abscissa_errorpropagation=self.abscissaerrorpropagation,
                errorpropagation=self.errorpropagation)
            if self.sanitize_curves:
                curve=curve.sanitize()
            ds=group1d.create_dataset(
                '{{:0{:d}d}}'.format(self.ndigits).format(h.fsn),
                shape=(len(curve),3),dtype=np.double)
            ds[:,0]=curve.q
            ds[:,1]=curve.Intensity
            ds[:,2]=curve.Error
            ds.attrs['date']=h.date.isoformat()
        if curve is None:
            # no files have been loaded
            return
        dataset2d/=len(group1d)
        error2d/=len(group1d)

    def stabilityassessment(self, samplename:str, distance:float, hdf5:h5py.File):
        cmatrix = correlmatrix(
            hdf5.require_group('Samples/{}/{:.2f}/curves'.format(samplename,distance)),
            self.std_multiplier, self.logarithmic_correlmatrix
        )
        grp=hdf5.require_group('correlmatrix')
        grp.require_dataset('{}_{:.2f}'.format(samplename, distance), data=cmatrix, shape=cmatrix.shape, dtype=cmatrix.dtype)

    def summarize(self, overwrite_results=True, yield_messages=False):
        if overwrite_results:
            filemode='w'
        else:
            filemode='a'
        with h5py.File(self.outputfile,filemode) as hdf5:
            for groupname in ['Samples','masks', 'images','curves','correlmatrix','_meta_']:
                hdf5.require_group(groupname)
            num=sum([len(self.distances(sn)) for sn in self.allsamplenames()])
            if yield_messages:
                yield '__init_summarize__', num
            for sn in self.allsamplenames():
                logger.info('Sample name: {}'.format(sn))
                for dist in self.distances(sn):
                    yield sn, dist
                    logger.info('Distance: {:.2f} mm (sample {})'.format(dist,sn))
                    for msg in self.collect_exposures(sn, dist, hdf5, yield_messages=yield_messages):
                        yield msg
                    if yield_messages:
                        yield '__init_stabilityassessment__', 0
                    self.stabilityassessment(sn, dist, hdf5)
        return None