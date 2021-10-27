from typing import Optional, Dict, Any

from .calibrant import Calibrant


class IntensityCalibrant(Calibrant):
    datafile: Optional[str]

    def __init__(self, name: str, datafile: Optional[str] = None):
        super().__init__(name)
        self.datafile = datafile

    def __setstate__(self, state: Dict[str, Any]):
        super().__setstate__(state)
        self.datafile = state['datafile']

    def __getstate__(self) -> Dict[str, Any]:
        st = super().__getstate__()
        st['datafile'] = self.datafile
        return st
