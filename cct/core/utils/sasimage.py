from .radint import radint_fullq
import numpy as np

from .errorvalue import ErrorValue


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
    def new_from_file(cls, npzname, picklename):
        pass

    def radial_average(self, qrange=None, pixels=False):
        if pixels:
            abscissa_kind = 0
        else:
            abscissa_kind = 3
        q, dq, I, dI, area = radint_fullq(self.val, self.err,
                                          self._param['geometry']['wavelength'],
                                          self._param['geometry']['wavelength.err'],
                                          self._param['geometry']['truedistance'],
                                          self._param['geometry']['truedistance.err'],
                                          self._param['geometry']['pixelsize'],
                                          self._param['geometry']['beamposx'],
                                          0, self._param['geometry']['beamposy'], 0,
                                          self._mask, qrange, errorpropagation=3,
                                          abscissa_errorpropagation=3,
                                          abscissa_kind=abscissa_kind
                                          )
        return {'q': q, 'dq': dq, 'I': I, 'dI': dI}

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
        return ((x - self._param['geometry']['beamposx']) ** 2 + (y - self._param['geometry']['beamposy']) ** 2) ** 0.5

    @property
    def detradius(self):
        return self.pixel / self._param['geometry']['pixelsize']

    @property
    def twotheta_rad(self):
        """In radians"""
        return (self.detradius / ErrorValue(self._param['geometry']['truedistance'],
                                            self._param['geometry']['truedistance.err'])).arctan()

    @property
    def twotheta_deg(self):
        return self.twotheta_rad * 180 / np.pi

    @property
    def q(self):
        return (self.twotheta_rad * 0.5).sin() * 4 * np.pi / ErrorValue(self._param['geometry']['wavelength'],
                                                                        self._param['geometry']['wavelength.err'])
