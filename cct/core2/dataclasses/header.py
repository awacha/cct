import pickle
import numpy as np
from typing import Tuple, Dict, Any, Optional, Final, List, Sequence

from .headerparameter import ValueAndUncertaintyHeaderParameter, StringHeaderParameter, IntHeaderParameter, \
    DateTimeHeaderParameter, FloatHeaderParameter
from .sample import Sample

ValueAndUncertaintyType = Tuple[float, float]


class Header:
    distance = ValueAndUncertaintyHeaderParameter(('geometry', 'truedistance'), ('geometry', 'truedistance.err'))
    beamposrow = ValueAndUncertaintyHeaderParameter(('geometry', 'beamposx'), ('geometry', 'beamposx.err'))
    beamposcol = ValueAndUncertaintyHeaderParameter(('geometry', 'beamposy'), ('geometry', 'beamposy.err'))
    pixelsize = ValueAndUncertaintyHeaderParameter(('geometry', 'pixelsize'), ('geometry', 'pixelsize.err'))
    wavelength = ValueAndUncertaintyHeaderParameter(('geometry', 'wavelength'), ('geometry', 'wavelength.err'))
    flux = ValueAndUncertaintyHeaderParameter(('datareduction', 'flux'), ('datareduction', 'flux.err'))
    samplex = ValueAndUncertaintyHeaderParameter(('sample', 'positionx.val'), ('sample', 'positionx.err'))
    sampley = ValueAndUncertaintyHeaderParameter(('sample', 'positiony.val'), ('sample', 'positiony.err'))
    temperature = ValueAndUncertaintyHeaderParameter(('environment', 'temperature'), ('environment', 'temperature.err'),
                                                     (None, 0.0))
    vacuum = ValueAndUncertaintyHeaderParameter(('environment', 'vacuum_pressure'),
                                                ('environment', 'vacuum_pressure.err'), (None, 0.0))
    fsn_absintref = IntHeaderParameter(('datareduction', 'absintrefFSN'))
    fsn_emptybeam = IntHeaderParameter(('datareduction', 'emptybeamFSN'))
    fsn_dark = IntHeaderParameter(('datareduction', 'darkFSN'))
    dark_cps = ValueAndUncertaintyHeaderParameter(('datareduction', 'dark_cps.val'), ('datareduction', 'dark_cps.err'))
    project = StringHeaderParameter(('accounting', 'projectid'))
    username = StringHeaderParameter(('accounting', 'operator'))
    distancedecreaase = ValueAndUncertaintyHeaderParameter(('sample', 'distminus.val'), ('sample', 'distminus.err'))
    sample_category = StringHeaderParameter(('sample', 'category'))
    startdate = DateTimeHeaderParameter(('exposure', 'startdate'))
    enddate = DateTimeHeaderParameter(('exposure', 'enddate'))
    date = enddate
    exposuretime = ValueAndUncertaintyHeaderParameter(('exposure', 'exptime'), ('exposure', 'exptime.err'), (None, 0.0))
    absintfactor = ValueAndUncertaintyHeaderParameter(('datareduction', 'absintfactor'),
                                                      ('datareduction', 'absintfactor.err'))
    absintdof = IntHeaderParameter(('datareduction', 'absintdof'))
    absintchi2 = IntHeaderParameter(('datareduction', 'absintchi2_red'))
    absintqmin = FloatHeaderParameter(('datareduction', 'absintqmin'))
    absintqmax = FloatHeaderParameter(('datareduction', 'absintqmax'))

    prefix = StringHeaderParameter(('exposure', 'prefix'), default='crd')
    title = StringHeaderParameter(('sample', 'title'))
    fsn = IntHeaderParameter(('exposure', 'fsn'))
    maskname = StringHeaderParameter(('geometry', 'mask'))
    thickness = ValueAndUncertaintyHeaderParameter(('sample', 'thickness.val'), ('sample', 'thickness.err'))
    transmission = ValueAndUncertaintyHeaderParameter(('sample', 'transmission.val'), ('sample', 'transmission.err'))
    _data: Dict[str, Any]

    _headerattributes_ensureunique: Final[List[str]] = \
        ['title', 'distance', 'beamposrow', 'beamposcol', 'wavelength', 'pixelsize', 'distancedecrease', 'prefix']

    _headerattributes_average: Final[List[str]] = \
        ['transmission', 'thickness', 'flux', 'samplex', 'sampley', 'temperature', 'vacuum', 'dark_cps',
         'absintfactor', ]

    _headerattributes_collectfirst: Final[List[str]] = \
        ['startdate', 'date', 'fsn', 'fsn_absintref', 'fsn_emptybeam', 'maskname', 'project', 'username']

    _headerattributes_collectlast: Final[List[str]] = ['enddate']

    _headerattributes_drop: Final[List[str]] = ['absintdof', 'absintchi2', 'absintqmin', 'absintqmax', ]

    _headerattributes_sum: Final[List[str]] = ['exposuretime']

    def __init__(self, filename: Optional[str] = None, datadict: Optional[Dict[str, Any]] = None):
        if filename is None and datadict is None:
            raise ValueError('Either filename or datadict must be supplied.')
        if filename is not None and datadict is not None:
            raise ValueError('Filename and datadict must not be supplied together.')
        if filename is not None:
            with open(filename, 'rb') as f:
                self._data = pickle.load(f)
        else:
            assert datadict is not None
            self._data = datadict

    def sample(self) -> Optional[Sample]:
        return Sample.fromdict(self._data['sample']) if 'sample' in self._data else None

    @classmethod
    def average(cls, *headers: "Header") -> "Header":
        collatedvalues = {}

        def collect(f: str, hs: Sequence["Header"]) -> List[Any]:
            lis = []
            for h in hs:
                try:
                    lis.append(getattr(h, f))
                except KeyError:
                    continue
            return lis

        for field in cls._headerattributes_ensureunique:
            values = set(collect(field, headers))
            if len(values) < 1:
                raise ValueError(f'Field {field} is not unique. Found values: {", ".join([str(x) for x in values])}')
            collatedvalues[field] = values.pop()
        for field in cls._headerattributes_sum:
            values = collect(field, headers)
            if not values:
                continue
            collatedvalues[field] = sum(values)
        for field in cls._headerattributes_average:
            values = collect(field, headers)
            if not values:
                continue
            val = np.array([v if isinstance(v, float) else v[0] for v in values])
            err = np.array([np.nan if isinstance(v, float) else v[1] for v in values])
            if np.isfinite(err).sum() == 0:
                # no error bars anywhere
                err = np.ones_like(val)
            elif (err > 0).sum() == 0:
                # no positive error bars
                err = np.ones_like(val)
            else:
                # some non-finite error bars may exist: replace them with the lowest positive error bar data
                minposerr = np.nanmin(err[err > 0])
                err[err <= 0] = minposerr
                err[~np.isfinite(err)] = minposerr
            collatedvalues[field] = (
                (val / err ** 2).sum() / (1 / err ** 2).sum(),
                1 / (1 / err ** 2).sum() ** 0.5
            )
        for field in cls._headerattributes_collectfirst:
            try:
                collatedvalues[field] = collect(field, headers)[0]
            except IndexError:
                continue
        for field in cls._headerattributes_collectlast:
            try:
                collatedvalues[field] = collect(field, headers)[-1]
            except IndexError:
                continue
        h = cls(datadict={})
        for field in collatedvalues:
            setattr(h, field, collatedvalues[field])
        return h
