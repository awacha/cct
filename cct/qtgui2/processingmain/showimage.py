from PyQt5 import QtWidgets, QtGui

from .resultviewwindow import ResultViewWindow
from ..utils.plotimage import PlotImage


class ShowImageWindow(ResultViewWindow):
    plotImage: PlotImage = None

    def setupUi(self, Form:QtWidgets.QWidget):
        self.plotImage = PlotImage(self)
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0,)
        self.setLayout(layout)
        layout.addWidget(self.plotImage)
        self.onResultItemChanged(self.resultitems[0][0], self.resultitems[0][1])
        self.setWindowIcon(QtGui.QIcon(':/icons/saxspattern.svg'))

    def onResultItemChanged(self, samplename: str, distancekey: str):
        ex = self.project.settings.h5io.readExposure(f'Samples/{samplename}/{distancekey}')
        self.plotImage.setExposure(ex, keepzoom=True)
        self.setWindowTitle(f'Scattering pattern of {samplename} @ {distancekey} mm')