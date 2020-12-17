import datetime
import numbers
import pickle
import numpy as np
import logging
from typing import Tuple, Dict, Any, Optional, Final, List, Sequence

from .headerparameter import ValueAndUncertaintyHeaderParameter, StringHeaderParameter, IntHeaderParameter, \
    DateTimeHeaderParameter, FloatHeaderParameter
from .sample import Sample

ValueAndUncertaintyType = Tuple[float, float]


class Header:
    distance = ValueAndUncertaintyHeaderParameter(('geometry', 'truedistance'), ('geometry', 'truedistance.err'), default=(np.nan, 0.0))
    beamposrow = ValueAndUncertaintyHeaderParameter(('geometry', 'beamposx'), ('geometry', 'beamposx.err'), default=(np.nan, 0.0))
    beamposcol = ValueAndUncertaintyHeaderParameter(('geometry', 'beamposy'), ('geometry', 'beamposy.err'), default=(np.nan, 0.0))
    pixelsize = ValueAndUncertaintyHeaderParameter(('geometry', 'pixelsize'), ('geometry', 'pixelsize.err'), default=(1.0, 0.0))
    wavelength = ValueAndUncertaintyHeaderParameter(('geometry', 'wavelength'), ('geometry', 'wavelength.err'), default=(np.nan, 0.0))
    flux = ValueAndUncertaintyHeaderParameter(('datareduction', 'flux'), ('datareduction', 'flux.err'), default=(np.nan, np.nan))
    samplex = ValueAndUncertaintyHeaderParameter(('sample', 'positionx.val'), ('sample', 'positionx.err'), default=(np.nan, np.nan))
    sampley = ValueAndUncertaintyHeaderParameter(('sample', 'positiony.val'), ('sample', 'positiony.err'), default=(np.nan, np.nan))
    temperature = ValueAndUncertaintyHeaderParameter(('environment', 'temperature'), ('environment', 'temperature.err'),
                                                     default=(np.nan, np.nan))
    vacuum = ValueAndUncertaintyHeaderParameter(('environment', 'vacuum_pressure'),
                                                ('environment', 'vacuum_pressure.err'), default=(np.nan, np.nan))
    fsn_absintref = IntHeaderParameter(('datareduction', 'absintrefFSN'), default=-1)
    fsn_emptybeam = IntHeaderParameter(('datareduction', 'emptybeamFSN'), default=-1)
    fsn_dark = IntHeaderParameter(('datareduction', 'darkFSN'), default=-1)
    dark_cps = ValueAndUncertaintyHeaderParameter(('datareduction', 'dark_cps.val'), ('datareduction', 'dark_cps.err'), default=(np.nan, 0))
    project = StringHeaderParameter(('accounting', 'projectid'), default='--no-project--')
    username = StringHeaderParameter(('accounting', 'operator'), default='Anonymous')
    distancedecrease = ValueAndUncertaintyHeaderParameter(('sample', 'distminus.val'), ('sample', 'distminus.err'), default=(0.0, 0.0))
    sample_category = StringHeaderParameter(('sample', 'category'), default='sample')
    startdate = DateTimeHeaderParameter(('exposure', 'startdate'), default=datetime.datetime.fromtimestamp(0))
    enddate = DateTimeHeaderParameter(('exposure', 'enddate'), default=datetime.datetime.fromtimestamp(0))
    exposurecount = IntHeaderParameter(('exposure', 'count'), default=1)
    date = enddate
    exposuretime = ValueAndUncertaintyHeaderParameter(('exposure', 'exptime'), ('exposure', 'exptime.err'), default=(np.nan, 0))
    absintfactor = ValueAndUncertaintyHeaderParameter(('datareduction', 'absintfactor'),
                                                      ('datareduction', 'absintfactor.err'), default=(np.nan, 0))
    absintdof = IntHeaderParameter(('datareduction', 'absintdof'), default=-1)
    absintchi2 = FloatHeaderParameter(('datareduction', 'absintchi2_red'), default=np.nan)
    absintqmin = FloatHeaderParameter(('datareduction', 'absintqmin'), default=np.nan)
    absintqmax = FloatHeaderParameter(('datareduction', 'absintqmax'), default=np.nan)

    prefix = StringHeaderParameter(('exposure', 'prefix'), default='crd')
    title = StringHeaderParameter(('sample', 'title'), default='Untitled')
    fsn = IntHeaderParameter(('exposure', 'fsn'), default=-1)
    maskname = StringHeaderParameter(('geometry', 'mask'), default='')
    thickness = ValueAndUncertaintyHeaderParameter(('sample', 'thickness.val'), ('sample', 'thickness.err'), default=(np.nan, 0.0))
    transmission = ValueAndUncertaintyHeaderParameter(('sample', 'transmission.val'), ('sample', 'transmission.err'), default=(np.nan,0.0))
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

    _headerattributes_sum: Final[List[str]] = ['exposuretime', 'exposurecount']

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
                except (KeyError, TypeError):
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
            if isinstance(cls.__dict__[field], IntHeaderParameter):
                collatedvalues[field] = int(np.sum(values))
            elif isinstance(cls.__dict__[field], FloatHeaderParameter):
                collatedvalues[field] = float(np.sum(values))
            elif isinstance(cls.__dict__[field], ValueAndUncertaintyHeaderParameter):
                val = np.array([v[0] for v in values])
                err = np.array([v[1] for v in values])
                collatedvalues[field] = (val.sum(), (err ** 2).sum() ** 0.5)
            else:
                raise TypeError(f'Cannot sum header parameter of type {type(cls.__dict__[field])}.')
        for field in cls._headerattributes_average:
            values = collect(field, headers)
            if not values:
                continue
            if isinstance(cls.__dict__[field], FloatHeaderParameter):
                collatedvalues[field] = float(np.mean(values))
            elif isinstance(cls.__dict__[field], ValueAndUncertaintyHeaderParameter):
                val = np.array([v[0] for v in values])
                err = np.array([v[1] for v in values])
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
            else:
                raise TypeError(f'Cannot average header parameter of type {type(cls.__dict__[field])}')
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
