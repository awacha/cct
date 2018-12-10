from PyQt5 import QtWidgets, QtCore

from .simpleeditablelist_ui import Ui_GroupBox


class SimpleEditableList(QtWidgets.QGroupBox, Ui_GroupBox):
    defaultValue = 0.0
    listChanged = QtCore.pyqtSignal(list)

    def __init__(self, parent, type_function, repr_function):
        QtWidgets.QGroupBox.__init__(self, parent=parent)
        self.type_function=type_function
        self.repr_function=repr_function
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
            yield self.type_function(item.data(QtCore.Qt.DisplayRole))

    def addItems(self, lis):
        self.listWidget.addItems([self.repr_function(self.type_function(l)) for l in lis])
        self.setAllItemsEditable()
        self.listChanged.emit(list(self.items()))

    def setupUi(self, GroupBox):
        Ui_GroupBox.setupUi(self, GroupBox)
        self.addPushButton.clicked.connect(self.onAddItem)
        self.removePushButton.clicked.connect(self.onRemoveItem)
        self.sortPushButton.clicked.connect(self.onSortList)
        self.listWidget.itemChanged.connect(self.onListItemEdited)

    def onAddItem(self):
        self.listWidget.addItems([self.repr_function(self.type_function(self.defaultValue))])
        self.setAllItemsEditable()
        self.listChanged.emit(list(self.items()))

    def onRemoveItem(self):
        while self.listWidget.selectedIndexes():
            self.listWidget.takeItem(self.listWidget.selectedIndexes()[0].row())
        self.setAllItemsEditable()
        self.listChanged.emit(list(self.items()))

    def onSortList(self):
        self.listWidget.sortItems(QtCore.Qt.AscendingOrder)
        self.setAllItemsEditable()
        self.listChanged.emit(list(self.items()))

    def onListItemEdited(self):
        self.listChanged.emit(list(self.items()))
