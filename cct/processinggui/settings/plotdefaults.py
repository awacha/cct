import matplotlib.cm
from PyQt5 import QtWidgets

from .plotdefaults_ui import Ui_Form
from .settingspage import SettingsPage


class PlotSettings(QtWidgets.QWidget, Ui_Form, SettingsPage):
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setupUi(self)
        self.initSettingsPage([
            (self.showMaskCheckBox, 'showmask'),
            (self.showCenterCheckBox, 'showcenter'),
            (self.showColorBarCheckBox, 'showcolorbar'),
            (self.paletteComboBox, 'colorpalette'),
            (self.twodimAxisScalingComboBox, 'twodimaxisvalues'),
            (self.onedimAxisScalesComboBox, 'plottype'),
            (self.onedimSymbolsComboBox, 'symbolstype'),
            (self.showErrorBarsCheckBox, 'showerrorbars'),
            (self.showLinesCheckBox, 'showlines'),
            (self.showGridCheckBox, 'showgrid'),
            (self.showLegendCheckBox, 'showlegend')
            ])

    def setupUi(self, Form):
        super().setupUi(Form)
        self.paletteComboBox.clear()
        self.paletteComboBox.addItems(sorted(matplotlib.cm.cmap_d))
