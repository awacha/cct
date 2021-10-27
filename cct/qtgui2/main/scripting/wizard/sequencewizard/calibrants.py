from PyQt5 import QtWidgets, QtCore
from .calibrants_ui import Ui_WizardPage
from ......core2.instrument.instrument import Instrument


class CalibrantsPage(QtWidgets.QWizardPage, Ui_WizardPage):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, WizardPage):
        super().setupUi(WizardPage)
        instrument = Instrument.instance()
        for combobox, regexp, fieldname in [
            (self.darkComboBox, "(Dark)|(calibration sample)|(normalization sample)", 'darkSample*'),
            (self.emptyComboBox, "(Empty beam)|(calibration sample)|(normalization sample)", 'emptySample*'),
            (self.intensityComboBox, "normalization sample", 'absintSample*'),
            (self.qComboBox, "calibration sample", 'qCalibrantSample*'),
        ]:
            sortmodel = QtCore.QSortFilterProxyModel(self)
            sortmodel.setSourceModel(instrument.samplestore)
            sortmodel.setFilterKeyColumn(8)
            sortmodel.setFilterRegExp(regexp)
            combobox.setModel(sortmodel)
            self.registerField(fieldname, combobox, 'currentText', combobox.currentTextChanged)
            combobox.setCurrentIndex(-1)
        for spinbox, fieldname in [
            (self.darkExpTimeDoubleSpinBox, 'darkTime'),
            (self.emptyExpTimeDoubleSpinBox, 'emptyTime'),
            (self.intensityExpTimeDoubleSpinBox, 'absintTime'),
            (self.qExpTimeDoubleSpinBox, 'qCalibrantTime'),
        ]:
            self.registerField(fieldname, spinbox, 'value', spinbox.valueChanged)
        self.initializePage()
