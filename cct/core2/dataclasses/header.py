import pickle
from typing import Tuple, Dict, Any, Optional

from .headerparameter import ValueAndUncertaintyHeaderParameter, StringHeaderParameter, IntHeaderParameter, \
    DateTimeHeaderParameter

ValueAndUncertaintyType = Tuple[float, float]


class Header:
    distance = ValueAndUncertaintyHeaderParameter(('geometry', 'truedistance'), ('geometry', 'truedistance.err'))
    beamposrow = ValueAndUncertaintyHeaderParameter(('geometry', 'beamposx'), ('geometry', 'beamposx.err'))
    beamposcol = ValueAndUncertaintyHeaderParameter(('geometry', 'beamposy'), ('geometry', 'beamposy.err'))
    pixelsize = ValueAndUncertaintyHeaderParameter(('geometry', 'pixelsize'), ('geometry', 'pixelsize.err'))
    wavelength = ValueAndUncertaintyHeaderParameter(('geometry', 'wavelength'), ('geometry', 'wavelength.err'))
    flux = ValueAndUncertaintyHeaderParameter(('dataredution', 'flux'), ('datareduction', 'flux.err'))
    samplex = ValueAndUncertaintyHeaderParameter(('sample', 'positionx.val'), ('sample', 'positionx.err'))
    sampley = ValueAndUncertaintyHeaderParameter(('sample', 'positiony.val'), ('sample', 'positiony.err'))
    temperature = ValueAndUncertaintyHeaderParameter(('environment', 'temperature'), None)
    vacuum = ValueAndUncertaintyHeaderParameter(('environment', 'vacuum_pressure'), None)
    fsn_absintref = IntHeaderParameter(('datareduction', 'absintrefFSN'))
    fsn_emptybeam = IntHeaderParameter(('datareduction', 'emptybeamFSN'))
    project = StringHeaderParameter(('accounting', 'projectid'))
    username = StringHeaderParameter(('accounting', 'operator'))
    distancedecreaase = ValueAndUncertaintyHeaderParameter(('sample', 'distminus.val'), ('sample', 'distminus.err'))
    sample_category = StringHeaderParameter(('sample', 'category'))
    startdate = DateTimeHeaderParameter(('exposure', 'startdate'))
    enddate = DateTimeHeaderParameter(('exposure', 'enddate'))
    date = enddate
    exposuretime = ValueAndUncertaintyHeaderParameter(('exposure', 'exptime'), None)
    absintfactor = ValueAndUncertaintyHeaderParameter(('datareduction', 'absintfactor'),
                                                      ('datareduction', 'absintfactor.err'))

    title = StringHeaderParameter(('sample', 'title'))
    fsn = IntHeaderParameter(('exposure', 'fsn'))
    maskname = StringHeaderParameter(('geometry', 'mask'))
    thickness = ValueAndUncertaintyHeaderParameter(('sample', 'thickness.val'), ('sample', 'thickness.err'))
    transmission = ValueAndUncertaintyHeaderParameter(('sample', 'transmission.val'), ('sample', 'transmission.err'))
    _data: Dict[str, Any]

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
