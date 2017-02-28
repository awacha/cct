from PyQt5 import QtWidgets, QtCore

from .simpleeditablelist_ui import Ui_GroupBox


class SimpleEditableList(QtWidgets.QGroupBox, Ui_GroupBox):
    defaultValue = 0.0

    def __init__(self, *args, **kwargs):
        QtWidgets.QGroupBox.__init__(self, *args, **kwargs)
        self.setupUi(self)

    def setAllItemsEditable(self):
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            assert isinstance(item, QtWidgets.QListWidgetItem)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)

    def items(self):
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            assert isinstance(item, QtWidgets.QListWidgetItem)
            yield item.data(QtCore.Qt.DisplayRole)

    def addItems(self, lis):
        self.listWidget.addItems([str(l) for l in lis])
        self.setAllItemsEditable()

    def setupUi(self, GroupBox):
        Ui_GroupBox.setupUi(self, GroupBox)
        self.addPushButton.clicked.connect(self.onAddItem)
        self.removePushButton.clicked.connect(self.onRemoveItem)
        self.sortPushButton.clicked.connect(self.onSortList)

    def onAddItem(self):
        self.listWidget.addItems([str(self.defaultValue)])
        self.setAllItemsEditable()

    def onRemoveItem(self):
        while self.listWidget.selectedIndexes():
            self.listWidget.takeItem(self.listWidget.selectedIndexes()[0].row())
        self.setAllItemsEditable()

    def onSortList(self):
        self.listWidget.sortItems(QtCore.Qt.AscendingOrder)
        self.setAllItemsEditable()
