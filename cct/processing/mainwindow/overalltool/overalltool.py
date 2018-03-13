import h5py

from .overalltool_ui import Ui_Form
from ..toolbase import ToolBase
from ...display import make_exptimes_table, make_transmission_table, plot_vacuum_and_flux


class OverallTool(ToolBase, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.qcVacuumFluxPushButton.clicked.connect(self.onQCVacuumFlux)
        self.qcTransmissionsPushButton.clicked.connect(self.onQCTransmissions)
        self.qcExposureTimesPushButton.clicked.connect(self.onQCExposureTimes)
        self.configWidgets = []

    def onQCExposureTimes(self):
        with h5py.File(self.h5FileName, 'r') as f:
            model = make_exptimes_table(f['Samples'])
        self.treeView.setModel(model)
        self.tableShown.emit()

    def onQCTransmissions(self):
        with h5py.File(self.h5FileName, 'r') as f:
            model = make_transmission_table(f['Samples'])
        self.treeView.setModel(model)
        self.tableShown.emit()

    def onQCVacuumFlux(self):
        with h5py.File(self.h5FileName, 'r') as f:
            plot_vacuum_and_flux(self.figure, f['Samples'], self.cctConfig['datareduction']['absintrefname'])
        self.figureDrawn.emit()
