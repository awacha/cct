import numpy as np
from PyQt5 import QtWidgets

from .resultviewwindow import ResultViewWindow
from .transmission_ui import Ui_Form


class TransmissionWindow(ResultViewWindow, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(self)
        self.repopulateTreeWidget()
        self.setWindowTitle('Transmissions')

    def onResultItemChanged(self, samplename: str, distancekey: str):
        self.repopulateTreeWidget()

    def repopulateTreeWidget(self):
        self.treeWidget.clear()
        items = []
        for samplename, distkey in self.resultitems[:]:
            try:
                sde = self.project.results.get(samplename, distkey)
            except IndexError:
                self.resultitems.remove((samplename, distkey))
                continue
            transm = sde.header.transmission
            thickness = sde.header.thickness
            if transm[0] >= 1:
                # full transmission, typically empty beam. Thickness should be zero. Anyway, 1/mu = infinity, mu=0
                mu = '∞'
                invmu = '0'
            elif transm[0] <= 0:
                # zero transmission, typically dark. Thickness should be infinite. 1/mu = 0, mu=infinity
                mu = '0'
                invmu = '∞'
            else:
                mud = -np.log(transm[0]), np.abs(transm[1] / transm[0])
                mu = mud[0] / thickness[0], (
                        (mud[1] / thickness[0]) ** 2 + (mud[0] / thickness[0] ** 2 * thickness[1]) ** 2) ** 0.5
                invmu = 1 / mu[0], np.abs(mu[1] / mu[0])
                mu = f'{mu[0]:.4f} \xb1 {mu[1]:.4f}'
                invmu = f'{invmu[0]:.4f} \xb1 {invmu[1]:.4f}'
            items.append(QtWidgets.QTreeWidgetItem([
                sde.samplename,
                sde.distancekey,
                f'{transm[0]:.4f} \xb1 {transm[1]:.4f}',
                f'{thickness[0]:.4f} \xb1 {thickness[1]:.4f}',
                mu,
                invmu])
            )
        self.treeWidget.addTopLevelItems(items)
        for i in range(self.treeWidget.columnCount()):
            self.treeWidget.resizeColumnToContents(i)

    def clear(self):
        self.repopulateTreeWidget()

