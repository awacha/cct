from PyQt5 import QtWidgets, QtCore
from .backgroundtool_ui import Ui_Form
from .backgroundsubtractionmodel import BackgroundSubtractionModel, ComboBoxDelegate
from ..toolbase import ToolBase, HeaderModel

class BackgroundTool(ToolBase, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.backgroundList=BackgroundSubtractionModel()
        self.backgroundListTreeView.setModel(self.backgroundList)
        self.backgroundListDelegate = ComboBoxDelegate()
        self.backgroundListTreeView.setItemDelegateForColumn(0, self.backgroundListDelegate)
        self.backgroundListTreeView.setItemDelegateForColumn(1, self.backgroundListDelegate)
        self.backgroundListAddPushButton.clicked.connect(self.onAddBackgroundListElement)
        self.backgroundListDeletePushButton.clicked.connect(self.onDeleteBackgroundListElement)
        self.backgroundListClearPushButton.clicked.connect(self.onClearBackgroundList)
        self.configWidgets = []

    def onAddBackgroundListElement(self):
        self.backgroundList.addSample(None)

    def onDeleteBackgroundListElement(self):
        while self.backgroundListTreeView.selectedIndexes():
            sel = self.backgroundListTreeView.selectedIndexes()
            self.backgroundList.removeRow(sel[0].row(), QtCore.QModelIndex())

    def onClearBackgroundList(self):
        self.backgroundList.clear()

    def updateBackgroundList(self):
        self.backgroundList.setSampleNameList(sorted(self.headerModel.sampleNames()))
        for c in range(self.backgroundList.columnCount()):
            self.backgroundListTreeView.resizeColumnToContents(c)

    def setHeaderModel(self, headermodel:HeaderModel):
        super().setHeaderModel(headermodel)
        self.updateBackgroundList()

    def getBackgroundSubtractionList(self):
        return self.backgroundList.getBackgroundSubtractionList()

    def getEnabledSampleNameList(self):
        return self.backgroundList.getEnabledSampleNameList()
