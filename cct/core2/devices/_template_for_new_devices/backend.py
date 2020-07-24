from typing import Sequence, Any, Tuple, List

from ..device.backend import DeviceBackend


class NewDeviceBackend(DeviceBackend):
    variables = [
        DeviceBackend.VariableInfo(name='', dependsfrom=[], urgent=False, timeout=1.0),

    ]

    def _query(self, variablename: str):
        pass

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        pass

    def interpretMessage(self, message: bytes, sentmessage: bytes):
        pass

    def issueCommand(self, name: str, args: Sequence[Any]):
        pass
