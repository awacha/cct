from PySide6 import QtWidgets
from PySide6.QtCore import Slot
from .newconnectiondialog_ui import Ui_Dialog
from ....core2.devices.device.frontend import DeviceFrontend


class NewConnectionDialog(QtWidgets.QDialog, Ui_Dialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Dialog):
        super().setupUi(Dialog)
        self.driverClassComboBox.addItems(sorted([sc.devicename for sc in DeviceFrontend.subclasses() if sc.devicename]))
        self.driverClassComboBox.setCurrentIndex(0)
        self.deviceNameLineEdit.textEdited.connect(self.check)
        self.driverClassComboBox.currentIndexChanged.connect(self.check)
        self.hostNameLineEdit.textEdited.connect(self.check)
        self.portSpinBox.valueChanged.connect(self.check)
        self.check()

    @Slot()
    def check(self):
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(
            bool(self.driverClassComboBox.currentText()) and
            bool(self.deviceNameLineEdit.text()) and
            bool(self.hostNameLineEdit.text()) and
            bool(self.portSpinBox.value())
        )

    def devicename(self) -> str:
        return self.deviceNameLineEdit.text()

    def driverClassName(self) -> str:
        return self.driverClassComboBox.currentText()

    def host(self) -> str:
        return self.hostNameLineEdit.text()

    def port(self) -> int:
        return self.portSpinBox.value()