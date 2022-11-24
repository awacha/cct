from typing import Optional
from PySide6.QtCore import Slot

from .processingwindow import ProcessingWindow
from .settings_ui import Ui_Form
from ...core2.algorithms.matrixaverager import ErrorPropagationMethod
from ...core2.dataclasses.exposure import QRangeMethod
from ...core2.processing.calculations.outliertest import OutlierMethod


class SettingsWindow(ProcessingWindow, Ui_Form):
    samplename: Optional[str] = None
    distkey: Optional[str] = None

    def __init__(self, *args, **kwargs):
        if 'samplename' in kwargs:
            self.samplename = kwargs.pop('samplename')
        if 'distkey' in kwargs:
            self.distkey = kwargs.pop('distkey')
        super().__init__(*args, **kwargs)

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
        if (self.samplename is not None) and (self.distkey is not None):
            self.setWindowTitle(f'Edit settings for sample {self.samplename}@{self.distkey}')
        else:
            self.setWindowTitle(f'Edit default settings')

    @Slot()
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
        if (self.samplename is not None) and (self.distkey is not None):
            with self.project.settings.h5io.reader(f'Samples/{self.samplename}/{self.distkey}') as grp:
                attrs = dict(grp.attrs)
            if 'outlierthreshold' not in attrs:
                # the others are not there, either
                return
            self.outlierTestThresholdDoubleSpinBox.setValue(float(attrs['outlierthreshold']))
            self.logarithmicCorrelationMatrixCheckBox.setChecked(bool(attrs['outlierlogcormat']))
            self.outlierTestMethodComboBox.setCurrentIndex(
                self.outlierTestMethodComboBox.findText(attrs['outliermethod'])
            )
            self.qErrorPropagationComboBox.setCurrentIndex(
                self.qErrorPropagationComboBox.findText(attrs['qerrorprop']))
            self.intensityErrorPropagationComboBox.setCurrentIndex(
                self.intensityErrorPropagationComboBox.findText(attrs['ierrorprop'])
            )
            self.bigMemoryModeCheckBox.setChecked(bool(attrs['bigmemorymode']))
            self.autoQScaleSpacingComboBox.setCurrentIndex(
                self.autoQScaleSpacingComboBox.findText(attrs['qrangemethod'])
            )
            self.autoQLengthSpinBox.setValue(int(attrs['qcount']))

    @Slot()
    def saveSettings(self):
        if (self.samplename is not None) and (self.distkey is not None):
            with self.project.settings.h5io.writer(f'Samples/{self.samplename}/{self.distkey}') as grp:
                grp.attrs['outliermethod'] = OutlierMethod(self.outlierTestMethodComboBox.currentText()).value
                grp.attrs['ierrorprop'] = ErrorPropagationMethod[self.intensityErrorPropagationComboBox.currentText()].name
                grp.attrs['qerrorprop'] = ErrorPropagationMethod[self.qErrorPropagationComboBox.currentText()].name
                grp.attrs['outlierlogcormat'] = self.logarithmicCorrelationMatrixCheckBox.isChecked()
                grp.attrs['bigmemorymode'] = self.bigMemoryModeCheckBox.isChecked()
                grp.attrs['outlierthreshold'] = self.outlierTestThresholdDoubleSpinBox.value()
                grp.attrs['qcount'] = self.autoQLengthSpinBox.value()
                grp.attrs['qrangemethod'] = QRangeMethod[self.autoQScaleSpacingComboBox.currentText()].name
        else:
            self.project.settings.outliermethod = OutlierMethod(self.outlierTestMethodComboBox.currentText())
            self.project.settings.ierrorprop = ErrorPropagationMethod[self.intensityErrorPropagationComboBox.currentText()]
            self.project.settings.qerrorprop = ErrorPropagationMethod[self.qErrorPropagationComboBox.currentText()]
            self.project.settings.outlierlogcormat = self.logarithmicCorrelationMatrixCheckBox.isChecked()
            self.project.settings.bigmemorymode = self.bigMemoryModeCheckBox.isChecked()
            self.project.settings.outlierthreshold = self.outlierTestThresholdDoubleSpinBox.value()
            self.project.settings.qcount = self.autoQLengthSpinBox.value()
            self.project.settings.qrangemethod = QRangeMethod[self.autoQScaleSpacingComboBox.currentText()]
            self.project.settings.emitSettingsChanged()

