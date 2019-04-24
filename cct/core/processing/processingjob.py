"""A class representing a processing job: for one sample and one sample-to-detector distance"""
import itertools
import multiprocessing
import os
from typing import List

import numpy as np
import scipy.io
from sastool.io.credo_cct import Header, Exposure

from . import outliers
from .config import Config
from .correlmatrix import correlmatrix_cython
from .h5writer import H5Writer


class Message:
    def __init__(self, type_:str, message:str, totalcount:int=None, currentcount:int=None):
        self.type_=type_
        self.message=message
        self.totalcount=totalcount
        self.currentcount=currentcount


def getfilename(rootdir, subdir, prefix, extension, fsn, fsndigits=5):
    """Find a file from the data directory.

    The cause of the problem is that there are too many exposures to be put in a single directory,
    and it never has been standardised what to name the subdirectories. The default layout for cct is:

    <rootdir>
        images
        eval2d
        param
        param_override
        mask
        ...

    Exposure files (numbered with FSN) are stored under images, eval2d and param. Sometimes flatly
    in a single directory but sometimes in subdirectories, such as scn0, crd, tst_1 etc. Because of the
    large number of files, enumerating the subdirectories, especially on a network share takes too
    much time. We therefore use a heuristic approach. Given the root directory, the subdirectory
    (e.g. 'eval2d'), the prefix (e.g. 'crd'), the extension ('cbf') and the file sequence number, the
    filename is constructed:  <prefix>_<fsn padded with zeros to the desired length>.<extension>.
    The base path for the search is <rootdir>/<subdir>. Directories are searched in the following order:

    1. <rootdir>/<subdir>
    2. <rootdir>/<subdir>/<prefix>
    3. <rootdir>/<subdir>/<prefix><index>
    4. <rootdir>/<subdir>/<prefix>_<index>

    <index> is an increasing number without padding. 0 and 1 are always checked. It is assumed that
    subdirectories are continuous, therefore when a missing index is found, no more indices are checked.


    :param rootdir: root directory (containing e.g. 'images', 'eval2d', 'param' etc. subdirectories)
    :type rootdir: str
    :param subdir: subdirectory (e.g. 'images', 'eval2d', 'param' etc.)
    :type subdir: str
    :param prefix: exposure prefix (e.g. 'crd', 'tst', 'scn', 'tra')
    :type prefix: str
    :param extension: file extension without the dot (e.g. '.cbf', '.pickle' etc.)
    :type extension: str
    :param fsn: file sequence number
    :type fsn: int
    :param fsndigits: number of digits in the file name (defaults to 5)
    :type fsndigits: int
    :return: the name and path of the first found existing file
    :rtype: str
    :raises: FileNotFoundError if the file could not be found in any of the directories
    """
    basepath=os.path.join(rootdir, subdir)
    filename = '{{}}_{{:0{}}}.{{}}'.format(fsndigits).format(prefix, fsn, extension)
    # first try basepath / filename
    if os.path.exists(os.path.join(basepath, filename)):
        return os.path.join(basepath, filename)
    # try basepath/prefix
    if os.path.exists(os.path.join(basepath, prefix, filename)):
        return os.path.join(basepath, prefix, filename)
    # try basepath/prefix<number>
    for i in range(100):
        currentpath=os.path.join(basepath, prefix+str(i))
        if not os.path.isdir(currentpath) and i>=1:
            # if basepath/prefix<number> does not exist, do not try larger numbers.
            # An exception is i=0, because some weird people start counting from one...
            break
        if os.path.exists(os.path.join(currentpath, filename)):
            return os.path.join(currentpath, filename)
    # try basepath/prefix_<number> scheme
    for i in range(100):
        currentpath=os.path.join(basepath, prefix+'_'+str(i))
        if not os.path.isdir(currentpath) and i>=1:
            # if basepath/prefix<number> does not exist, do not try larger numbers.
            # An exception is i=0, because some weird people start counting from one...
            break
        if os.path.exists(os.path.join(currentpath, filename)):
            return os.path.join(currentpath, filename)
    raise FileNotFoundError(filename)


class ProcessingJob(multiprocessing.Process):
    """A separate process for processing (summarizing, azimuthally averaging, finding outliers) of a range
    of exposures belonging to the same sample, measured at the same sample-to-detector distance.
    """
    def __init__(self, fsnlist:List[int], h5writer:H5Writer, h5path:List[str], config:Config):
        super().__init__()
        self.fsnlist=fsnlist
        self.config=config
        self.subprocess=None
        self.starttime=None
        self.h5path=h5path
        self.h5writer=h5writer
        self.resultsqueue=multiprocessing.Queue()
        self.masks={}

    @staticmethod
    def load_header(rootdir:str, fsn:int) -> Header:
        for subdir, extension in itertools.product(['eval2d'], ['pickle', 'pickle.gz']):
            try:
                filename=getfilename(rootdir, subdir, 'crd', extension, fsn)
                break
            except FileNotFoundError:
                continue
        else:
            raise FileNotFoundError(fsn)
        return Header.new_from_file(filename)

    def load_exposure(self, rootdir:str, header:Header) -> Exposure:
        filename = getfilename(rootdir, 'eval2d', 'crd', 'npz', header.fsn)
        mask = None
        try:
            mask = self.masks[header.maskname]
        except KeyError:
            for folder, subfolders, files in  os.walk(os.path.join(rootdir, 'mask')):
                if header.maskname in files:
                    mf=scipy.io.loadmat(os.path.join(folder, header.maskname))
                    maskkey=[k for k in mf.keys() if not (k.startswith('_') and k.endswith('_'))][0]
                    self.masks[header.maskname]=mf[maskkey]
                    break
            else:
                raise FileNotFoundError(header.maskname)
        return Exposure.new_from_file(filename, header, mask)

    def run(self) -> None:
        # first load all header files
        headers = []
        self.resultsqueue.put(Message(
            type_='message', message='Loading headers {}/{}'.format(0, len(self.fsnlist)),
            totalcount=len(self.fsnlist), currentcount=0))
        for i, fsn in enumerate(self.fsnlist, start=1):
            try:
                headers.append(self.load_header(self.config.getStr('io', 'datadir'), fsn))
                self.resultsqueue.put(Message(
                    type_='message', message='Loading headers {}/{}'.format(i, len(self.fsnlist)),
                    totalcount=len(self.fsnlist), currentcount=i))
            except FileNotFoundError:
                continue
        # check if all headers correspond to the same sample and distance
        if len({(h.title, h.distance) for h in headers})>1:
            self.resultsqueue.put(Message(type_='error', message='There are more samples/distances!'))
            return

        # now load all exposures
        exposures=[]
        self.resultsqueue.put(Message(
            type_='message', message='Loading exposures {}/{}'.format(0, len(headers)),
            totalcount=len(headers), currentcount=0))
        for i,h in enumerate(headers, start=1):
            try:
                exposures.append(self.load_exposure(self.config.getStr('io', 'datadir'), h))
                self.resultsqueue.put(Message(
                    type_='message', message='Loading exposures {}/{}'.format(i, len(headers)),
                    totalcount=len(headers), currentcount=i))
            except FileNotFoundError as fnfe:
                self.resultsqueue.put(Message(
                    type_='error', message='Cannot find file: {}'.format(fnfe.args[0])
                ))
                return

        # make radial averages for the correlation map tests
        nq=self.config.getInt('processing', 'cmap_rad_nq')
        intensities=np.empty((nq, len(headers)), dtype=np.double)
        errors=np.empty_like(intensities)

        self.resultsqueue.put(Message(
            type_='message', message='Azimuthal averaging for CMAT {}/{}'.format(0, len(headers)),
            totalcount=len(headers), currentcount=0))
        for i, ex in enumerate(exposures):
            rad=ex.radial_average(nq)
            intensities[:,i]=rad.Intensity
            errors[:,i]=rad.Error
            self.resultsqueue.put(Message(
                type_='message', message='Azimuthal averaging for CMAT {}/{}'.format(i+1, len(headers)),
                totalcount=len(headers), currentcount=i+1))

        self.resultsqueue.put(Message(
            type_='message', message='Calculating correlation matrix', currentcount=0, totalcount=0
        ))
        cmat=correlmatrix_cython(intensities, errors, self.config.getBool('processing', 'logcorrelmatrix'))
        discrp=np.diagonal(cmat)
        # find outliers
        if self.config.getStr('processing', 'corrmatmethod') in ['Interquartile Range', 'Tukey_IQR', 'Tukey', 'IQR']:
            bad = outliers.outliers_Tukey_iqr(discrp, self.config.getFloat('processing', 'std_multiplier'))
        elif self.config.getStr('processing', 'corrmatmethod') in ['Z-score']:
            bad = outliers.outliers_zscore(discrp, self.config.getFloat('processing', 'std_multiplier'))
        elif self.config.getStr('processing', 'corrmatmethod') in ['Modified Z-score', 'Iglewicz-Hoaglin']:
            bad = outliers.outliers_zscore_mod(discrp, self.config.getFloat('processing', 'std_multiplier'))
        else:
            self.resultsqueue.put(Message(type_='error', message='Invalid outlier detection mode: {}'.format(
                self.config.getStr('processing', 'corrmatmethod')
            )))
            return
        goodheaders=[h for i,h in enumerate(headers) if i not in bad]
        goodexposures=[ex for i, ex in enumerate(exposures) if i not in bad]

        # summarize 2D and 1D datasets
        self.resultsqueue.put(Message(
            type_='message',
            message='Averaging exposures and curves 0/{}'.format(
                len(goodheaders), currentcount=0, totalcount=len(goodheaders))
        ))
        curve=None
        intensity2D=None
        error2D=None
        mask=None
        # determine the desired q-range
        if self.config.getBool('processing', 'customq'):
            # custom q-range is requested
            qmin=self.config.getFloat('processing', 'customqmin')
            qmax=self.config.getFloat('processing', 'customqmax')
            qcount=self.config.getInt('processing', 'customqcount')
            if self.config.getBool('processing', 'customqlogscale'):
                qrange=np.logspace(np.log10(qmin), np.log10(qmax), qcount)
            else:
                qrange=np.linspace(qmin, qmax, qcount)
        else:
            qrange=None
        errorpropagationlist=['Weighted', 'Average of errors', 'Squared (Gaussian)', 'Conservative']
        # Error propagation types: if y_i are the measured data and e_i are their uncertainties:
        #
        #  1) Weighted:
        #       y = sum_i (1/e_i^2 y_i) / sum_i (1/e_i^2)
        #       e = 1/sqrt(sum_i(1/e_i^2))
        #  2) Average of errors (linear):
        #       y = mean(y_i)    ( simple mean)
        #       e = mean(e_i)
        #  3) Gaussian (squared):
        #       y = mean(y_i)
        #       e = sqrt(sum(e_i^2)/N)
        #  4) Conservative:
        #       y = mean(y_i)
        #       e: either the Gaussian, or that from the standard deviation, take the larger one.
        try:
            ep=errorpropagationlist.index(self.config.getStr('processing', 'errorpropagation'))
        except ValueError:
            self.resultsqueue.put(Message(
                type_='error',
                message='Invalid error propagation type: {}'.format(self.config.getStr('processing', 'errorpropagation'))
            ))
            return
        try:
            aep=errorpropagationlist.index(self.config.getStr('processing', 'abscissaerrorpropagation'))
        except ValueError:
            self.resultsqueue.put(Message(
                type_='error',
                message='Invalid error propagation type for the abscissa: {}'.format(self.config.getStr('processing', 'abscissaerrorpropagation'))
            ))
            return
        for ex in goodexposures:
            rad=ex.radial_average(qrange, errorpropagation=ep, abscissa_errorpropagation=aep)