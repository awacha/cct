from PyQt5 import QtWidgets, QtCore
from .accounting_ui import Ui_Frame
from ....core2.instrument.instrument import Instrument


class AccountingIndicator(QtWidgets.QFrame, Ui_Frame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Frame):
        super().setupUi(Frame)
        self.projectIDComboBox.clear()
        self.projectIDComboBox.setModel(Instrument.instance().projects)
        self.projectIDComboBox.setModelColumn(0)
        view = QtWidgets.QTreeView()
        view.setModel(Instrument.instance().projects)
        view.setSelectionBehavior(view.SelectRows)
        view.setHeaderHidden(True)
        view.setRootIsDecorated(False)
        view.setMinimumWidth(600)
        view.setAlternatingRowColors(True)
        view.setWordWrap(True)
        view.resizeColumnToContents(0)
        view.resizeColumnToContents(1)
        view.resizeColumnToContents(2)
        self.projectIDComboBox.setSizeAdjustPolicy(self.projectIDComboBox.AdjustToContents)
        self.projectIDComboBox.setView(view)
        self.projectIDComboBox.currentIndexChanged.connect(self.onProjectChanged)
        self.projectIDComboBox.setCurrentIndex(self.projectIDComboBox.findText(Instrument.instance().projects.projectID()))

    def onProjectChanged(self):
        Instrument.instance().projects.setProject(self.projectIDComboBox.currentText())
        self.titleLineEdit.setText(Instrument.instance().projects.project().title)
        self.titleLineEdit.setToolTip(self.titleLineEdit.text())
        self.titleLineEdit.home(False)
        self.proposerLineEdit.setText(Instrument.instance().projects.project().proposer)
        self.proposerLineEdit.setToolTip(self.proposerLineEdit.text())
        self.proposerLineEdit.home(False)
