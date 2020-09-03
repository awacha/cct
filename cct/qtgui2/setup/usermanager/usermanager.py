from PyQt5 import QtWidgets, QtCore, QtGui
from ...utils.window import WindowRequiresDevices
from .usermanager_ui import Ui_Form
from ....core2.instrument.components.auth.privilege import Privilege
from ....core2.instrument.components.auth.usermanager import User


class UserManager(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.instrument.auth.currentUserChanged.connect(self.onCurrentUserChanged)
        self.userListTreeView.setModel(self.instrument.auth)
        self.addUserPushButton.clicked.connect(self.addUser)
        self.removeUserPushButton.clicked.connect(self.removeUser)
        self.updateEditPushButton.clicked.connect(self.updateEditedValues)
        self.userListTreeView.selectionModel().selectionChanged.connect(self.fetchUserData)
        self.resetPushButton.clicked.connect(self.fetchUserData)
        self.passwordLineEdit.textEdited.connect(self.passwordEdit)
        self.passwordRepeatLineEdit.textEdited.connect(self.passwordEdit)
        for priv in Privilege:
            itm = QtWidgets.QListWidgetItem(priv.name)
            itm.setFlags(QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
            itm.setCheckState(QtCore.Qt.Unchecked)
            self.privilegeListWidget.addItem(itm)
        self.onCurrentUserChanged()
        for c in range(self.instrument.auth.columnCount()):
            self.userListTreeView.resizeColumnToContents(c)

    def passwordEdit(self):
        pal = self.passwordLineEdit.palette()
        if self.passwordLineEdit.text() != self.passwordRepeatLineEdit.text():
            pal.setColor(pal.Background, QtGui.QColor('red'))
        else:
            pal.setColor(pal.Background, self.emailLineEdit.palette().color(pal.Background))
        self.passwordLineEdit.setPalette(pal)
        self.passwordRepeatLineEdit.setPalette(pal)

    def fetchUserData(self):
        user = self.userListTreeView.selectionModel().currentIndex().data(QtCore.Qt.UserRole)
        assert isinstance(user, User)
        self.onCurrentUserChanged()  # set widget permissions
        self.userNameLabel.setText(user.username)
        self.firstNameLineEdit.setText(user.firstname)
        self.lastnameLineEdit.setText(user.lastname)
        self.emailLineEdit.setText(user.email)
        self.ldapdnLineEdit.setText(user.ldapdn)
        self.krbprincipalLineEdit.setText(user.kerberosprincipal)
        self.passwordLineEdit.setText('')
        self.passwordRepeatLineEdit.setText('')
        for row in range(self.privilegeListWidget.count()):
            item = self.privilegeListWidget.item(row)
            priv = [p for p in Privilege if p.name == item.text()][0]
            item.setCheckState(QtCore.Qt.Checked if user.hasPrivilege(priv) else QtCore.Qt.Unchecked)

    def addUser(self):
        username, ok = QtWidgets.QInputDialog.getText(self, 'Create new user', 'User name of the new user:')
        if not ok:
            return
        if username in self.instrument.auth:
            QtWidgets.QMessageBox.critical(self, 'Cannot create user', f'User {username} already exists.')
        self.instrument.auth.addUser(username)

    def removeUser(self):
        self.instrument.auth.removeUser(
            self.userListTreeView.selectionModel().currentIndex().data(QtCore.Qt.UserRole).username)

    def updateEditedValues(self):
        password, ok = QtWidgets.QInputDialog.getText(self, 'Authenticate', 'Please type your password:', QtWidgets.QLineEdit.Password, '')
        if not ok:
            return
        if not self.instrument.auth[self.instrument.auth.username()].authenticate(password):
            QtWidgets.QMessageBox.critical(self, 'Permission denied', 'Authentication error')
        user = self.userListTreeView.selectionModel().currentIndex().data(QtCore.Qt.UserRole)
        assert isinstance(user, User)
        if (user.username == self.instrument.auth.username()) or (self.instrument.auth.hasPrivilege(Privilege.UserManagement)):
            # these properties can be self-edited
            if self.firstNameLineEdit.text() != user.firstname:
                user.firstname = self.firstNameLineEdit.text()
            if self.lastnameLineEdit.text() != user.lastname:
                user.lastname = self.lastnameLineEdit.text()
            if self.emailLineEdit.text() != user.email:
                user.email = self.emailLineEdit.text()
            if self.passwordLineEdit.text():
                if not self.passwordLineEdit.text() == self.passwordRepeatLineEdit.text():
                    QtWidgets.QMessageBox.critical(self, 'Password mismatch', 'Password and repetition do not match.')
                else:
                    user.setPassword(self.passwordLineEdit.text())
        if self.instrument.auth.hasPrivilege(Privilege.UserManagement):
            # these properties can only be edited by user managers
            if user.ldapdn != self.ldapdnLineEdit.text():
                user.setLDAPdn(self.ldapdnLineEdit.text())
            if user.kerberosprincipal != self.krbprincipalLineEdit.text():
                user.setKerberosPrincipal(self.krbprincipalLineEdit.text())
            for row in range(self.privilegeListWidget.count()):
                priv = [p for p in Privilege if p.name == self.privilegeListWidget.item(row).text()][0]
                if self.privilegeListWidget.item(row).checkState() == QtCore.Qt.Checked:
                    user.grantPrivilege(priv)
                else:
                    user.revokePrivilege(priv)
        self.instrument.auth.saveToConfig()
        self.fetchUserData()

    def onCurrentUserChanged(self):
        # the current authenticated user has changed or the currently selected user has changed: set widget permissions
        widgets_only_usermanagers_can_edit = [self.ldapdnLineEdit, self.krbprincipalLineEdit, self.privilegeListWidget]
        widgets_self_can_edit = [self.firstNameLineEdit, self.lastnameLineEdit, self.emailLineEdit, self.passwordLineEdit, self.passwordRepeatLineEdit]
        if not self.userListTreeView.selectionModel().currentIndex().isValid():
            # no selection
            for widget in widgets_only_usermanagers_can_edit + widgets_self_can_edit + [self.removeUserPushButton]:
                widget.setEnabled(False)
            return
        user = self.userListTreeView.selectionModel().currentIndex().data(QtCore.Qt.UserRole)
        assert isinstance(user, User)
        for widget in widgets_only_usermanagers_can_edit + [self.addUserPushButton]:
            widget.setEnabled(self.instrument.auth.hasPrivilege(Privilege.UserManagement))
        for widget in widgets_self_can_edit:
            if not widget.isEnabled():  # do not disable if alrady enabled because of UserManagement privilege
                widget.setEnabled(user.username == self.instrument.auth.username())
        self.removeUserPushButton.setEnabled(
            self.instrument.auth.hasPrivilege(Privilege.UserManagement)
            and (user.username != self.instrument.auth.username()))  # the user cannot remove his/herself

