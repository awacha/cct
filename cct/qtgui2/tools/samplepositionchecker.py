from typing import List

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSlot as Slot
from adjustText import adjust_text
from matplotlib.axes import Axes
from matplotlib.text import Text
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from .samplepositionchecker_ui import Ui_Form
from ..utils.window import WindowRequiresDevices


class SamplePositionChecker(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    figure: Figure
    canvas: FigureCanvasQTAgg
    figtoolbar: NavigationToolbar2QT
    axes: Axes
    texts: List[Text]
    xdata: List[float]
    ydata: List[float]

    def __init__(self, **kwargs):
        self.texts = []
        self.xdata = []
        self.ydata = []
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.instrument.samplestore.sampleListChanged.connect(self.repopulateListWidget)
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.figtoolbar = NavigationToolbar2QT(self.canvas, self)
        self.verticalLayout.addWidget(self.figtoolbar)
        self.verticalLayout.addWidget(self.canvas)
        self.axes = self.figure.add_subplot(self.figure.add_gridspec(1, 1)[:, :])
        self.replotPushButton.clicked.connect(self.replot)
        self.upsideDownToolButton.toggled.connect(self.flipPlot)
        self.rightToLeftToolButton.toggled.connect(self.flipPlot)
        # ToDo: support dragging
        self.snapXToolButton.setVisible(False)
        self.snapYToolButton.setVisible(False)
        self.enableDragSamplesToolButton.setVisible(False)
        self.repopulateListWidget()

    @Slot()
    def repopulateListWidget(self):
        items = [self.listWidget.item(row) for row in range(self.listWidget.count())]
        selected = [item.text() for item in items if item.checkState() == QtCore.Qt.Checked]
        self.listWidget.clear()
        self.listWidget.addItems(sorted([sample.title for sample in self.instrument.samplestore]))
        for item in [self.listWidget.item(row) for row in range(self.listWidget.count())]:
            item.setFlags(
                QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if (item.text() in selected) else QtCore.Qt.Unchecked)
        self.listWidget.setMinimumWidth(self.listWidget.sizeHintForColumn(0))

    @Slot()
    def replot(self):
        items = [self.listWidget.item(row) for row in range(self.listWidget.count())]
        selected = sorted([item.text() for item in items if item.checkState() == QtCore.Qt.Checked])
        self.axes.clear()
        samples = [self.instrument.samplestore[samplename] for samplename in selected]
        self.xdata = [s.positionx[0] for s in samples]
        self.ydata = [s.positiony[0] for s in samples]
        xerr = [s.positionx[1] for s in samples]
        yerr = [s.positiony[1] for s in samples]
        self.axes.errorbar(self.xdata, self.ydata, yerr, xerr, 'b.')
        self.texts = []
        for x, y, title in zip(self.xdata, self.ydata, selected):
            self.texts.append(self.axes.text(x, y, title, fontsize=self.labelSizeHorizontalSlider.value()))
        if self.instrument.samplestore.hasMotors():
            self.axes.set_xlabel(self.instrument.samplestore.xmotorname())
            self.axes.set_ylabel(self.instrument.samplestore.ymotorname())
        else:
            self.axes.set_xlabel("Sample X motor of unknown name")
            self.axes.set_ylabel("Sample Y motor of unknown name")
        self.axes.grid(True, which='both')
        self.axes.axis('equal')
        self.flipPlot()

    @Slot()
    def flipPlot(self):
        x1, x2, y1, y2 = self.axes.axis()
        self.axes.axis(
            xmin=max(x1,x2) if self.rightToLeftToolButton.isChecked() else min(x1, x2),
            xmax=min(x1, x2) if self.rightToLeftToolButton.isChecked() else max(x1, x2),
            ymin=max(y1, y2) if self.upsideDownToolButton.isChecked() else min(y1, y2),
            ymax=min(y1, y2) if self.upsideDownToolButton.isChecked() else max(y1, y2))
        self.canvas.draw()
        adjust_text(self.texts, self.xdata, self.ydata, ax=self.axes)#, arrowprops={'arrowstyle': "-", "color": 'k', 'lw': 0.5})
        self.canvas.draw_idle()
