from typing import List, Tuple

from PyQt5 import QtWidgets, QtCore

from ..config import Config


class SettingsPage:
    """Mix-in class for settings pages"""
    changed = QtCore.pyqtSignal(bool, name='changed')

    _changedWidgets:List[QtWidgets.QWidget]
    _trackedWidgets:List[QtWidgets.QWidget]


    def initSettingsPage(self, widgetsconfigs:List[Tuple[QtWidgets.QWidget, str]]):
        self._changedWidgets = []
        for widget, configname in widgetsconfigs:
            if isinstance(widget, QtWidgets.QComboBox):
                widget.currentIndexChanged.connect(self.onWidgetChanged)
            elif isinstance(widget, QtWidgets.QDoubleSpinBox) or isinstance(widget, QtWidgets.QSpinBox):
                widget.valueChanged.connect(self.onWidgetChanged)
            elif isinstance(widget, QtWidgets.QCheckBox):
                widget.toggled.connect(self.onWidgetChanged)
            elif isinstance(widget, QtWidgets.QLineEdit):
                widget.textChanged.connect(self.onWidgetChanged)
            else:
                raise ValueError('Invalid widget type: {}'.format(type(widget)))
        self._trackedWidgets = widgetsconfigs

    def fromConfig(self, config:Config):
        for widget, configname in self._trackedWidgets:
            if isinstance(widget, QtWidgets.QComboBox):
                idx = widget.findText(getattr(config, configname))
                if idx<0:
                    raise ValueError('Cannot find config value {} for item {} in the list for the combo box.'.format(getattr(config, configname), configname))
                widget.setCurrentIndex(idx)
            elif isinstance(widget, QtWidgets.QSpinBox) or isinstance(widget, QtWidgets.QDoubleSpinBox):
                widget.setValue(getattr(config, configname))
            elif isinstance(widget, QtWidgets.QCheckBox):
                widget.setChecked(getattr(config, configname))
            elif isinstance(widget, QtWidgets.QLineEdit):
                widget.setText(getattr(config, configname))
            else:
                raise ValueError(
                    'Unknown widget type {} associated with config item {}'.format(type(widget), configname))
        self.resetChangedWidgets()

    def toConfig(self, config:Config, onlychanged:bool=True):
        for widget, configname in self._trackedWidgets:
            if onlychanged and (widget not in self._changedWidgets):
                continue
            if isinstance(widget, QtWidgets.QComboBox):
                setattr(config, configname, widget.currentText())
            elif isinstance(widget, QtWidgets.QSpinBox) or isinstance(widget, QtWidgets.QDoubleSpinBox):
                setattr(config, configname, widget.value())
            elif isinstance(widget, QtWidgets.QCheckBox):
                setattr(config, configname, widget.isChecked())
            elif isinstance(widget, QtWidgets.QLineEdit):
                setattr(config, configname, widget.text())
            else:
                raise ValueError(
                    'Unknown widget type {} associated with config item {}'.format(type(widget), configname))
            self._changedWidgets = [w for w in self._changedWidgets if w is not widget] # remove _all_ occurrences
        self.changed.emit(bool(self._changedWidgets))

    def onWidgetChanged(self):
        self.addChangedWidget(self.sender())
        self.changed.emit(True)

    def addChangedWidget(self, widget:QtWidgets.QWidget):
        if widget not in self._changedWidgets:
            self._changedWidgets.append(widget)

    def resetChangedWidgets(self):
        self._changedWidgets=[]
        self.changed.emit(False)

    def hasChanges(self) -> bool:
        return bool(self._changedWidgets)