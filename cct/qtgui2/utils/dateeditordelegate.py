import datetime

from PySide6 import QtWidgets, QtCore
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DateTimeEditorDelegate(QtWidgets.QStyledItemDelegate):
    """A treeview edit delegate for presenting date & time information

    The current value is taken from the EditRole. The list of choices is in UserRole.
    """
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        w = QtWidgets.QDateTimeEdit(parent)
        w.setFrame(False)
        w.setCalendarPopup(True)
        return w

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                             index: QtCore.QModelIndex) -> None:
        editor.setGeometry(option.rect)

    def setEditorData(self, editor: QtWidgets.QDateTimeEdit, index: QtCore.QModelIndex) -> None:
        assert isinstance(editor, QtWidgets.QDateTimeEdit)
        currentdatetime = index.data(QtCore.Qt.ItemDataRole.EditRole)
        if not isinstance(currentdatetime, datetime.datetime):
            raise TypeError(f'Invalid type {type(currentdatetime)}, expected {datetime.datetime}')
        editor.setDateTime(QtCore.QDateTime(
            QtCore.QDate(currentdatetime.year, currentdatetime.month, currentdatetime.day),
            QtCore.QTime(currentdatetime.hour, currentdatetime.minute, currentdatetime.second,
                         int(currentdatetime.microsecond/1000))))

    def setModelData(self, editor: QtWidgets.QDateTimeEdit, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        dt = editor.dateTime()
        model.setData(
            index,
            datetime.datetime(dt.date().year(), dt.date().month(), dt.date().day(),
                              dt.time().hour(), dt.time().minute(), dt.time().second(), dt.time().msec()*1000),
            QtCore.Qt.ItemDataRole.EditRole)


class DateEditorDelegate(QtWidgets.QStyledItemDelegate):
    """A treeview edit delegate for presenting dates

    The current value is taken from the EditRole.
    """
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        w = QtWidgets.QDateEdit(parent)
        w.setFrame(False)
        w.setCalendarPopup(True)
        return w

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                             index: QtCore.QModelIndex) -> None:
        editor.setGeometry(option.rect)

    def setEditorData(self, editor: QtWidgets.QDateEdit, index: QtCore.QModelIndex) -> None:
        assert isinstance(editor, QtWidgets.QDateEdit)
        currentdate = index.data(QtCore.Qt.ItemDataRole.EditRole)
        if not isinstance(currentdate, datetime.date):
            raise TypeError(f'Invalid type {type(currentdate)}, expected {datetime.date}')
        editor.setDate(
            QtCore.QDate(currentdate.year, currentdate.month, currentdate.day)
        )

    def setModelData(self, editor: QtWidgets.QDateEdit, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        dt = editor.date()
        model.setData(
            index,
            datetime.date(dt.year(), dt.month(), dt.date().day()),
            QtCore.Qt.ItemDataRole.EditRole)


class TimeEditorDelegate(QtWidgets.QStyledItemDelegate):
    """A treeview edit delegate for presenting times

    The current value is taken from the EditRole.
    """
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        w = QtWidgets.QTimeEdit(parent)
        w.setFrame(False)
        w.setCalendarPopup(True)
        return w

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                             index: QtCore.QModelIndex) -> None:
        editor.setGeometry(option.rect)

    def setEditorData(self, editor: QtWidgets.QTimeEdit, index: QtCore.QModelIndex) -> None:
        assert isinstance(editor, QtWidgets.QTimeEdit)
        currenttime = index.data(QtCore.Qt.ItemDataRole.EditRole)
        if not isinstance(currenttime, datetime.time):
            raise TypeError(f'Invalid type {type(currenttime)}, expected {datetime.time}')
        editor.setTime(
            QtCore.QTime(currenttime.hour, currenttime.minute, currenttime.second, int(currenttime.microsecond/1000))
        )

    def setModelData(self, editor: QtWidgets.QTimeEdit, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        t = editor.time()
        model.setData(
            index,
            datetime.time(t.hour(), t.minute(), t.second(), t.msec()*1000),
            QtCore.Qt.ItemDataRole.EditRole)
