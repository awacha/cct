from PyQt5 import QtWidgets, QtCore
from .dbconnection_ui import Ui_GroupBox

class DBConnection(QtWidgets.QGroupBox, Ui_GroupBox):
    newConnection = QtCore.pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

    def setupUi(self, GroupBox):
        super().setupUi(GroupBox)
        self.connectPushButton.clicked.connect(self.onConnect)
        self.browseSqlite3DBFilePushButton.clicked.connect(self.onBrowse)

    def dbUrl(self):
        if self.dbEngineComboBox.currentText()=='SQLite3':
            return 'sqlite+pysqlite://'+self.sqlite3DBFileLineEdit.text()
        elif self.dbEngineComboBox.currentText() == 'MySQL / MariaDB':
            if self.mysqlUserNameCheckBox.isChecked():
                auth=self.mysqlUserNameLineEdit.text()+':'+self.mysqlPasswordLineEdit.text()+'@'
            else:
                auth=''
            return 'mysql+pymysql://'+auth+self.mysqlServerLineEdit.text()+':{:d}'.format(self.mysqlPortSpinBox.value())+'/'+self.mysqlDatabaseLineEdit.text()

    def onConnect(self):
        self.newConnection.emit(self.dbUrl())

    def onBrowse(self):
        filename, filtername = QtWidgets.QFileDialog.getOpenFileName(self, 'Select database file', '', 'SQLite3 databases (*.db);;All files (*)', 'SQLite3 databases (*.db)')
        if filename:
            self.sqlite3DBFileLineEdit.setText(filename)