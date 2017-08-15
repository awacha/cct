import numpy as np
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from .samplepositionchecker_ui import Ui_Form
from .sampleselectorlist import SampleSelectorModel
from ...core.mixins import ToolWindow
from ....core.services.samples import SampleStore


class SamplePositionChecker(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self._connections=[]
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.model=SampleSelectorModel(self.credo)
        self.treeView.setModel(self.model)
        self.figure = Figure()
        self.axes=self.figure.add_subplot(1,1,1)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumSize(300,300)
        self.navtoolbar = NavigationToolbar2QT(self.canvas, None)
        self.verticalLayout.addWidget(self.canvas,1)
        self.verticalLayout.addWidget(self.navtoolbar)
        self.showLabelsCheckBox.toggled.connect(self.onShowLabels)
        ss=self.credo.services['samplestore']
        assert isinstance(ss,SampleStore)
        self._connections=[ss.connect('list-changed', self.onSampleListChanged)]
        self.model.dataChanged.connect(self.replot)

    def cleanup(self):
        for c in self._connections:
            self.credo.services['samplestore'].disconnect(c)
        self._connections=[]
        super().cleanup()

    def onSampleListChanged(self):
        self.model.update()
        return False

    def onShowLabels(self):
        self.replot()

    def replot(self):
        assert isinstance(self.axes, Axes)
        self.axes.clear()
        samples = self.model.getSelected()
        if not samples:
            self.canvas.draw()
            return False
        ss=self.credo.services['samplestore']
        assert isinstance(ss, SampleStore)
        coords=np.array([[s.positionx.val, s.positiony.val, s.positionx.err, s.positiony.err] for s in ss if s.title in samples])
        self.axes.errorbar(coords[:,0],coords[:,1],coords[:,3],coords[:,2],'bo')
        if self.showLabelsCheckBox.isChecked():
            for s,x,y in zip(samples, coords[:,0],coords[:,1]):
                self.axes.text(x,y,s,ha='left',va='center')
        self.axes.axis('equal')
        self.canvas.draw()
