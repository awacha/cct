import pickle

import numpy as np
from sastool.io.twodim import readcbf
from sastool.misc.errorvalue import ErrorValue
from sastool.utils2d.integrate import radint_fullq_errorprop
from scipy.io import loadmat

from .pathutils import find_in_subfolders
from .sascurve import SASCurve


class SASImage(ErrorValue):
    def __init__(self, intensity, error, param, mask):
        ErrorValue.__init__(self, intensity, error)
        self._param = param
        self._mask = mask

    @property
    def intensity(self):
        return self.val

    @intensity.setter
    def intensity(self, value):
        self.val = value

    @property
    def error(self):
        return self.err

    @error.setter
    def error(self, value):
        self.err = value

    @classmethod
    def new_from_file(cls, twodname, picklename):
        if twodname.lower().endswith('.npz'):
            f = np.load(twodname)
            intensity = f['Intensity']
            error = f['Error']
            header = None
        elif twodname.lower().endswith('.cbf'):
            intensity, header = readcbf(twodname, load_header=True,
                                        load_data=True)
            error = intensity ** 0.5
        else:
            raise NotImplementedError(twodname.lower())
        if isinstance(picklename, str):
            with open(picklename, 'rb') as f:
                param = pickle.load(f)
        elif isinstance(picklename, dict):
            param=picklename
        else:
            raise NotImplementedError(type(picklename))
        if header is None:
            param['cbf'] = header
        maskfile = loadmat(find_in_subfolders('mask', param['geometry']['mask']))
        mask = maskfile[[k for k in maskfile if not k.startswith('_')][0]]
        return cls(intensity, error, param, mask)

    def radial_average(self, qrange=None, pixels=False, raw_result=False):
        if pixels:
            abscissa_kind = 3
        else:
            abscissa_kind = 0
        q, dq, I, dI, area = radint_fullq_errorprop(
            self.val, self.err,
            self._param['geometry']['wavelength'],
            self._param['geometry']['wavelength.err'],
            self._param['geometry']['truedistance'],
            self._param['geometry']['truedistance.err'],
            self._param['geometry']['pixelsize'],
            self._param['geometry']['pixelsize'],
            self._param['geometry']['beamposx'], 0,
            self._param['geometry']['beamposy'], 0,
            (self._mask == 0).astype(np.uint8), qrange, errorpropagation=3,
            abscissa_errorpropagation=3,
            abscissa_kind=abscissa_kind)
        if raw_result:
            return q, dq, I, dI, area
        else:
            return SASCurve(q, I, dq, dI, self._param['sample']['title'] +
                            ' %.2f mm' % self._param['geometry']['truedistance'])

    @property
    def params(self):
        return self._param

    @params.setter
    def params(self, value):
        self._param = value

    @property
    def pixel(self):
        x = np.arange(self.val.shape[0])[:, np.newaxis]
        y = np.arange(self.val.shape[1])[np.newaxis, :]
        return ErrorValue(((x - self._param['geometry']['beamposx']) ** 2 +
                           (y - self._param['geometry']['beamposy']) ** 2) ** 0.5, np.zeros_like(self.val))

    @property
    def detradius(self):
        return self.pixel * self._param['geometry']['pixelsize']

    @property
    def twotheta_rad(self):
        """In radians"""
        return (self.detradius / ErrorValue(
            self._param['geometry']['truedistance'],
            self._param['geometry']['truedistance.err'])).arctan()

    @property
    def twotheta_deg(self):
        return self.twotheta_rad * 180 / np.pi

    @property
    def q(self):
        return ((self.twotheta_rad * 0.5).sin() * 4 * np.pi /
                ErrorValue(self._param['geometry']['wavelength'],
                           self._param['geometry']['wavelength.err']))


    def get_statistics(self):
        return {'NaNs':np.isnan(self.intensity).sum(),'finites':np.isfinite(self.intensity).sum(),'negatives':(self.intensity<0).sum(),
                'unmaskedNaNs':np.isnan(self.intensity[self._mask!=0]).sum(),
                'unmaskednegatives':(self.intensity[self._mask!=0]<0).sum(),
                'masked':(self._mask==0).sum(),
                }

    def sum(self, respect_mask=True):
        if respect_mask:
            return self.intensity[self._mask!=0].sum()
        else:
            return self.intensity.sum()

    def mean(self, respect_mask=True):
        if respect_mask:
            return self.intensity[self._mask!=0].mean()
        else:
            return self.intensity.mean()


