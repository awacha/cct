from PySide6 import QtWidgets, QtGui

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
        self.onResultItemChanged('', '')  # at present only full redraw is supported
        self.plotCurve.setPixelMode(False)
        self.plotCurve.setShowErrorBars(False)
        self.setWindowIcon(QtGui.QIcon(':/icons/saxscurve.svg'))

    def onResultItemChanged(self, samplename: str, distancekey: str):
        # full redraw every time. This is suboptimal, ToDo
        self.plotCurve.clear()
        for sn, dist in self.resultitems:
            if not sn:  # then dist is the FSN!
                try:
                    ex = self.project.loader().loadExposure(int(dist))
                    curve = ex.radial_average(
                        errorprop=self.project.settings.ierrorprop, qerrorprop=self.project.settings.qerrorprop)
                    label = f'{ex.header.title}, #{ex.header.fsn}'
                except Exception:
                    continue
            else:
                curve = self.project.settings.h5io.readCurve(f'Samples/{sn}/{dist}/curve')
                label = f'{sn} @ {dist} mm'
            self.plotCurve.addCurve(curve, label=label)
        self.plotCurve.replot()
        self.setWindowTitle(f'Scattering curves')

    def clear(self):
        self.plotCurve.clear()
