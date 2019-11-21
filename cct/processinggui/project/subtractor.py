from PyQt5 import QtWidgets

from .samplenamecomboboxdelegate import SampleNameComboBoxDelegate
from .submethodcomboboxdelegate import SubtractionMethodComboBoxDelegate
from .subtractionparameterdelegate import SubtractionParameterDelegate
from .subtractor_ui import Ui_Form
from ..models.subtraction import SubtractionModel


class Subtractor(QtWidgets.QWidget, Ui_Form):
    def __init__(self, parent: QtWidgets.QWidget = None, project: "Project" = None):
        super().__init__(parent)
        self.project = project
        if project is None:
            raise ValueError('Subtractor needs a project')
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.model = SubtractionModel()
        self.treeView.setModel(self.model)
        self.subParDelegate = SubtractionParameterDelegate()
        self.treeView.setItemDelegateForColumn(3, self.subParDelegate)
        self.bgnameDelegate = SampleNameComboBoxDelegate()
        self.treeView.setItemDelegateForColumn(1, self.bgnameDelegate)
        self.submethodDelegate =SubtractionMethodComboBoxDelegate()
        self.treeView.setItemDelegateForColumn(2, self.submethodDelegate)

    def updateList(self):
        for samplename in sorted(self.project.headerList.samples()):
            if samplename not in self.model:
                self.model.add(samplename)
        for c in range(self.model.columnCount()):
            self.treeView.resizeColumnToContents(c)
