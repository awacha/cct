import enum
from typing import Optional

from PyQt5 import QtWidgets, QtCore, QtGui
import logging

from .filebrowsers import getSaveFile, getOpenFile, getDirectory

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class FileSelectorDelegate(QtWidgets.QStyledItemDelegate):
    """A treeview edit delegate for presenting choices in a combo box

    The current value is taken from the EditRole. The list of choices is in UserRole.
    """
    class Mode(enum.Enum):
        ExistingDirectory = enum.auto()
        OpenFile = enum.auto()
        SaveFile = enum.auto()
    _filter: str = 'All files (*)'
    _defaultfilter: str = 'All files (*)'
    _caption: Optional[str] = None
    _mode: Mode = Mode.SaveFile

    def mode(self) -> Mode:
        return self._mode

    def setMode(self, mode: Mode):
        self._mode = mode

    def caption(self):
        if self._caption is None:
            if self._mode is self.Mode.ExistingDirectory:
                return 'Select directory...'
            elif self._mode is self.Mode.OpenFile:
                return 'Select file to open...'
            elif self._mode is self.Mode.SaveFile:
                return 'Select file to save to...'
            else:
                assert False
        else:
            return self._caption

    def setCaption(self, caption: str):
        self._caption = caption

    def filter(self) -> str:
        return self._filter

    def setFilter(self, filter: str):
        self._filter = filter

    def defaultfilter(self) -> str:
        return self._defaultfilter

    def setDefaultFilter(self, defaultfilter: str):
        self._defaultfilter = defaultfilter

    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget(parent)
        layout = QtWidgets.QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        lineedit = QtWidgets.QLineEdit(w)
        layout.addWidget(lineedit, 1)
        toolbutton = QtWidgets.QToolButton(w)
        layout.addWidget(toolbutton, 0)
        toolbutton.setText('Browse')
        toolbutton.setIcon(QtGui.QIcon.fromTheme('document-open'))
        toolbutton.clicked.connect(self.onToolButtonClicked)
        return w

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                             index: QtCore.QModelIndex) -> None:
        editor.setGeometry(option.rect)

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex) -> None:
        lineedit = editor.layout().itemAt(0).widget()
        toolbutton = editor.layout().itemAt(1).widget()
        assert isinstance(lineedit, QtWidgets.QLineEdit)
        assert isinstance(toolbutton, QtWidgets.QToolButton)
        lineedit.setText(index.data(QtCore.Qt.EditRole))

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        lineedit = editor.layout().itemAt(0).widget()
        toolbutton = editor.layout().itemAt(1).widget()
        assert isinstance(lineedit, QtWidgets.QLineEdit)
        assert isinstance(toolbutton, QtWidgets.QToolButton)
        model.setData(index, lineedit.text(), QtCore.Qt.EditRole)

    def onToolButtonClicked(self):
        assert isinstance(self.sender(), QtWidgets.QToolButton)
        widget = self.sender().parent()
        assert isinstance(widget, QtWidgets.QWidget)
        lineedit = widget.layout().itemAt(0).widget()
        toolbutton = widget.layout().itemAt(1).widget()
        assert isinstance(lineedit, QtWidgets.QLineEdit)
        assert isinstance(toolbutton, QtWidgets.QToolButton)
        assert toolbutton is self.sender()
        if self.mode() is self.Mode.OpenFile:
            filename = getOpenFile(widget, self.caption(), lineedit.text(), self.filter())
        elif self.mode() is self.Mode.SaveFile:
            filename = getSaveFile(widget, self.caption(), lineedit.text(), self.filter())
        else:
            assert self.mode() is self.Mode.ExistingDirectory
            filename = getDirectory(widget, self.caption(), lineedit.text())
        if not filename:
            return
        else:
            lineedit.setText(filename)
            self.commitData.emit(widget)
            self.closeEditor.emit(widget, QtWidgets.QAbstractItemDelegate.SubmitModelCache)

