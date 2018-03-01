import numpy as np
from PyQt5 import QtWidgets, QtGui
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from sastool.classes2 import Curve

from .plotcurve_ui import Ui_Form


class PlotCurve(QtWidgets.QWidget, Ui_Form):
    def __init__(self, *args, **kwargs):
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.figure = Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(1, 1, 1)
        self.figureContainer.setLayout(QtWidgets.QVBoxLayout())
        self.figureContainer.layout().addWidget(self.canvas)
        self.figureToolbar = NavigationToolbar2QT(self.canvas, self.figureContainer)
        self.figureContainer.layout().addWidget(self.figureToolbar)
        assert isinstance(self.figureToolbar, QtWidgets.QToolBar)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/legend.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.legendAction = QtWidgets.QAction(icon, 'Show legend', None)
        self.legendAction.setCheckable(True)
        self.legendAction.setChecked(True)
        self.legendAction.triggered.connect(self.onLegendTriggered)
        icon = QtGui.QIcon.fromTheme("edit-clear-all")
        self.clearAxesAction = QtWidgets.QAction(icon, 'Clear all curves', None)
        self.clearAxesAction.triggered.connect(self.onClearAxes)
        toolbutton = QtWidgets.QToolButton()
        toolbutton.setDefaultAction(self.legendAction)
        self.figureToolbar.insertWidget(self.figureToolbar.actions()[0], toolbutton)
        toolbutton = QtWidgets.QToolButton()
        toolbutton.setDefaultAction(self.clearAxesAction)
        self.figureToolbar.insertWidget(self.figureToolbar.actions()[0], toolbutton)
        self.legendAction.setVisible(True)
        self.clearAxesAction.setVisible(True)
        self.figureToolbar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def onClearAxes(self):
        self.axes.clear()
        self.canvas.draw()

    def addFitCurve(self, x, y, **kwargs):
        this_is_the_first = (len(self.axes.lines)==0)
        self.axes.plot(x, y, **kwargs)
        if this_is_the_first:
            self.figureToolbar.update()
        self.onLegendTriggered()

    def addCurve(self, curve: Curve, label='_nolabel_', hold_mode=True, **kwargs):
        if not hold_mode:
            for l in self.axes.lines:
                l.remove()
        this_is_the_first = (len(self.axes.lines)==0)
        curve.loglog(axes=self.axes, label=label, **kwargs)
        if this_is_the_first:
            self.figureToolbar.update()
        self.onLegendTriggered()

    def onLegendTriggered(self):
        assert isinstance(self.legendAction, QtWidgets.QAction)
        if self.legendAction.isChecked():
            self.axes.legend(loc='best')
        else:
            self.axes.legend().remove()
        self.canvas.draw()

    def setXLabel(self, xlabel):
        assert isinstance(self.axes, Axes)
        self.axes.set_xlabel(xlabel)
        self.canvas.draw()

    def setYLabel(self, ylabel):
        assert isinstance(self.axes, Axes)
        self.axes.set_ylabel(ylabel)
        self.canvas.draw()

    def getZoomRange(self):
        xmin, xmax, ymin, ymax = self.axes.axis()
        for line in self.axes.lines:
            assert isinstance(line, Line2D)
            x = line.get_xdata()
            y = line.get_ydata()
            idx = np.logical_and(np.logical_and(x >= xmin, x <= xmax), np.logical_and(y >= ymin, y <= ymax))
            if idx.sum():
                return x[idx].min(), x[idx].max(), y[idx].min(), y[idx].max()
        return (xmin, xmax, ymin, ymax)

    def clear(self):
        self.axes.clear()
        self.canvas.draw()
