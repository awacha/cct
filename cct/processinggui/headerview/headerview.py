import logging

from PyQt5 import QtCore, QtWidgets

from .columnselector import ColumnSelectorDialog
from .headerview_ui import Ui_Form
from ..config import Config
from ..project import Project

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class HeaderView(QtWidgets.QWidget, Ui_Form):
    config:Config=None
    project:Project=None
    columnSelectorDialog:ColumnSelectorDialog=None


    def __init__(self, parent: QtWidgets.QWidget, project:Project, config:Config):
        super().__init__(parent)
        self.config=config
        self.project=project
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.project.headerList)
        logger.debug('The headerlist associated with the header view contains {} rows and {} columns'.format(
            self.project.headerList.rowCount(), self.project.headerList.columnCount()))
        self.columnSelectorDialog = ColumnSelectorDialog(self, self.config)
        self.columnSelectorDialog.accepted.connect(self.onColumnSelectorAccepted)
        self.project.headerList.modelReset.connect(self.resizeTreeColumns)

    def resizeTreeColumns(self):
        for c in range(self.treeView.model().columnCount()):
            self.treeView.resizeColumnToContents(c)

    @QtCore.pyqtSlot()
    def onColumnSelectorAccepted(self):
        logger.debug('Column selector accepted')
        # setting the .fields config item will emit a signal which is caught by the header model, causing it to
        # update the columns.
        self.config.fields = self.columnSelectorDialog.selectedColumns()

    @QtCore.pyqtSlot()
    def on_columnConfigurePushButton_clicked(self):
        self.columnSelectorDialog.open()

    @QtCore.pyqtSlot()
    def on_exportTablePushButton_clicked(self):
        pass

    @QtCore.pyqtSlot()
    def on_reloadHeadersPushButton_clicked(self):
        self.project.reloadHeaders()

    @QtCore.pyqtSlot()
    def on_showCurvePushButton_clicked(self):
        pass

    @QtCore.pyqtSlot()
    def on_showImagePushButton_clicked(self):
        selectedrows = self.treeView.selectionModel().selectedRows(0)
        if not selectedrows:
            return
        for index in selectedrows:
            ex = self.project.loadExposure(self.project.headerList[index.row()])
            self.project.exposureToBeShown.emit(ex)
