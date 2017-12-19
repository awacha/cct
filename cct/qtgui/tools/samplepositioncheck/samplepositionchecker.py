import numpy as np
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from .samplepositionchecker_ui import Ui_Form
from .sampleselectorlist import SampleSelectorModel
from ...core.mixins import ToolWindow
from ....core.services.samples import SampleStore


class SamplePositionChecker(QtWidgets.QWidget, Ui_Form, ToolWindow):

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self._connections = []
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.model = SampleSelectorModel(self.credo)
        self.treeView.setModel(self.model)
        self.figure = Figure()
        self.axes = self.figure.add_subplot(1, 1, 1)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumSize(300, 300)
        self.navtoolbar = NavigationToolbar2QT(self.canvas, None)
        self.verticalLayout.addWidget(self.canvas, 1)
        self.verticalLayout.addWidget(self.navtoolbar)
        self.showLabelsToolButton.toggled.connect(self.onShowLabels)
        ss = self.credo.services['samplestore']
        assert isinstance(ss, SampleStore)
        self._connections = [ss.connect('list-changed', self.onSampleListChanged)]
        self.model.dataChanged.connect(self.replot)
        self.labelSizeHorizontalSlider.valueChanged.connect(self.replot)
        self.upsideDownToolButton.toggled.connect(self.replot)
        self.rightToLeftToolButton.toggled.connect(self.replot)
        self.loadPersistence()
        self.replot()

    def savePersistence(self):
        self.credo.savePersistence(
            'samplepositionchecker',
            {'show_labels':self.showLabelsToolButton.isChecked(),
             'rtl':self.rightToLeftToolButton.isChecked(),
             'upsidedown':self.upsideDownToolButton.isChecked(),
             'samples':self.model.getSelected()
             })

    def loadPersistence(self):
        data=self.credo.loadPersistence('samplepositionchecker')
        if not data:
            return
        try:
            self.showLabelsToolButton.setChecked(data['show_labels'])
        except KeyError:
            pass
        try:
            self.rightToLeftToolButton.setChecked(data['rtl'])
        except KeyError:
            pass
        try:
            self.upsideDownToolButton.setChecked(data['upsidedown'])
        except KeyError:
            pass
        try:
            self.model.setSelected(data['samples'])
        except KeyError:
            pass

    def cleanup(self):
        for c in self._connections:
            self.credo.services['samplestore'].disconnect(c)
        self._connections = []
        super().cleanup()

    def onSampleListChanged(self, ss: SampleStore):
        self.model.update()
        return False

    def onShowLabels(self):
        self.replot()

    def replot(self):
        assert isinstance(self.axes, Axes)
        self.axes.clear()
        try:
            xmin = self.credo.motors['Sample_X'].get_variable('softleft')
            ymin = self.credo.motors['Sample_Y'].get_variable('softleft')
            xmax = self.credo.motors['Sample_X'].get_variable('softright')
            ymax = self.credo.motors['Sample_Y'].get_variable('softright')
            self.axes.add_patch(Rectangle([xmin, ymin], xmax - xmin, ymax - ymin, fill=True, color='lightgray'))
        except KeyError:
            pass
        self.axes.grid(True, which='both')
        self.axes.axis('equal')
        xmin, xmax, ymin, ymax = self.axes.axis()
        if self.upsideDownToolButton.isChecked():
            self.axes.axis(ymin=max(ymax, ymin), ymax=min(ymin, ymax))
        else:
            self.axes.axis(ymin=min(ymax, ymin), ymax=max(ymin, ymax))
        if self.rightToLeftToolButton.isChecked():
            self.axes.axis(xmin = max(xmax, xmin), xmax = min(xmax, xmin))
        else:
            self.axes.axis(xmin=min(xmax, xmin), xmax=max(xmin, xmax))
        samples = self.model.getSelected()
        if not samples:
            self.canvas.draw()
            return False
        ss = self.credo.services['samplestore']
        assert isinstance(ss, SampleStore)
        coords = np.array(
            [[s.positionx.val, s.positiony.val, s.positionx.err, s.positiony.err] for s in ss if s.title in samples])
        self.axes.errorbar(coords[:, 0], coords[:, 1], coords[:, 3], coords[:, 2], 'bo')
        if self.showLabelsToolButton.isChecked():
            for s, x, y in zip(samples, coords[:, 0], coords[:, 1]):
                self.axes.text(x, y, ' ' + s + ' ', ha='left', va='center',
                               fontdict={'size': self.labelSizeHorizontalSlider.value()})
        self.canvas.draw()
