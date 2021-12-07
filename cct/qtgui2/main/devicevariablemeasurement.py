from PyQt5 import QtCore, QtWidgets
from .devicevariablemeasurement_ui import Ui_Form
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from ..utils.window import WindowRequiresDevices


class DeviceVariableMeasurement(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    figure: Figure = None
    canvas: FigureCanvasQTAgg = None
    figToolbar: NavigationToolbar2QT = None
    axes: Axes = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.devicestatus)
        self.figure = Figure(figsize=(6, 4), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.figToolbar = NavigationToolbar2QT(self.canvas, self)
        self.figureVerticalLayout.addWidget(self.figToolbar)
        self.figureVerticalLayout.addWidget(self.canvas, 1)
        self.canvas.mpl_connect('resize_event', self.onCanvasResize)
        self.canvas.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding)

    def onCanvasResize(self, event):
        pass

    def replot(self):
        pass
