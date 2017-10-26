from PyQt5 import QtWidgets, QtCore

from .headerpopup_ui import Ui_Form


class HeaderPopup(QtWidgets.QWidget, Ui_Form):
    def __init__(self, parent, fields, allfields):
        QtWidgets.QWidget.__init__(self, parent, QtCore.Qt.Popup)
        self.fields = fields
        self.allfields = allfields
        self.setupUi(self)

    applied = QtCore.pyqtSignal()
    closed = QtCore.pyqtSignal()

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.setWindowTitle('Select and sort metadata fields')
        self.listWidget.addItems(
            self.fields + ['-- hidden fields below --'] + [f for f in self.allfields if f not in self.fields])
        self.okPushButton.clicked.connect(self.onOK)
        self.cancelPushButton.clicked.connect(self.onCancel)

    def closeEvent(self, event: QtCore.QEvent):
        self.onCancel()
        event.accept()
        self.closed.emit()

    def onOK(self):
        self.fields = []
        for i in range(self.listWidget.count()):
            it = self.listWidget.item(i)
            if it.text() == '-- hidden fields below --':
                break
            else:
                self.fields.append(it.text())
        self.applied.emit()
        self.close()

    def onCancel(self):
        self.close()
