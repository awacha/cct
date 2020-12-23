from PyQt5 import QtWidgets, QtGui

from .resultviewwindow import ResultViewWindow
from ..utils.anisotropy import AnisotropyEvaluator


class ShowAnisotropyWindow(ResultViewWindow):
    anisotropyWidget: AnisotropyEvaluator = None

    def setupUi(self, Form: QtWidgets.QWidget):
        self.anisotropyWidget = AnisotropyEvaluator(self, mainwindow = self.mainwindow)
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0, )
        self.setLayout(layout)
        layout.addWidget(self.anisotropyWidget)
        self.onResultItemChanged(self.resultitems[0][0], self.resultitems[0][1])
        self.anisotropyWidget.h5Selector.hide()
        self.setWindowIcon(QtGui.QIcon(':/icons/anisotropy.svg'))

    def onResultItemChanged(self, samplename: str, distancekey: str):
        self.anisotropyWidget.setExposure(
            self.project.settings.h5io.readExposure(f'Samples/{samplename}/{distancekey}'))
        self.setWindowTitle(f'Anisotropy of {samplename} @ {distancekey} mm')
