import itertools

from PyQt5 import QtWidgets, QtCore
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure

from .devicevariablelogger_ui import Ui_Form
from ...utils.comboboxdelegate import ComboBoxDelegate
from ....core2.instrument.components.devicestatus.devicestatuslogger import DeviceStatusLogger
from ....core2.instrument.instrument import Instrument


class DeviceVariableLoggerUI(QtWidgets.QWidget, Ui_Form):
    figure: Figure
    canvas: FigureCanvasQTAgg
    figtoolbar: NavigationToolbar2QT
    axes: Axes
    devicelogger: DeviceStatusLogger
    instrument: Instrument

    def __init__(self, **kwargs):
        self.devicelogger = kwargs.pop('devicelogger')
        self.instrument = kwargs.pop('instrument')
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.devicelogger)
        self.treeView.setItemDelegateForColumn(0, ComboBoxDelegate(self.treeView))
        self.treeView.setItemDelegateForColumn(1, ComboBoxDelegate(self.treeView))
        self.recordToolButton.setChecked(self.devicelogger.isRecording())
        self.deviceNameComboBox.setModel(self.instrument.devicemanager)
        self.deviceNameComboBox.currentIndexChanged.connect(self.onDeviceNameChanged)
        self.devicelogger.newData.connect(self.onNewData)
        self.devicelogger.destroyed.connect(self.onDeviceLoggerDestroyed)
        self.devicelogger.recordingStarted.connect(self.onDeviceLoggerStarted)
        self.devicelogger.recordingStopped.connect(self.onDeviceLoggerStopped)
        self.addEntryToolButton.clicked.connect(self.onAddEntryClicked)
        self.removeEntryToolButton.clicked.connect(self.onRemoveEntryClicked)
        self.clearAllEntriesToolButton.clicked.connect(self.onClearAllClicked)
        self.fileNameLineEdit.editingFinished.connect(self.onFileNameLineEditChanged)
        self.fileNameToolButton.clicked.connect(self.onBrowseClicked)
        self.recordToolButton.toggled.connect(self.onRecordToggled)
        self.destroyToolButton.clicked.connect(self.devicelogger.deleteLater)
        self.figure = Figure(figsize=(6, 3), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setSizePolicy(
            QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding))
        self.figtoolbar = NavigationToolbar2QT(self.canvas, self)
        self.figureVerticalLayout.addWidget(self.figtoolbar, 0)
        self.figureVerticalLayout.addWidget(self.canvas, 1)
        self.groupBox.setTitle(self.devicelogger.name())
        self.devicelogger.nameChanged.connect(self.groupBox.setTitle)
        self.devicelogger.fileNameChanged.connect(self.onFileNameChanged)
        self.devicelogger.nrecordChanged.connect(self.onNrecordChanged)
        gs = self.figure.add_gridspec(1, 1)
        self.axes = self.figure.add_subplot(gs[:, :])
        self.onDeviceNameChanged()

    def onFileNameChanged(self, newfilename: str):
        self.fileNameLineEdit.blockSignals(True)
        self.fileNameLineEdit.setText(newfilename)
        self.fileNameLineEdit.blockSignals(False)

    def onPeriodChanged(self, newperiod: float):
        pass

    def onNrecordChanged(self, nrecord: int):
        pass

    def onDeviceNameChanged(self):
        if self.deviceNameComboBox.currentIndex() < 0:
            self.variableNameComboBox.setModel(None)
        try:
            self.variableNameComboBox.setModel(self.instrument.devicemanager[self.deviceNameComboBox.currentText()])
        except KeyError:
            self.variableNameComboBox.setModel(None)

    def onNewData(self, recordptr: int):
        data = self.devicelogger.record()
        self.axes.clear()
        t = data['Time']
        for name, marker in zip(data.dtype.names[1:], itertools.cycle('osvd*^<>')):
            self.axes.plot(t, data[name], marker + '-', label=name)
        self.axes.set_xlabel('Time (sec)')
        self.axes.grid(True, which='both')
        self.axes.legend(loc='best')
        self.canvas.draw_idle()

    def onDeviceLoggerDestroyed(self):
        self.deleteLater()

    def onDeviceLoggerStarted(self):
        self.recordToolButton.blockSignals(True)
        self.recordToolButton.setChecked(True)
        for widget in [self.addEntryToolButton, self.removeEntryToolButton, self.clearAllEntriesToolButton,
                       self.fileNameToolButton, self.fileNameLineEdit]:
            widget.setEnabled(False)
        self.recordToolButton.blockSignals(False)

    def onDeviceLoggerStopped(self):
        self.recordToolButton.blockSignals(True)
        self.recordToolButton.setChecked(False)
        for widget in [self.addEntryToolButton, self.removeEntryToolButton, self.clearAllEntriesToolButton,
                       self.fileNameLineEdit, self.fileNameToolButton]:
            widget.setEnabled(True)
        self.recordToolButton.blockSignals(False)

    def onAddEntryClicked(self):
        if not ((self.deviceNameComboBox.currentIndex() >= 0) and (self.variableNameComboBox.currentIndex() >= 0)):
            return
        try:
            self.devicelogger.addRecordedVariable(
                self.deviceNameComboBox.currentText(), self.variableNameComboBox.currentText())
        except ValueError as ve:
            QtWidgets.QMessageBox.critical(
                self, f'Cannot add variable',
                f'Error while adding variable '
                f'{self.deviceNameComboBox.currentText()}/{self.variableNameComboBox.currentText()}: {ve}')

    def onRemoveEntryClicked(self):
        rowindexes = {index.row() for index in self.treeView.selectionModel().selectedRows(0)}
        for row in reversed(sorted(rowindexes)):
            self.devicelogger.removeRow(row, QtCore.QModelIndex())

    def onBrowseClicked(self):
        filename, filtr = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Select file to save record', '', 'All files (*)', 'All files (*)')
        if not filename:
            return
        self.fileNameLineEdit.setText(filename)
        self.onFileNameLineEditChanged()

    def onFileNameLineEditChanged(self):
        self.devicelogger.setFileName(self.fileNameLineEdit.text())

    def onClearAllClicked(self):
        self.devicelogger.removeRows(0, self.devicelogger.rowCount(QtCore.QModelIndex()), QtCore.QModelIndex())

    def onRecordToggled(self, checked: bool):
        if checked:
            self.devicelogger.startRecording()
        else:
            self.devicelogger.stopRecording()
