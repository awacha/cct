import logging
from typing import Tuple, List

from .processingwindow import ProcessingWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ResultViewWindow(ProcessingWindow):
    resultitems: List[Tuple[str, str]]
    closable = True

    def __init__(self, **kwargs):
        if ('samplename' in kwargs) and ('distancekey' in kwargs):
            self.resultitems = [(kwargs.pop('samplename'), kwargs.pop('distancekey'))]
        if 'resultitems' in kwargs:
            # this takes priority over 'samplename' and 'distancekey'
            self.resultitems = kwargs.pop('resultitems')
        super().__init__(**kwargs)
        self.setObjectName('Form')
        self.resize(100, 100)
        self.show()
        self.project.resultItemChanged.connect(self._onResultItemChanged)

    def _onResultItemChanged(self, samplename: str, distancekey: str):
        logger.debug(f'_onResultItemChanged in ResultViewWindow with resultitems {self.resultitems}')
        if (samplename, distancekey) in self.resultitems:
            if (samplename, distancekey) in self.project.results:
                logging.debug(f'ACCEPTED _onResultItemChanged({samplename}, {distancekey})')
                self.onResultItemChanged(samplename, distancekey)
            else:
                self.clear()
        else:
            logging.debug(f'SKIPPED _onResultItemChanged({samplename}, {distancekey})')

    def onResultItemChanged(self, samplename: str, distancekey: str):
        raise NotImplementedError

    def clear(self):
        """Clear the display"""
        self.close()
        self.destroy()
        self.deleteLater()