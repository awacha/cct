from PyQt5 import QtWidgets

from .cpw_ui import Ui_Dialog
from ....core.instrument.instrument import Instrument
from ....core.instrument.privileges import PRIV_USERMAN
from ....core.services import ServiceError
from ....core.services.accounting import Accounting


class ChangePasswordDialog(QtWidgets.QDialog, Ui_Dialog):
    def __init__(self, parent, credo:Instrument):
        super().__init__(parent)
        self.credo = credo
        self.setupUi(self)

    def setupUi(self, Dialog):
        Ui_Dialog.setupUi(self, Dialog)
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        self.userNameComboBox.addItems(sorted([u for u in acc.get_usernames()]))
        self.userNameComboBox.setCurrentIndex(self.userNameComboBox.findText(acc.get_user().username))
        self.userNameComboBox.setEnabled(acc.has_privilege(PRIV_USERMAN))

    def accept(self):
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        if self.newPasswordLineEdit.text() != self.repeatedPasswordLineEdit.text():
            QtWidgets.QMessageBox.critical(self, 'Cannot change password', 'Repeated password does not match')
            return super().accept()
        else:
            try:
                acc.change_local_password(self.userNameComboBox.currentText(), self.ownPasswordLineEdit.text(), self.newPasswordLineEdit.text())
            except ServiceError as se:
                QtWidgets.QMessageBox.critical(self, 'Cannot change password', se.args[0])
            return super().accept()
