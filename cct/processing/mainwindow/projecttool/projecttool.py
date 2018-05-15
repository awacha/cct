from PyQt5 import QtWidgets
from ..toolbase   import ToolBase
from .projecttool_ui import Ui_Form
import configparser
import os

class ProjectTool(ToolBase, Ui_Form):
    projectfilename = None
    def setupUi(self, Form):
        super().setupUi(Form)
        self.saveProjectAsPushButton.clicked.connect(self.onSaveProjectAs)
        self.openProjectPushButton.clicked.connect(self.onOpenProject)

    def onSaveProjectAs(self):
        filename, lastfilter = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save project to...', self.projectfilename if self.projectfilename is not None else '',
            'CPT projects (*.cpt);;All files (*)', 'CPT projects (*.cpt)'
        )
        if not filename:
            return
        self.projectfilename=filename
        self.saveProject()

    def saveProject(self):
        if self.projectfilename is None:
            return
        cp = configparser.ConfigParser()
        for sibling in self.siblings:
            self.siblings[sibling].save_state(cp)
        with open(self.projectfilename,'wt') as f:
            cp.write(f)

    def onOpenProject(self):
        filename, lastfilter = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open project from...', self.projectfilename if self.projectfilename is not None else '',
            'CPT projects (*.cpt);;All files (*)', 'CPT projects (*.cpt)'
        )
        if not filename:
            return
        cp=configparser.ConfigParser()
        cp.read(filename)
        for sibling in self.siblings:
            self.siblings[sibling].load_state(cp)
        self.projectfilename = filename