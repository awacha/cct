from typing import Dict, Any, Tuple, List

from .calibrant import Calibrant


class QCalibrant(Calibrant):
    peaks: List[Tuple[str, float, float]]

    def __init__(self, name: str):
        super().__init__(name)
        self.peaks = []

    def __setstate__(self, state: Dict[str, Any]):
        super().__setstate__(state)
        self.peaks = list(state['peaks'])

    def __getstate__(self) -> Dict[str, Any]:
        st = super().__getstate__()
        st['peaks'] = list(self.peaks)
        return st

    def __len__(self) -> int:
        return len(self.peaks)
