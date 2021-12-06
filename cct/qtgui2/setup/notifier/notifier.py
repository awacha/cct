from typing import Tuple, Any

from .notifier_ui import Ui_Form
from PyQt5 import QtWidgets, QtCore
from ...utils.window import WindowRequiresDevices


class NotifierSetup(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.notifier)
        self.addToolButton.clicked.connect(self.onAddClicked)
        self.removeToolButton.clicked.connect(self.onRemoveClicked)
        self.clearToolButton.clicked.connect(self.onClearClicked)
        self.smtpServerLineEdit.setText(self.instrument.notifier.smtpserver if self.instrument.notifier.smtpserver is not None else '')
        self.fromAddressLineEdit.setText(self.instrument.notifier.fromaddress if self.instrument.notifier.fromaddress is not None else '')
        self.setSMTPServerToolButton.clicked.connect(self.onSetSMTPServerClicked)
        self.setFromAddressToolButton.clicked.connect(self.onSetFromAddressClicked)

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

    def onSetSMTPServerClicked(self):
        self.instrument.notifier.smtpserver = self.smtpServerLineEdit.text()

    def onSetFromAddressClicked(self):
        self.instrument.notifier.fromaddress = self.fromAddressLineEdit.text()

    def onConfigChanged(self, path: Tuple[str, ...], newvalue: Any):
        if path == ('notifier', 'smtpserver'):
            self.smtpServerLineEdit.setText(newvalue)
        elif path == ('notifier', 'fromaddress'):
            self.fromAddressLineEdit.setText(newvalue)
