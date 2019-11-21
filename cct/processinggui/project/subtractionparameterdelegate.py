import logging

from PyQt5 import QtCore, QtWidgets

from ..models.subtraction import Subtraction

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class RangeSpinBox(QtWidgets.QWidget):
    layout: QtWidgets.QHBoxLayout
    left: QtWidgets.QDoubleSpinBox
    right: QtWidgets.QDoubleSpinBox

    def __init__(self, parent):
        super().__init__(parent, QtCore.Qt.Widget)
        self.layout = QtWidgets.QHBoxLayout(self)
        self.left=QtWidgets.QDoubleSpinBox(self)
        self.right = QtWidgets.QDoubleSpinBox(self)
        self.layout.setContentsMargins(0,0,0,0)
        label = QtWidgets.QLabel('-')
        self.layout.addWidget(self.left)
        self.layout.addWidget(label)
        self.layout.addWidget(self.right)
        self.left.setRange(0, 9999)
        self.right.setRange(0, 9999)
        self.left.setDecimals(4)
        self.right.setDecimals(4)
        self.setAutoFillBackground(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.adjustSize()
        self.left.setVisible(True)
        self.right.setVisible(True)
        self.setVisible(True)
        self.repaint()


class SubtractionParameterDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)

    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        sub = index.model()[index]
        assert isinstance(sub, Subtraction)
        logger.debug('Subtracting metod: {}. Creating editor.'.format(sub.scalingmethod))
        if sub.scalingmethod == 'None':
            logger.debug('Raising uneditable exception.')
            raise ValueError('If the subtraction type is "None", the parameters cannot be edited.')
        elif sub.scalingmethod in ['Interval', 'Power-law']:
            logger.debug('Creating an editor for interval / power-law')
            editor = RangeSpinBox(parent)
        elif sub.scalingmethod == 'Constant':
            logger.debug('Creating editor for constant.')
            editor = QtWidgets.QDoubleSpinBox(parent)
            editor.setRange(0, 999999)
            editor.setDecimals(6)
            editor.setValue(1)
            editor.setFrame(False)
        else:
            logger.debug('Raising invalid method exception.')
            raise ValueError('Invalid subtraction method: {}'.format(sub.scalingmethod))
        logger.debug('Returning editor.')
        return editor

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex) -> None:
        logger.debug('Setting Editor data')
        sub = index.model()[index]
        assert isinstance(sub, Subtraction)
        if sub.scalingmethod == 'None':
            raise ValueError('If the subtraction type is "None", the parameters cannot be edited.')
        elif sub.scalingmethod in ['Interval', 'Power-law']:
            left, right = index.data(QtCore.Qt.EditRole)
            logging.debug('Setting editor data for interval / power-law: {}, {}'.format(left, right))
            editor.left.setValue(left)
            editor.right.setValue(right)
            logging.debug('Values: {}, {}'.format(editor.left.value(),
                                                  editor.right.value()))
        elif sub.scalingmethod == 'Constant':
            editor.setValue(index.data(QtCore.Qt.EditRole))
        else:
            raise ValueError('Invalid subtraction method: {}'.format(sub.scalingmethod))
        logger.debug('Editor data has been set.')

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        logger.debug('Updating model data')
        sub = index.model()[index]
        assert isinstance(sub, Subtraction)
        if sub.scalingmethod == 'None':
            raise ValueError('If the subtraction type is "None", the parameters cannot be edited.')
        elif sub.scalingmethod in ['Interval', 'Power-law']:
            model.setData(index, (editor.left.value(),
                                  editor.right.value()), QtCore.Qt.EditRole)
            logging.debug('Updated model data from interval / power-law editor.')
        elif sub.scalingmethod == 'Constant':
            model.setData(index, editor.value(), QtCore.Qt.EditRole)
        else:
            raise ValueError('Invalid subtraction method: {}'.format(sub.scalingmethod))
        logger.debug('Model data has been updated')

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                             index: QtCore.QModelIndex) -> None:
        logger.debug('Updating editor geometry.')
        editor.setGeometry(option.rect)
        editor.repaint()
        logger.debug('Editor geometry: {}'.format(editor.geometry()))
        logger.debug('Editor size hint: {}'.format(editor.sizeHint()))
        logger.debug('Editor geometry set.')

    def sizeHint(self, option: 'QStyleOptionViewItem', index: QtCore.QModelIndex) -> QtCore.QSize:
        sb = QtWidgets.QDoubleSpinBox()
        try:
            return QtCore.QSize(int(sb.sizeHint().width()*2.5), sb.sizeHint().height())
        finally:
            sb.destroy()

