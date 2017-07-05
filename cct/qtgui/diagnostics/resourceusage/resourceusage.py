from typing import Optional

from PyQt5 import QtWidgets

from .resourceusage_ui import Ui_Form
from .telemetrymodel import TelemetryModel
from ...core.mixins import ToolWindow
from ....core.services.telemetry import TelemetryManager, TelemetryInfo
from ....core.utils.inhibitor import Inhibitor


class ResourceUsage(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self._telemetry_connections = []
        self._updating = Inhibitor()
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        tm = self.credo.services['telemetrymanager']
        assert isinstance(tm, TelemetryManager)
        self._telemetry_connections = [
            self.credo.services['telemetrymanager'].connect(
                'telemetry', self.onTelemetry)
        ]
        self.model = TelemetryModel()
        self.treeView.setModel(self.model)
        self.onTelemetry(tm, None, tm.get_telemetry(None))
        self.comboBox.currentIndexChanged.connect(self.getTelemetry)

    def getTelemetry(self):
        tm = self.credo.services['telemetrymanager']
        unit = self.comboBox.currentText()
        if unit == '-- overall --':
            unit = None
        self.onTelemetry(tm, unit, tm.get_telemetry(unit))

    def onTelemetry(self, telemetrymanager: TelemetryManager, unit: Optional[str], tm: TelemetryInfo):
        if self._updating:
            return False
        if unit is None:
            unit = '-- overall --'
        units_available = ['-- overall --'] + sorted(telemetrymanager.keys())
        units_known = [self.comboBox.itemText(i) for i in range(self.comboBox.count())]
        if units_available != units_known:
            with self._updating:
                selected_unit = self.comboBox.currentText()
                self.comboBox.clear()
                self.comboBox.addItems(units_available)
                self.comboBox.setCurrentIndex(self.comboBox.findText(selected_unit))
                if not self.comboBox.currentText():
                    self.comboBox.setCurrentIndex(0)
        if self.comboBox.currentText() == unit:
            self.model.update_telemetry(tm)
        self.treeView.resizeColumnToContents(0)
        self.treeView.resizeColumnToContents(1)

    def cleanup(self):
        for c in self._telemetry_connections:
            self.credo.services['telemetrymanager'].disconnect(c)
        self._telemetry_connections = []
