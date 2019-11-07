import logging

from PyQt5 import QtWidgets, QtCore

from ..project import Project

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class SubWindow(QtWidgets.QMdiSubWindow):
    project: Project

    def __init__(self, parent, project:Project, widget:QtWidgets.QWidget):
        super().__init__(parent)
        self.project = project
        self.setWidget(widget)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose) # delete this subwindow if it is closed
        widget.setAttribute(QtCore.Qt.WA_DeleteOnClose) # delete the underlying widget on close
        self.project.destroyed.connect(self.onProjectDestroyed)
        widget.destroyed.connect(self.onWidgetDestroyed)

    def close(self) -> bool:
        logger.debug('Closing subwindow {}'.format(self.objectName()))
        self.mdiArea().removeSubWindow(self)
        return super().close() # this will automatically call the .close() method of the wrapped widget

    def onProjectDestroyed(self, project):
        logger.debug('PROJECT DESTROYED, subwindow {} deletes itself.'.format(self.objectName()))
        try:
            self.destroy()
        except RuntimeError:
            logger.debug('Underlying c/c++ object deleted')
        logger.debug('Calling deleteLater on subwindow {}'.format(self.objectName()))
        QtWidgets.QApplication.instance().processEvents()
        logger.debug('Exiting onProjectDestroyed()')

    def onWidgetDestroyed(self, widget):
        logger.debug('Underlying widget (name = {}) of subwindow {} destroyed, deleting self.'.format(widget.objectName(), self.objectName()))
        self.destroy()
        QtWidgets.QApplication.instance().processEvents()
        logger.debug('Exiting onWidgetDestroyed')
