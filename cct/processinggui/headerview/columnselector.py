from typing import List

from PyQt5 import QtCore, QtWidgets

from .columnselector_ui import Ui_Dialog
from ..config import Config
from ..models.headerlist import HeaderList


class ColumnSelectorDialog(QtWidgets.QDialog, Ui_Dialog):
    config:Config

    def __init__(self, parent: QtWidgets.QWidget, config:Config):
        super().__init__(parent)
        self.config=config
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.availableListWidget.clear()
        #self.availableListWidget.addItems(HeaderList.allColumns.values())
        self.fromConfig()
        self.on_selectedListWidget_itemSelectionChanged()
        self.on_availableListWidget_itemSelectionChanged()

    def fromConfig(self):
        self.selectedListWidget.clear()
        self.selectedListWidget.addItems([HeaderList.allColumns[f] for f in self.config.fields])
        self.availableListWidget.clear()
        self.availableListWidget.addItems([label for fieldname, label in HeaderList.allColumns.items() if fieldname not in self.config.fields])

    def toConfig(self):
        labels = [self.selectedListWidget.item(i).text() for i in range(self.selectedListWidget.count())]
        self.config.fields = [[c for c,v in HeaderList.allColumns.items() if v==l][0] for l in labels]

    @QtCore.pyqtSlot()
    def on_addPushButton_clicked(self):
        if not self.availableListWidget.selectedItems():
            return
        labels = [item.text() for item in self.availableListWidget.selectedItems()]
        self.selectedListWidget.addItems(labels)
        for l in labels:
            item = self.availableListWidget.findItems(l, QtCore.Qt.MatchExactly)[0]
            row = self.availableListWidget.row(item)
            item = self.availableListWidget.takeItem(row)


    @QtCore.pyqtSlot()
    def on_removePushButton_clicked(self):
        if not self.selectedListWidget.selectedItems():
            return
        labels = [item.text() for item in self.selectedListWidget.selectedItems()]
        self.availableListWidget.addItems(labels)
        for l in labels:
            item = self.selectedListWidget.findItems(l, QtCore.Qt.MatchExactly)[0]
            row = self.selectedListWidget.row(item)
            item = self.selectedListWidget.takeItem(row)

    @QtCore.pyqtSlot()
    def on_availableListWidget_itemSelectionChanged(self):
        self.addPushButton.setEnabled(bool(self.availableListWidget.selectedItems()))

    @QtCore.pyqtSlot()
    def on_selectedListWidget_itemSelectionChanged(self):
        state = bool(self.selectedListWidget.selectedItems())
        self.removePushButton.setEnabled(state)
        self.moveToTopPushButton.setEnabled(state)
        self.moveUpPushButton.setEnabled(state)
        self.moveDownPushButton.setEnabled(state)
        self.moveToBottomPushButton.setEnabled(state)

    def selectedColumns(self) -> List[str]:
        return [[k for k,l in HeaderList.allColumns.items() if l==label][0]
                for label in [self.selectedListWidget.item(row).text() for row in range(self.selectedListWidget.count())]]