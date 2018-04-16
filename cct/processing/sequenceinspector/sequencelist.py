from PyQt5 import QtCore, QtWidgets
import sys

from .sequencelist_ui import Ui_Form
from .sequencemodel import SequenceModel
from .dbconnection import DBConnection

class SequenceList(QtWidgets.QWidget, Ui_Form):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.toolBox.removeItem(0)
        self.dbConnectionPage = DBConnection()
        self.toolBox.addItem(self.dbConnectionPage,'Database connection')
        self.dbConnectionPage.newConnection.connect(self.onNewConnection)
        self.sequencemodel = None

    def onNewConnection(self, url:str):
        try:
            newmodel = SequenceModel(url)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, 'Error connecting', 'Error while connecting to database: {}'.format(exc))
            return
        try:
            self.sequencemodel.cleanup()
            del self.sequencemodel
        except AttributeError:
            pass
        self.sequencemodel = newmodel
        self.treeView.setModel(self.sequencemodel)

def run():
    app = QtWidgets.QApplication(sys.argv)
    mw = SequenceList()
    mw.setWindowTitle('Browse SAXS sequences')
    mw.show()
    result = app.exec_()
    mw.deleteLater()
    app.deleteLater()
    sys.exit(result)
