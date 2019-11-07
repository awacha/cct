from PyQt5 import QtWidgets

from .exportsettings_ui import Ui_Form
from .settingspage import SettingsPage


class ExportSettings(QtWidgets.QWidget, Ui_Form, SettingsPage):

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setupUi(self)
        self.initSettingsPage([
            (self.imageFormatComboBox, 'imageformat'),
            (self.imageResolutionSpinBox, 'imagedpi'),
            (self.lengthUnitsComboBox, 'imagewidthunits'),
            (self.imageWidthDoubleSpinBox, 'imagewidth'),
            (self.imageHeightDoubleSpinBox, 'imageheight'),
            (self.onedimFormatComboBox, 'onedimformat'),
            (self.twodimFormatComboBox, 'twodimformat')])

    def setupUi(self, Form):
        super().setupUi(Form)


        