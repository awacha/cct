from PyQt5 import QtWidgets
from .averaging_ui import Ui_Form
from .processingwindow import ProcessingWindow


class AveragingWindow(ProcessingWindow, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.project.summarization)
