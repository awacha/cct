from typing import Tuple, List

from .processingwindow import ProcessingWindow


class ResultViewWindow(ProcessingWindow):
    resultitems: List[Tuple[str, str]]

    def __init__(self, **kwargs):
        if ('samplename' in kwargs) and ('distancekey' in kwargs):
            self.resultitems = [(kwargs.pop('samplename'), kwargs.pop('distancekey'))]
        if 'resultitems' in kwargs:
            # this takes priority over 'samplename' and 'distancekey'
            self.resultitems = kwargs.pop('resultitems')
        super().__init__(**kwargs)
        self.project.resultItemChanged.connect(self._onResultItemChanged)

    def _onResultItemChanged(self, samplename:str, distancekey:str):
        if (samplename, distancekey) in self.resultitems:
            self.onResultItemChanged(samplename, distancekey)

    def onResultItemChanged(self, samplename: str, distancekey: str):
        raise NotImplementedError