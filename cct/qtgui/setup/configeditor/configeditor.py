import logging

from PyQt5 import QtWidgets, QtCore

from .configeditor_ui import Ui_Form
from .configstore import ConfigStore
from ...core.mixins import ToolWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ConfigEditor(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self._editorwidget = None
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.model = ConfigStore(self.credo)
        self.treeView.setModel(self.model)
        self.treeView.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.resetButton.clicked.connect(self.onReset)
        self.applyButton.clicked.connect(self.onApply)

    def onSelectionChanged(self):
        si = self.treeView.selectionModel().selectedIndexes()
        self._path = self.model.getPath(si[0])
        value = self.model.getValue(si[0])
        self.pathLabel.setText('.'.join([str(p) for p in self._path]))
        if self._editorwidget is not None:
            assert isinstance(self._editorwidget, QtWidgets.QWidget)
            self.editorLayout.removeWidget(self._editorwidget)
            self._editorwidget.disconnect()
            self._editorwidget.deleteLater()
            del self._editorwidget
            self._editorwidget = None
        if isinstance(value, str):
            self._editorwidget = QtWidgets.QLineEdit(value, None)
            assert isinstance(self._editorwidget, QtWidgets.QLineEdit)
            self._editorwidget.textChanged.connect(self.onValueChangedInEditor)
        elif isinstance(value, float):
            self._editorwidget = QtWidgets.QDoubleSpinBox(None)
            self._editorwidget.setMinimum(-1e10)
            self._editorwidget.setMaximum(1e10)
            self._editorwidget.setDecimals(6)
            self._editorwidget.setValue(value)
            self._editorwidget.valueChanged.connect(self.onValueChangedInEditor)
        elif isinstance(value, int):
            self._editorwidget = QtWidgets.QSpinBox(None)
            self._editorwidget.setMinimum(-1e10)
            self._editorwidget.setMaximum(1e10)
            self._editorwidget.setValue(value)
            self._editorwidget.valueChanged.connect(self.onValueChangedInEditor)
        elif isinstance(value, bool):
            self._editorwidget = QtWidgets.QPushButton(None)
            self._editorwidget.setCheckable(True)
            if value:
                self._editorwidget.setChecked(True)
                self._editorwidget.setText('True')
            else:
                self._editorwidget.setChecked(False)
                self._editorwidget.setText('False')
            self._editorwidget.toggled.connect(self.onValueChangedInEditor)
        else:
            # do not try to edit other types of values, including dicts.
            return
        self.editorLayout.addWidget(self._editorwidget)
        self.applyButton.setEnabled(False)
        self.resetButton.setEnabled(False)

    def onValueChangedInEditor(self):
        self.applyButton.setEnabled(True)
        self.resetButton.setEnabled(True)

    def editorValue(self):
        if isinstance(self._editorwidget, QtWidgets.QPushButton):
            return self._editorwidget.isChecked()
        elif isinstance(self._editorwidget, QtWidgets.QLineEdit):
            return self._editorwidget.text()
        elif isinstance(self._editorwidget, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)):
            return self._editorwidget.value()
        else:
            raise TypeError(self._editorwidget)

    def onApply(self):
        selectedindex = self.treeView.selectionModel().selectedIndexes()[0]
        path = self.model.getPath(selectedindex)
        logger.debug('Applying changes to path: {}. New value: {}'.format(path, self.editorValue()))
        self.model.setData(selectedindex, self.editorValue(), QtCore.Qt.EditRole)
        self.applyButton.setEnabled(False)
        self.resetButton.setEnabled(False)
        self.treeView.selectionModel().select(selectedindex, QtCore.QItemSelectionModel.ClearAndSelect)

    def onReset(self):
        return self.onSelectionChanged()
