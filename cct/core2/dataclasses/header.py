import pickle
from typing import Tuple, Dict, Any, Optional

from .headerparameter import ValueAndUncertaintyHeaderParameter, StringHeaderParameter, IntHeaderParameter

ValueAndUncertaintyType = Tuple[float, float]


class Header:
    distance = ValueAndUncertaintyHeaderParameter(('geometry','truedistance'), ('geometry', 'truedistance.err'))
    beamposrow = ValueAndUncertaintyHeaderParameter(('geometry','beamposx'), ('geometry', 'beamposx.err'))
    beamposcol = ValueAndUncertaintyHeaderParameter(('geometry','beamposy'), ('geometry', 'beamposy.err'))
    pixelsize = ValueAndUncertaintyHeaderParameter(('geometry','pixelsize'), ('geometry', 'pixelsize.err'))
    wavelength = ValueAndUncertaintyHeaderParameter(('geometry','wavelength'), ('geometry', 'wavelength.err'))
    title = StringHeaderParameter(('sample', 'title'))
    fsn = IntHeaderParameter(('exposure', 'fsn'))
    maskname = StringHeaderParameter(('geometry', 'mask'))
    thickness = ValueAndUncertaintyHeaderParameter(('sample', 'thickness.val'), ('sample', 'thickness.err'))
    transmission = ValueAndUncertaintyHeaderParameter(('sample', 'transmission.val'), ('sample', 'transmission.err'))
    _data: Dict[str, Any]

    def __init__(self, filename: Optional[str] = None, datadict: Optional[Dict[str, Any]]=None):
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
