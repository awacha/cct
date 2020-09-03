from .logindialog_ui import Ui_Form
from PyQt5 import QtWidgets, QtGui, QtCore
from ...core2.instrument.instrument import Instrument


class LoginDialog(QtWidgets.QWidget, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.loginPushButton.clicked.connect(self.authenticate)
        self.quitPushButton.clicked.connect(self.close)

    def authenticate(self):
        try:
            Instrument.instance().auth.setUser(self.userNameLineEdit.text(), self.passwordLineEdit.text())
            self.close()
        except RuntimeError:
            self.passwordLineEdit.setAutoFillBackground(True)
            pal = self.passwordLineEdit.palette()
            pal.setColor(QtGui.QPalette.Background, QtGui.QColor('red'))
            self.passwordLineEdit.setPalette(pal)

    def passwordEdited(self):
        pal = self.passwordLineEdit.palette()
        pal.setColor(QtGui.QPalette.Background, self.userNameLineEdit.palette().color(QtGui.QPalette.Background))
        self.passwordLineEdit.setPalette(pal)
        
    def isOffline(self):
        return self.offlineCheckBox.isChecked()

    def setOffline(self, offline: bool):
        self.offlineCheckBox.setChecked(offline)
