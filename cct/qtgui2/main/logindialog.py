import logging

import pkg_resources
from PyQt5 import QtWidgets, QtGui

from .logindialog_ui import Ui_Dialog
from ...core2.instrument.instrument import Instrument

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class LoginDialog(QtWidgets.QDialog, Ui_Dialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Dialog):
        super().setupUi(Dialog)
        self.setWindowTitle(f'CCT v{pkg_resources.get_distribution("cct").version} login')
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setText('Login')
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setIcon(QtGui.QIcon.fromTheme('user-info'))
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setIcon(QtGui.QIcon.fromTheme('system-exit'))
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setText('Exit')
        self.resize(self.minimumSizeHint())

    def authenticate(self) -> bool:
        try:
            Instrument.instance().auth.setUser(self.userNameLineEdit.text(), self.passwordLineEdit.text())
            return True
        except (RuntimeError, KeyError) as exc:
            logger.debug(f'Authentication failed with exception {repr(exc)}')
            self.passwordLineEdit.setAutoFillBackground(True)
            pal = self.passwordLineEdit.palette()
            pal.setColor(QtGui.QPalette.Background, QtGui.QColor('red'))
            self.passwordLineEdit.setPalette(pal)
            return False

    def passwordEdited(self):
        pal = self.passwordLineEdit.palette()
        pal.setColor(QtGui.QPalette.Background, self.userNameLineEdit.palette().color(QtGui.QPalette.Background))
        self.passwordLineEdit.setPalette(pal)

    def isOffline(self):
        return self.offlineCheckBox.isChecked()

    def setOffline(self, offline: bool):
        self.offlineCheckBox.setChecked(offline)
