from typing import Dict

from PyQt5 import QtWidgets, QtGui

from .exportsettings import ExportSettings
from .plotdefaults import PlotSettings
from .processingsettings import ProcessingSettings
from .settingsmain_ui import Ui_Form
from .settingspage import SettingsPage
from ..config import Config


class SettingsWindow(QtWidgets.QWidget, Ui_Form):
    pages: Dict[str, SettingsPage]

    def __init__(self, parent: QtWidgets.QWidget, config:Config):
        super().__init__(parent)
        self.config=config
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.pages = {
            'Export': ExportSettings(self),
            'Plotting': PlotSettings(self),
            'Processing': ProcessingSettings(self),
        }
        self.listWidget.addItems(sorted(self.pages))
        for p in self.pages.values():
            self.stackedWidget.addWidget(p)
            p.changed.connect(self.onSettingsPageChanged)
            p.fromConfig(self.config)
        self.listWidget.setCurrentRow(0)

    def on_listWidget_currentTextChanged(self, currentText:str):
        self.stackedWidget.setCurrentWidget(self.pages[currentText])

    def onSettingsPageChanged(self, changed:bool):
        self.buttonBox.button(self.buttonBox.Apply).setEnabled(
            any([p.hasChanges() for p in self.pages.values()])
        )

    def on_buttonBox_clicked(self, button):
        if self.buttonBox.standardButton(button) in [self.buttonBox.Apply, self.buttonBox.Ok]:
            for p in self.pages.values():
                p.toConfig(self.config)
        if self.buttonBox.standardButton(button) in [self.buttonBox.Ok, self.buttonBox.Cancel]:
            # try to close. The close method will warn us for unapplied changes
            self.close()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if any([p.hasChanges() for p in self.pages.values()]):
            result = QtWidgets.QMessageBox.warning(self, 'Cancel changes', 'You have made changes to the configuration. Save them?', QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel)
            if result == QtWidgets.QMessageBox.Yes:
                for p in self.pages.values():
                    p.toConfig(self.config)
                event.accept()
            elif result == QtWidgets.QMessageBox.No:
                event.accept()
            elif result == QtWidgets.QMessageBox.Cancel:
                event.ignore()
        self.parent().close()
