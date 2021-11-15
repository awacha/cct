from .processingwindow import ProcessingWindow
from .settings_ui import Ui_Form
from ...core2.algorithms.matrixaverager import ErrorPropagationMethod
from ...core2.dataclasses.exposure import QRangeMethod
from ...core2.processing.calculations.outliertest import OutlierMethod


class SettingsWindow(ProcessingWindow, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.project.settings.settingsChanged.connect(self.onSettingsChanged)
        self.outlierTestMethodComboBox.addItems(sorted([om.value for om in OutlierMethod]))
        self.qErrorPropagationComboBox.addItems(sorted([ep.name for ep in ErrorPropagationMethod]))
        self.intensityErrorPropagationComboBox.addItems(sorted([ep.name for ep in ErrorPropagationMethod]))
        self.outlierTestThresholdDoubleSpinBox.setRange(0, 99)
        self.outlierTestThresholdDoubleSpinBox.setDecimals(4)
        self.autoQScaleSpacingComboBox.addItems(sorted([qm.name for qm in QRangeMethod]))
        self.savePushButton.clicked.connect(self.saveSettings)
        self.onSettingsChanged()

    def onSettingsChanged(self):
        self.outlierTestThresholdDoubleSpinBox.setValue(self.project.settings.outlierthreshold)
        self.logarithmicCorrelationMatrixCheckBox.setChecked(self.project.settings.outlierlogcormat)
        self.outlierTestMethodComboBox.setCurrentIndex(
            self.outlierTestMethodComboBox.findText(self.project.settings.outliermethod.value))
        self.qErrorPropagationComboBox.setCurrentIndex(
            self.qErrorPropagationComboBox.findText(self.project.settings.qerrorprop.name))
        self.intensityErrorPropagationComboBox.setCurrentIndex(
            self.intensityErrorPropagationComboBox.findText(self.project.settings.ierrorprop.name))
        self.bigMemoryModeCheckBox.setChecked(self.project.settings.bigmemorymode)
        self.autoQScaleSpacingComboBox.setCurrentIndex(
            self.autoQScaleSpacingComboBox.findText(self.project.settings.qrangemethod.name))
        self.autoQLengthSpinBox.setValue(self.project.settings.qcount)

    def saveSettings(self):
        self.project.settings.outliermethod = OutlierMethod(self.outlierTestMethodComboBox.currentText())
        self.project.settings.ierrorprop = ErrorPropagationMethod[self.intensityErrorPropagationComboBox.currentText()]
        self.project.settings.qerrorprop = ErrorPropagationMethod[self.qErrorPropagationComboBox.currentText()]
        self.project.settings.outlierlogcormat = self.logarithmicCorrelationMatrixCheckBox.isChecked()
        self.project.settings.bigmemorymode = self.bigMemoryModeCheckBox.isChecked()
        self.project.settings.outlierthreshold = self.outlierTestThresholdDoubleSpinBox.value()
        self.project.settings.qcount = self.autoQLengthSpinBox.value()
        self.project.settings.qrangemethod = QRangeMethod[self.autoQScaleSpacingComboBox.currentText()]
        self.project.settings.emitSettingsChanged()
        print(self.saveGeometry())
