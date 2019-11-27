from PyQt5 import QtCore, QtGui, QtWidgets

from .processor import JobRecord


class ProgressBarDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent:QtWidgets.QWidget=None):
        super().__init__(parent)

    def paint(self, painter:QtGui.QPainter, option:QtWidgets.QStyleOptionViewItem, index:QtCore.QModelIndex):
        data = index.data(QtCore.Qt.UserRole)
        assert isinstance(data, JobRecord)
        if data.isRunning:
            pbaroption = QtWidgets.QStyleOptionProgressBar()
            pbaroption.state = QtWidgets.QStyle.State_Enabled
            pbaroption.direction = QtWidgets.QApplication.layoutDirection()
            pbaroption.rect = option.rect
            pbaroption.fontMetrics = QtWidgets.QApplication.fontMetrics()
            pbaroption.minimum = 0
            pbaroption.maximum = data.total if data.total is not None else 0
            pbaroption.textAlignment = QtCore.Qt.AlignCenter
            pbaroption.textVisible = True
            pbaroption.progress = data.current if data.current is not None else 0
            pbaroption.text = data.statusmessage
            QtWidgets.QApplication.style().drawControl(QtWidgets.QStyle.CE_ProgressBar, pbaroption, painter)
        else:
            super().paint(painter, option, index)

