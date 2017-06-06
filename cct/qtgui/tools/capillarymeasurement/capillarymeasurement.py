import os

import numpy as np
import sastool
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from .capillarymeasurement_ui import Ui_Form
from ...core.mixins import ToolWindow


class CapillaryMeasurement(QtWidgets.QWidget,Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo=kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self._peaklines=[None, None]
        self._peakposittions=[None,None]
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        layout=QtWidgets.QVBoxLayout(self.figureContainerWidget)
        self.figureContainerWidget.setLayout(layout)
        self.figure=Figure()
        self.canvas=FigureCanvasQTAgg(self.figure)
        self.figureToolbar=NavigationToolbar2QT(self.canvas, self.figureContainerWidget)
        self.axes=self.figure.add_subplot(1,1,1)
        self.axes.grid(True, which='both')
        layout.addWidget(self.canvas)
        layout.addWidget(self.figureToolbar)
        self.browsePushButton.clicked.connect(self.browse)
        self.scanIndexSpinBox.valueChanged.connect(self.loadScan)
        self.reloadPushButton.clicked.connect(self.loadScan)
        self.signalNameComboBox.currentTextChanged.connect(self.plotSignal)
        self.derivativeCheckBox.toggled.connect(self.plotSignal)
        self.fitNegativePushButton.clicked.connect(self.fitNegative)
        self.fitPositivePushButton.clicked.connect(self.fitPositive)
        scanfile=self.credo.services['filesequence'].get_scanfile()
        self.scanFileNameLineEdit.setText(scanfile)
        self.loadScanFile()

    def filename(self):
        return self.scanFileNameLineEdit.text()

    def browse(self):
        cwd, filename=os.path.split(self.filename())
        filename, filter = QtWidgets.QFileDialog.getOpenFileName(self,"Open scan file",cwd, filter='*.spec')
        if not filename:
            return
        self.scanFileNameLineEdit.setText(filename)
        self.loadScanFile()

    def loadScanFile(self):
        self.scanfile = sastool.classes2.scan.SpecFile(self.filename())
        self.scanIndexSpinBox.setMinimum(min(self.scanfile.toc.keys()))
        self.scanIndexSpinBox.setMaximum(max(self.scanfile.toc.keys()))
        self.scanIndexSpinBox.setValue(max(self.scanfile.toc.keys()))
        self.scanIndexSpinBox.setEnabled(True)
        self.reloadPushButton.setEnabled(True)

    def loadScan(self):
        index = self.scanIndexSpinBox.value()
        try:
            self.scan = self.scanfile.get_scan(index)
        except KeyError:
            self.scanfile.reload()
            try:
                self.scan = self.scanfile.get_scan(index)
            except KeyError:
                QtWidgets.QMessageBox.critical(self,'Error','Scan #{:d} not in file {}.'.format(index, self.filename()),QtWidgets.QMessageBox.Ok)
                return
        self.scan.reload()
        self.signalNameComboBox.setEnabled(True)
        self.derivativeCheckBox.setEnabled(True)
        prevsignal=self.signalNameComboBox.currentText()
        self.signalNameComboBox.clear()
        self.signalNameComboBox.addItems(self.scan.columnnames[1:])
        if prevsignal:
            idx=self.signalNameComboBox.findText(prevsignal)
            if idx is not None:
                self.signalNameComboBox.setCurrentIndex(idx)
            else:
                self.signalNameComboBox.setCurrentIndex(0)
        else:
            self.signalNameComboBox.setCurrentIndex(0)
        while self.signalNameComboBox.currentText()=='FSN':
            self.signalNameComboBox.setCurrentIndex(self.signalNameComboBox.currentIndex()+1)
        assert isinstance(self.axes, Axes)
        self.axes.set_xlabel(self.scan.motor)
        self.axes.set_title(self.scan.comment)
        self.plotSignal()

    def getSignal(self, zoomed=False):
        """Get the currently selected signal.

        Returns:
            x [np.ndarray], signal [np.ndarray], derivative? [bool], signal name [str].

            or ValueError is raised.
        """
        assert isinstance(self.scan, sastool.classes2.scan.SpecScan)
        signalname = self.signalNameComboBox.currentText()
        if not signalname in self.scan.dtype.names:
            raise ValueError
        signal = self.scan.data[self.signalNameComboBox.currentText()]
        x = self.scan.data[self.scan.motor]
        if self.derivativeCheckBox.checkState():
            signal=(signal[1:]-signal[:-1])/(x[1:]-x[:-1])
            x=0.5*(x[1:]+x[:-1])
        if zoomed:
            xmin, xmax, ymin, ymax = self.axes.axis()
            idx = np.logical_and(np.logical_and(x>=xmin,x<=xmax),np.logical_and(signal>=ymin,signal<=ymax))
            x=x[idx]
            signal=signal[idx]
        return x, signal, self.derivativeCheckBox.checkState(), signalname

    def clearGraph(self):
        self.axes.clear()
        self.canvas.draw()
        self._peaklines=[]
        self._peakposittions=[]

    def plotSignal(self):
        try:
            x, signal, is_derivative, signalname = self.getSignal()
        except ValueError:
            return
        assert isinstance(self.axes, Axes)
        for l in self.axes.lines:
            l.remove()
        self.axes.plot(x,signal,'b.-',label=self.signalNameComboBox.currentText())
        self.axes.legend(loc='best')
        self.axes.set_ylabel(self.signalNameComboBox.currentText())
        self.axes.relim()
        self.axes.autoscale_view(True, True, True)
        self.canvas.draw()
        self.fitNegativePushButton.setEnabled(True)
        self.fitPositivePushButton.setEnabled(True)

    def fitPeak(self, sign):
        try:
            x, signal, isderivative, signalname = self.getSignal(zoomed=True)
        except ValueError:
            return
        retx=np.linspace(x.min(),x.max(),100)
        pos,hwhm,baseline,amplitude,stat, fitted=sastool.misc.basicfit.findpeak_single(x,signal,None,return_stat=True,return_x = retx)
        self._peakposittions[sign>0]=pos
        if self._peaklines[sign>0] is not None:
            self._peaklines[sign>0].remove()
        self._peaklines[sign>0]=self.axes.plot(retx, fitted, 'r-')[0]
        if sign<0:
            self.negativeValDoubleSpinBox.setValue(pos.val)
            self.negativeErrDoubleSpinBox.setValue(pos.err)
        else:
            self.positiveValDoubleSpinBox.setValue(pos.val)
            self.positiveErrDoubleSpinBox.setValue(pos.err)
        self.canvas.draw()

    def fitNegative(self):
        return self.fitPeak(-1)

    def fitPositive(self):
        return self.fitPeak(+1)

    def updateCenter(self):
        pass

    def updateThickness(self):
        pass


