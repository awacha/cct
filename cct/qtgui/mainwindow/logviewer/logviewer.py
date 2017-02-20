import logging

from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import Qt


from .resource.logviewer_ui import Ui_Form

class LogModel(QtCore.QAbstractItemModel):
    """A model for storing log records.
    """

    columnConfig=[('asctime','Date'), ('levelname', 'Level'),
                  ('origin', 'Origin'), ('message', 'Message')]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records=[]
        self._level = logging.NOTSET

    def index(self, row:int, column:int, parent=None, *args, **kwargs):
        if column <0 or column>=len(self.columnConfig):
            raise ValueError('Invalid column: {}'.format(column))
        recs=self.records()
        if row >= len(recs):
            raise ValueError('Invalid row: {}'.format(row))
        return self.createIndex(row, column, getattr(recs[row],self.columnConfig[column][0]))

    def headerData(self, index, orientation, role=None):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columnConfig[index][1]
        return None

    def parent(self, modelindex=None):
        return QtCore.QModelIndex()

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.records())

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.columnConfig)

    def flags(self, index:QtCore.QModelIndex):
        return Qt.ItemNeverHasChildren | Qt.ItemIsEnabled

    def data(self, modelindex, role=None):
        if role is None:
            role = QtCore.Qt.DisplayRole
        if role == QtCore.Qt.DisplayRole:
            rec=self.records()[modelindex.row()]
            return str(getattr(rec, self.columnConfig[modelindex.column()][0]))
        elif role == QtCore.Qt.BackgroundRole:
            rec = self.records()[modelindex.row()]
            assert isinstance(rec, logging.LogRecord)
            if rec.levelno >= logging.CRITICAL:
                return QtGui.QBrush(Qt.red)
            else:
                return None
        elif role == QtCore.Qt.ForegroundRole:
            rec = self.records()[modelindex.row()]
            assert isinstance(rec, logging.LogRecord)
            if rec.levelno >= logging.CRITICAL:
                return QtGui.QBrush(Qt.black)
            elif rec.levelno >= logging.ERROR:
                return QtGui.QBrush(Qt.red)
            elif rec.levelno >= logging.WARNING:
                return QtGui.QBrush(Qt.darkYellow)
            elif rec.levelno >= logging.INFO:
                return QtGui.QBrush(Qt.black)
            else:
                return QtGui.QBrush(Qt.gray)
        elif role == QtCore.Qt.TextAlignmentRole:
            return Qt.AlignTop | Qt.AlignLeft
        return None

    def append(self, logrecord):
        logrecord.origin=logrecord.module+':{:d}'.format(logrecord.lineno)
        self.beginInsertRows(QtCore.QModelIndex(), len(self.records()),len(self.records()))
        self._records.append(logrecord)
        self.endInsertRows()

    def setLevel(self, level:int):
        self.beginRemoveRows(QtCore.QModelIndex(), 0, len(self.records()))
        self.endRemoveRows()
        self._level=level
        self.beginInsertRows(QtCore.QModelIndex(), 0, len(self.records()))
        self.endInsertRows()

    def level(self):
        return self._level

    def records(self):
        return [r for r in self._records if r.levelno>=self._level]

    def __len__(self):
        return len(self._records)

    def reduceTo(self, length=0):
        if len(self._records)<=length:
            return True
        else:
            self.beginRemoveRows(QtCore.QModelIndex(), 0, len(self)-length-1)
            self._records = self._records[len(self)-length :]
            self.endRemoveRows()

class LogViewer(QtWidgets.QWidget, Ui_Form, logging.Handler):
    def __init__(self, *args, **kwargs):
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        logging.Handler.__init__(self)
        formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
        self.setFormatter(formatter)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        Form.logModel=LogModel()
        Form.logTreeView.setModel(Form.logModel)
        Form.logLevelModel = QtGui.QStandardItemModel()
        Form.logLevelModel.setColumnCount(2)
        Form.filterLevelComboBox.setModel(Form.logLevelModel)
        for i in range(256):
            name = logging.getLevelName(i)
            if not name.startswith('Level '):
                Form.logLevelModel.appendRow([QtGui.QStandardItem(name), QtGui.QStandardItem(str(i))])
        Form.filterLevelComboBox.currentTextChanged.connect(Form.filterLevelChanged)
        Form.keptMessagesSpinBox.valueChanged.connect(Form.keptMessagesChanged)

    def keptMessagesChanged(self):
        self.logModel.reduceTo(self.keptMessagesSpinBox.value())
        self.shownMessagesLabel.setText('{:d} from {:d}'.format(self.logModel.rowCount(), len(self.logModel)))

    def filterLevelChanged(self):
        assert isinstance(self.logLevelModel, QtGui.QStandardItemModel)
        level = int(self.logLevelModel.item(self.filterLevelComboBox.currentIndex(), 1).text())
        self.logModel.setLevel(level)
        self.shownMessagesLabel.setText('{:d} from {:d}'.format(self.logModel.rowCount(), len(self.logModel)))

    def emit(self, record):
        self.format(record)
        self.logModel.append(record)
        self.shownMessagesLabel.setText('{:d} from {:d}'.format(self.logModel.rowCount(), len(self.logModel)))
        if self.autoscrollCheckBox.checkState() == Qt.Checked:
            self.logTreeView.scrollToBottom()

