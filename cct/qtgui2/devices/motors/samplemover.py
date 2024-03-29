# coding: utf-8
"""Motor mover widget"""

import logging
from typing import Optional

from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import pyqtSlot as Slot

from .samplemover_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.motors.motor import Motor

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SampleMover(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.movetoSampleToolButton.clicked.connect(self.moveToSample)
        self.movetoSampleXToolButton.clicked.connect(self.moveToSample)
        self.movetoSampleYToolButton.clicked.connect(self.moveToSample)
        self.sampleNameComboBox.setModel(self.instrument.samplestore.sortedmodel)

    @Slot()
    def moveToSample(self):
        if self.sampleNameComboBox.currentIndex() < 0:
            return
        for widget in [self.movetoSampleXToolButton, self.movetoSampleYToolButton, self.movetoSampleToolButton,
                       self.sampleNameComboBox]:
            widget.setEnabled(False)
        try:
            self.instrument.samplestore.movingFinished.connect(self.onMovingToSampleFinished)
            if self.sender() is self.movetoSampleXToolButton:
                self.instrument.samplestore.moveToSample(self.sampleNameComboBox.currentText(), direction='x')
            elif self.sender() is self.movetoSampleYToolButton:
                self.instrument.samplestore.moveToSample(self.sampleNameComboBox.currentText(), direction='y')
            elif self.sender() is self.movetoSampleToolButton:
                self.instrument.samplestore.moveToSample(self.sampleNameComboBox.currentText(), direction='both')
        except Exception as exc:
            for widget in [self.movetoSampleXToolButton, self.movetoSampleYToolButton, self.movetoSampleToolButton,
                           self.sampleNameComboBox]:
                widget.setEnabled(True)
            QtWidgets.QMessageBox.critical(self, 'Cannot move to sample', f'Cannot move sample in the beam: {exc}')
        else:
            logger.debug('Moving to sample started.')

    @Slot(bool, str)
    def onMovingToSampleFinished(self, success: bool, samplename: str):
        for widget in [self.movetoSampleXToolButton, self.movetoSampleYToolButton, self.movetoSampleToolButton,
                       self.sampleNameComboBox]:
            widget.setEnabled(True)
        self.instrument.samplestore.movingFinished.disconnect(self.onMovingToSampleFinished)
        logger.debug('Moving to sample finished')

