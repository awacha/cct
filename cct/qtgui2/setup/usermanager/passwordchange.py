from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import pyqtSlot as Slot

from ....core2.instrument.instrument import Instrument
from .passwordchange_ui import Ui_Form
from ...utils.window import WindowRequiresDevices


class PasswordChange(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.captionLabel.setText(f'Changing password for user {Instrument.instance().auth.username()}')
        self.newPasswordLineEdit.textEdited.connect(self.onPasswordEdited)
        self.repeatLineEdit.textEdited.connect(self.onPasswordEdited)
        self.okPushButton.clicked.connect(self.dochangepassword)
        self.cancelPushButton.clicked.connect(self.close)

    @Slot()
    def onPasswordEdited(self):
        palette = self.newPasswordLineEdit.palette()
        if self.newPasswordLineEdit.text() != self.repeatLineEdit.text():
            palette.setColor(palette.Background, QtGui.QColor('red'))
        else:
            palette.setColor(palette.Background, self.oldPasswordLineEdit.palette().color(palette.Background))
        self.newPasswordLineEdit.setPalette(palette)
        self.repeatLineEdit.setPalette(palette)
        self.okPushButton.setEnabled(
            (self.newPasswordLineEdit.text() == self.repeatLineEdit.text()) and
            (len(self.newPasswordLineEdit.text()) > 0))

    @Slot()
    def dochangepassword(self):
        if not Instrument.instance().auth.currentUser().authenticate(self.oldPasswordLineEdit.text()):
            QtWidgets.QMessageBox.critical(self, 'Request denied', 'This is not your current password.')
            return
        Instrument.instance().auth.changePassword(
            self.newPasswordLineEdit.text(), Instrument.instance().auth.username())
        QtWidgets.QMessageBox.information(self, 'Success', 'Your password has been changed.')
        self.close()

