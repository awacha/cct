from typing import Dict, List


class PinHoleConfiguration:
    pinhole1: float
    pinhole2: float
    pinhole3: float
    motors: Dict[str, float]
    l1parts: List[float]
    l2parts: List[float]
    beamstop: float
    sddistance: float

