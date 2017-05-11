from PyQt5 import QtWidgets, QtCore

from .users_ui import Ui_Form
from ...core.mixins.toolwindow import ToolWindow
from ....core.instrument.privileges import PrivilegeLevel, PRIV_USERMAN
from ....core.services.accounting import Accounting, User


class UserManager(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_privilege = PRIV_USERMAN
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        ToolWindow.__init__(self, credo)
        self._accounting_connections=[]
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        self.usersListWidget.currentItemChanged.connect(self.onUserSelected)
        self.privilegeLevelComboBox.addItems([p.name for p in sorted(PrivilegeLevel.all_privileges(), key=lambda p:p.ordinal)])
        self.addPushButton.clicked.connect(self.onAddUser)
        self.removePushButton.clicked.connect(self.onRemoveUser)
        self.updatePushButton.clicked.connect(self.onUpdateUser)
        self.emailAddressLineEdit.textChanged.connect(self.onEdit)
        self.firstNameLineEdit.textChanged.connect(self.onEdit)
        self.lastNameLineEdit.textChanged.connect(self.onEdit)
        self.privilegeLevelComboBox.currentIndexChanged.connect(self.onEdit)

    def onEdit(self):
        self.updatePushButton.setEnabled(True)

    def onUserSelected(self):
        username = self.selectedUser()
        self.usernameLabel.setText(username)
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        user=acc.get_user(username)
        assert isinstance(user, User)
        self.firstNameLineEdit.setText(user.firstname)
        self.lastNameLineEdit.setText(user.lastname)
        self.emailAddressLineEdit.setText(user.email)
        self.privilegeLevelComboBox.setCurrentIndex(self.privilegeLevelComboBox.findText(user.privlevel.name))
        self.updatePushButton.setEnabled(False)
        self.removePushButton.setEnabled(username != acc.get_user().username)

    def selectedUser(self):
        return self.usersListWidget.currentItem().text()

    def onUserListChanged(self, acc:Accounting):
        selected = self.selectedUser()
        self.usersListWidget.clear()
        self.usersListWidget.addItems(sorted(acc.get_usernames()))
        self.usersListWidget.setCurrentIndex(0)
        try:
            self.selectUser(selected)
        except IndexError:
            pass

    def cleanup(self):
        for c in self._accounting_connections:
            self.credo.services['accounting'].disconnect(c)
        self._accounting_connections=[]
        super().cleanup()

    def onAddUser(self):
        username, ok = QtWidgets.QInputDialog.getText(self, 'Add user', label='Login name for the new user:')
        if not ok: return
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        acc.add_user(username,'First name', 'Last name')
        self.selectUser(username)

    def selectUser(self, username):
        self.usersListWidget.setCurrentItem(self.usersListWidget.findItems(username, QtCore.Qt.MatchExactly)[0])


    def onRemoveUser(self):
        try:
            self.credo.services['accounting'].delete_user(self.selectedUser())
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self,'Cannot remove user',exc.args[0])
            return

    def onUpdateUser(self):
        acc=self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        acc.update_user(self.selectedUser(), self.firstNameLineEdit.text(),
                        self.lastNameLineEdit.text(),
                        PrivilegeLevel.get_priv(self.privilegeLevelComboBox.currentText()),
                        self.emailAddressLineEdit.text())
        self.updatePushButton.setEnabled(False)