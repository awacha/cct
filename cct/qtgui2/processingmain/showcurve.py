from PyQt5 import QtWidgets, QtGui

from .resultviewwindow import ResultViewWindow
from ..utils.plotcurve import PlotCurve


class ShowCurveWindow(ResultViewWindow):
    plotCurve: PlotCurve = None

    def setupUi(self, Form: QtWidgets.QWidget):
        self.plotCurve = PlotCurve(self)
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0, )
        self.setLayout(layout)
        layout.addWidget(self.plotCurve)
        self.onResultItemChanged('', '')
        self.plotCurve.setPixelMode(False)
        self.plotCurve.setShowErrorBars(False)
        self.setWindowIcon(QtGui.QIcon(':/icons/saxscurve.svg'))

    def onResultItemChanged(self, samplename: str, distancekey: str):
        self.plotCurve.clear()
        for sn, dist in self.resultitems:
            curve = self.project.settings.h5io.readCurve(f'Samples/{sn}/{dist}/curve')
            self.plotCurve.addCurve(curve, label=f'{sn} @ {dist} mm')
        self.plotCurve.replot()
        self.setWindowTitle(f'Scattering curves')
