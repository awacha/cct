from PyQt5 import QtWidgets, QtGui

from .resultviewwindow import ResultViewWindow
from ..utils.plotimage import PlotImage
import logging


logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ShowImageWindow(ResultViewWindow):
    plotImage: PlotImage = None

    def setupUi(self, Form: QtWidgets.QWidget):
        self.plotImage = PlotImage(self)
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0, )
        self.setLayout(layout)
        layout.addWidget(self.plotImage)
        self.onResultItemChanged(self.resultitems[0][0], self.resultitems[0][1])
        self.setWindowIcon(QtGui.QIcon(':/icons/saxspattern.svg'))
        logger.debug('ShowImageWindow setupUi done.')
        self.updateGeometry()

    def onResultItemChanged(self, samplename: str, distancekey: str):
        if not samplename:
            fsn = int(distancekey)
            try:
                ex = self.project.loader().loadExposure(self.project.settings.prefix, fsn)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, 'Error', f'Cannot load exposure #{fsn}: {exc}')
                return
            self.setWindowTitle(f'Scattering pattern of sample {ex.header.title}, {ex.header.distance[0]:.2f} mm, FSN {ex.header.fsn}')
        else:
            ex = self.project.settings.h5io.readExposure(f'Samples/{samplename}/{distancekey}')
            self.setWindowTitle(f'Scattering pattern of {samplename} @ {distancekey} mm')
        self.plotImage.setExposure(ex, keepzoom=True)
