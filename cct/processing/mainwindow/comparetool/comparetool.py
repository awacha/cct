import string

import numpy as np

from .comparetool_ui import Ui_Form
from .samplescalermodel import SampleScalerModel
from ..toolbase import ToolBase


class CompareTool(ToolBase, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.cmpSelectAllSamplesPushButton.clicked.connect(self.onCmpSelectAllSamples)
        self.cmpDeselectAllSamplesPushButton.clicked.connect(self.onCmpDeselectAllSamples)
        self.cmpPlotPushButton.clicked.connect(self.onCmpPlot)
        self.configWidgets = [
            (self.cmpLabelLineEdit, 'curvecmp', 'legendformat'),
            (self.cmpPlotTypeComboBox, 'curvecmp', 'plottype'),
            (self.cmpErrorBarsCheckBox, 'curvecmp', 'errorbars'),
            (self.cmpLegendCheckBox, 'curvecmp', 'legend'),
        ]

    def onCmpPlot(self):
        try:
            self.clearFigure()
            ax = self.figure.add_subplot(1, 1, 1)
            arbunits = False
            for sn in self.cmpSampleModel.selectedSamples():
                for dist in self.h5GetDistances(sn):
                    with self.getHDF5Group(sn, dist) as grp:
                        curve = np.array(grp['curve'])
                        attrs = dict(grp.attrs)
                    factor = self.cmpSampleModel.factorForSample(sn)
                    if factor != 1:
                        arbunits = True
                    try:
                        lbl = string.Formatter().vformat(self.cmpLabelLineEdit.text(), (), attrs)
                    except Exception as exc:
                        lbl = '--error-in-format-string--'
                    if self.cmpPlotTypeComboBox.currentText() == 'Kratky':
                        x = curve[:, 0]
                        y = curve[:, 1] * curve[:, 0] ** 2 * factor
                        dy = (4 * curve[:, 0] ** 2 * curve[:, 1] ** 2 * curve[:, 2] ** 2 +
                              curve[:, 0] ** 4 * curve[:, 2] ** 2) ** 0.5
                        dx = curve[:, 3]
                    elif self.cmpPlotTypeComboBox.currentText() == 'Porod':
                        x = curve[:, 0]
                        y = curve[:, 1] * curve[:, 0] ** 4 * factor
                        dy = (16 * curve[:, 0] ** 6 * curve[:, 1] ** 2 * curve[:, 2] ** 2 +
                              curve[:, 0] ** 8 * curve[:, 2] ** 2) ** 0.5
                        dx = curve[:, 3]
                    else:
                        x = curve[:, 0]
                        y = curve[:, 1] * factor
                        dy = curve[:, 2] * factor
                        dx = curve[:, 3]
                    if self.cmpErrorBarsCheckBox.isChecked():
                        ax.errorbar(x, y, dy, dx, label=lbl)
                    else:
                        ax.plot(x, y, label=lbl)
            ax.set_xlabel('q (nm$^{-1}$)')
            if arbunits:
                if self.cmpPlotTypeComboBox.currentText() == 'Kratky':
                    ax.set_ylabel('q$^2 \\times$ relative intensity (nm$^{-2}\\times$arb. units)')
                elif self.cmpPlotTypeComboBox.currentText() == 'Kratky':
                    ax.set_ylabel('q$^4 \\times$ relative intensity (nm$^{-4}\\times$arb. units)')
                else:
                    ax.set_ylabel('Relative intensity (arb. units)')
            else:
                if self.cmpPlotTypeComboBox.currentText() == 'Kratky':
                    ax.set_ylabel('$q^2\\times d\Sigma/d\Omega$ (nm$^{-2}$ cm$^{-1}$ sr$^{-1}$)')
                elif self.cmpPlotTypeComboBox.currentText() == 'Porod':
                    ax.set_ylabel('$q^4\\times d\Sigma/d\Omega$ (nm$^{-4}$ cm$^{-1}$ sr$^{-1}$)')
                else:
                    ax.set_ylabel('$d\Sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
            if self.cmpPlotTypeComboBox.currentText() == 'log I vs. log q':
                ax.set_xscale('log')
                ax.set_yscale('log')
            elif self.cmpPlotTypeComboBox.currentText() == 'log I vs. q':
                ax.set_xscale('linear')
                ax.set_yscale('log')
            elif self.cmpPlotTypeComboBox.currentText() == 'I vs. log q':
                ax.set_xscale('log')
                ax.set_yscale('linear')
            elif self.cmpPlotTypeComboBox.currentText() == 'Guinier':
                ax.set_xscale('power', exponent=2)
                ax.set_yscale('log')
            elif self.cmpPlotTypeComboBox.currentText() == 'Kratky':
                ax.set_xscale('linear')
                ax.set_yscale('linear')
            elif self.cmpPlotTypeComboBox.currentText() == 'Porod':
                ax.set_xscale('power', exponent=4)
                ax.set_yscale('linear')
            ax.grid(True, which='both')
            if self.cmpLegendCheckBox.isChecked():
                ax.legend(loc='best')
            self.figure.tight_layout()
            self.figureDrawn.emit()
        except (FileNotFoundError, ValueError, OSError):
            return

    def onCmpSelectAllSamples(self):
        self.cmpSampleModel.selectAll()

    def onCmpDeselectAllSamples(self):
        self.cmpSampleModel.deselectAll()

    def setH5FileName(self, h5filename: str):
        super().setH5FileName(h5filename)
        self.cmpSampleModel = SampleScalerModel(self.h5GetSamples())
        self.cmpSampleTreeView.setModel(self.cmpSampleModel)
        for i in range(self.cmpSampleModel.columnCount()):
            self.cmpSampleTreeView.resizeColumnToContents(i)
