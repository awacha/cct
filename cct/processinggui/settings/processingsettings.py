from PyQt5 import QtWidgets

from .processingsettings_ui import Ui_Form
from .settingspage import SettingsPage


class ProcessingSettings(QtWidgets.QWidget, Ui_Form, SettingsPage):

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setupUi(self)
        self.initSettingsPage([
            (self.intensityErrorPropagationComboBox, 'errorpropagation'),
            (self.qErrorPropagationComboBox, 'abscissaerrorpropagation'),
            (self.outlierSearchMethodComboBox, 'outliermethod'),
            (self.outlierSearchMultiplierDoubleSpinBox, 'std_multiplier'),
            (self.logarithmicCorrelMatrixCheckBox, 'logcorrelmatrix'),
            (self.autoQRangeCheckBox, 'autoq'),
            (self.qminDoubleSpinBox, 'customqmin'),
            (self.qmaxDoubleSpinBox, 'customqmax'),
            (self.numQRamgeSpinBox, 'customqcount'),
            (self.logQRangeCheckBox, 'customqlogscale'),
            (self.maxJobCountSpinBox, 'maxjobs'),
           ])

    def setupUi(self, Form):
        super().setupUi(Form)



