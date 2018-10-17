import os

import appdirs
from PyQt5 import QtWidgets, QtCore, QtGui

from .projectdialog_ui import Ui_Form


class ProjectDialog(QtWidgets.QWidget, Ui_Form):
    projectSelected = QtCore.pyqtSignal(str)

    def __init__(self, mainwindow: QtWidgets.QWidget):
        self.mainwindow = mainwindow
        super().__init__()
        self.projectname = None
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.updateRecentList()
        self.recentsListWidget.itemActivated.connect(self.onRecentSelected)
        self.newPushButton.clicked.connect(self.onNewProject)
        self.openPushButton.clicked.connect(self.onOpenProject)
        self.quitPushButton.clicked.connect(self.onQuit)
        self.move(self.mainwindow.geometry().center() - self.geometry().center())

    def closeEvent(self, event: QtGui.QCloseEvent):
        if not self.projectname:
            self.onQuit()
        event.accept()

    def updateRecentList(self):
        recentsfile = os.path.join(appdirs.user_config_dir('cpt', 'CREDO', roaming=True), 'projecthistory')
        try:
            with open(recentsfile, 'rt') as f:
                for l in f:
                    l = l.strip()
                    if os.path.exists(l) and l.lower().endswith('.cpt'):
                        print('Adding {}'.format(l))
                        self.recentsListWidget.addItem(QtWidgets.QListWidgetItem(l))
                    else:
                        print('Not adding {}'.format(l))
        except FileNotFoundError:
            return

    def onRecentSelected(self, item: QtWidgets.QListWidgetItem):
        self.projectname = item.text()
        self.projectSelected.emit(item.text())
        self.close()

    def onNewProject(self):
        filename, lastfilter = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Select a file name for the new project...', '',
            'CPT projects (*.cpt);;All files (*)', 'CPT projects (*.cpt)'
        )
        if not filename:
            return
        if not filename.endswith('.cpt'):
            filename=filename+'.cpt'
        self.projectname = filename
        self.projectSelected.emit(filename)
        self.close()

    def onOpenProject(self):
        filename, lastfilter = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open a processing project...', '',
            'CPT projects (*.cpt);;All files (*)', 'CPT projects (*.cpt)'
        )
        if not filename:
            return
        self.projectname = filename
        self.projectSelected.emit(filename)
        self.close()

    def onQuit(self):
        self.mainwindow.close()
        self.close()
