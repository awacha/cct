from PyQt5 import QtWidgets

from .geometry_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.instrument.instrument import Instrument


class GeometrySetup(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        self._updating_ui = False
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.updateUiFromConfig(self.credo)
        for sb in [self.l0DoubleSpinBox, self.l1DoubleSpinBox, self.l2DoubleSpinBox, self.lsDoubleSpinBox,
                   self.lbsDoubleSpinBox, self.sdValDoubleSpinBox, self.sdErrDoubleSpinBox, self.D1DoubleSpinBox,
                   self.D2DoubleSpinBox, self.D3DoubleSpinBox, self.DBSDoubleSpinBox, self.PixelSizeDoubleSpinBox,
                   self.wavelengthValDoubleSpinBox, self.wavelengthErrDoubleSpinBox, self.beamPosXDoubleSpinBox,
                   self.beamPosYDoubleSpinBox]:
            sb.valueChanged.connect(self.onDoubleSpinBoxChanged)
        self.maskFileNameLineEdit.textChanged.connect(self.onMaskChanged)
        self.descriptionPlainTextEdit.textChanged.connect(self.onDescriptionChanged)
        self.browseMaskPushButton.clicked.connect(self.onBrowseMask)

    def updateUiFromConfig(self, credo: Instrument):
        super().updateUiFromConfig(credo)
        self._updating_ui = True

        def updatespinbox(spinbox, value):
            if spinbox.value() != value:
                spinbox.setValue(value)

        try:
            updatespinbox(self.l0DoubleSpinBox, credo.config['geometry']['dist_source_ph1'])
            updatespinbox(self.l1DoubleSpinBox, credo.config['geometry']['dist_ph1_ph2'])
            updatespinbox(self.l2DoubleSpinBox, credo.config['geometry']['dist_ph2_ph3'])
            updatespinbox(self.lsDoubleSpinBox, credo.config['geometry']['dist_ph3_sample'])
            updatespinbox(self.lbsDoubleSpinBox, credo.config['geometry']['dist_det_beamstop'])
            updatespinbox(self.sdValDoubleSpinBox, credo.config['geometry']['dist_sample_det'])
            updatespinbox(self.sdErrDoubleSpinBox, credo.config['geometry']['dist_sample_det.err'])
            updatespinbox(self.D1DoubleSpinBox, credo.config['geometry']['pinhole_1'])
            updatespinbox(self.D2DoubleSpinBox, credo.config['geometry']['pinhole_2'])
            updatespinbox(self.D3DoubleSpinBox, credo.config['geometry']['pinhole_3'])
            updatespinbox(self.DBSDoubleSpinBox, credo.config['geometry']['beamstop'])
            updatespinbox(self.PixelSizeDoubleSpinBox, credo.config['geometry']['pixelsize'])
            updatespinbox(self.wavelengthValDoubleSpinBox, credo.config['geometry']['wavelength'])
            updatespinbox(self.wavelengthErrDoubleSpinBox, credo.config['geometry']['wavelength.err'])
            updatespinbox(self.beamPosXDoubleSpinBox, credo.config['geometry']['beamposx'])
            updatespinbox(self.beamPosYDoubleSpinBox, credo.config['geometry']['beamposy'])
            self.maskFileNameLineEdit.setText(credo.config['geometry']['mask'])
            if self.descriptionPlainTextEdit.toPlainText() != credo.config['geometry']['description']:
                self.descriptionPlainTextEdit.setPlainText(credo.config['geometry']['description'])
        finally:
            self._updating_ui = False

    def onBrowseMask(self):
        filename, filter = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open mask file...', self.credo.config['path']['mask'], '*.mat',
        )
        if filename:
            self.maskFileNameLineEdit.setText(filename)
            # this ensures the updating of the config as well.

    def onDescriptionChanged(self):
        assert isinstance(self.credo, Instrument)
        if self._updating_ui:
            return
        self.credo.config['geometry']['description'] = self.descriptionPlainTextEdit.toPlainText()
        self.credo.emit_config_change_signal()

    def onMaskChanged(self):
        assert isinstance(self.credo, Instrument)
        if self._updating_ui:
            return
        self.credo.config['geometry']['mask'] = self.maskFileNameLineEdit.text()
        self.credo.emit_config_change_signal()

    def onDoubleSpinBoxChanged(self):
        assert isinstance(self.credo, Instrument)
        if self._updating_ui:
            return
        if self.sender() == self.l0DoubleSpinBox:
            self.credo.config['geometry']['dist_source_ph1'] = self.sender().value()
        elif self.sender() == self.l1DoubleSpinBox:
            self.credo.config['geometry']['dist_ph1_ph2'] = self.sender().value()
        elif self.sender() == self.l2DoubleSpinBox:
            self.credo.config['geometry']['dist_ph2_ph3'] = self.sender().value()
        elif self.sender() == self.lsDoubleSpinBox:
            self.credo.config['geometry']['dist_ph3_sample'] = self.sender().value()
        elif self.sender() == self.lbsDoubleSpinBox:
            self.credo.config['geometry']['dist_det_beamstop'] = self.sender().value()
        elif self.sender() == self.sdValDoubleSpinBox:
            self.credo.config['geometry']['dist_sample_det'] = self.sender().value()
        elif self.sender() == self.sdErrDoubleSpinBox:
            self.credo.config['geometry']['dist_sample_det.err'] = self.sender().value()
        elif self.sender() == self.D1DoubleSpinBox:
            self.credo.config['geometry']['pinhole_1'] = self.sender().value()
        elif self.sender() == self.D2DoubleSpinBox:
            self.credo.config['geometry']['pinhole_2'] = self.sender().value()
        elif self.sender() == self.D3DoubleSpinBox:
            self.credo.config['geometry']['pinhole_3'] = self.sender().value()
        elif self.sender() == self.PixelSizeDoubleSpinBox:
            self.credo.config['geometry']['pixelsize'] = self.sender().value()
        elif self.sender() == self.wavelengthValDoubleSpinBox:
            self.credo.config['geometry']['wavelength'] = self.sender().value()
        elif self.sender() == self.wavelengthErrDoubleSpinBox:
            self.credo.config['geometry']['wavelength.err'] = self.sender().value()
        elif self.sender() == self.beamPosXDoubleSpinBox:
            self.credo.config['geometry']['beamposx'] = self.sender().value()
        elif self.sender() == self.beamPosYDoubleSpinBox:
            self.credo.config['geometry']['beamposy'] = self.sender().value()
        else:
            assert False
        self.credo.emit_config_change_signal()
