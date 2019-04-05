import weakref

from PyQt5 import QtWidgets, QtGui

from .logindialog_ui import Ui_Dialog


class LogInDialog(QtWidgets.QDialog, Ui_Dialog):
    def __init__(self, credo, onlinemode:bool):
        self.credo = weakref.proxy(credo)
        QtWidgets.QDialog.__init__(self, None)
        self.setupUi(self)
        self.onlineCheckBox.setChecked(onlinemode)

    def setupUi(self, Dialog):
        Ui_Dialog.setupUi(self, Dialog)
        self.defaultbase = self.passwordLineEdit.palette().color(QtGui.QPalette.Base)
        self.passwordLineEdit.setBackgroundRole(QtGui.QPalette.Base)
        self.passwordLineEdit.textChanged.connect(self.onTextChanged)
        self.operatorLineEdit.setFocus()

    def onTextChanged(self):
        palette = self.passwordLineEdit.palette()
        palette.setColor(QtGui.QPalette.Base, self.defaultbase)
        self.passwordLineEdit.setPalette(palette)

    def accept(self):
        if self.credo.services['accounting'].authenticate(self.operatorLineEdit.text(), self.passwordLineEdit.text()):
            return super().accept()
        else:
            palette = self.passwordLineEdit.palette()
            palette.setColor(QtGui.QPalette.Base, QtGui.QColor('red'))
            self.passwordLineEdit.setPalette(palette)
            return False

    def isOnlineEnabled(self) -> bool:
        return self.onlineCheckBox.isChecked()

    def reject(self):
        return super().reject()
