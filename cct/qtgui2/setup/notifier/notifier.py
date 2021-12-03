from .notifier_ui import Ui_Form
from PyQt5 import QtWidgets, QtCore
from ...utils.window import WindowRequiresDevices


class NotifierSetup(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.notifier)
        self.addToolButton.clicked.connect(self.onAddClicked)
        self.removeToolButton.clicked.connect(self.onRemoveClicked)
        self.clearToolButton.clicked.connect(self.onClearClicked)

    def onAddClicked(self):
        row = self.instrument.notifier.rowCount()
        self.instrument.notifier.insertRow(row)
        self.treeView.selectionModel().select(
            self.instrument.notifier.index(row, 0), QtCore.QItemSelectionModel.ClearAndSelect)

    def onRemoveClicked(self):
        while rowindices := self.treeView.selectionModel().selectedRows(column=0):
            self.instrument.notifier.removeRow(rowindices[0].row())

    def onClearClicked(self):
        self.instrument.notifier.removeRows(0, self.instrument.notifier.rowCount())