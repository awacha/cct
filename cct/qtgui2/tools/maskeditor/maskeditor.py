import os
from typing import Sequence, Optional, Union
import logging

import numpy as np
import scipy.io
from PyQt5 import QtWidgets
from matplotlib.backend_bases import MouseEvent
from matplotlib.path import Path
from matplotlib.widgets import Cursor, EllipseSelector, RectangleSelector, LassoSelector, PolygonSelector

from .maskeditor_ui import Ui_Form
from .stack import Stack
from ...utils.fsnselector import FSNSelector
from ...utils.h5selector import H5Selector
from ...utils.plotcurve import PlotCurve
from ...utils.plotimage import PlotImage
from ...utils.window import WindowRequiresDevices
from ....core2.dataclasses import Exposure
from .maskoperations import maskCircle, maskRectangle, maskPolygon, mm_mask, mm_flip, mm_unmask

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class MaskEditor(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    """Mask editor user interface.

    A series of masks is stored in an undo stack, the current one pointed to by the stack pointer.
    """

    undoStack: Stack
    plotimage: PlotImage
    plotcurve: PlotCurve
    fsnselector: FSNSelector
    h5selector: H5Selector
    _plotimage_connection: Sequence[int]
    _pixelhuntcursor: Cursor
    areaselector: Optional[Union[EllipseSelector, RectangleSelector, LassoSelector, PolygonSelector]] = None
    exposure: Optional[Exposure] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.undoStack = Stack(self)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.plotimage = PlotImage(self)
        self.plotimage.setPixelOnly(True)
        self.imageVerticalLayout.addWidget(self.plotimage)
        self.plotcurve = PlotCurve(self)
        self.curveVerticalLayout.addWidget(self.plotcurve)
        self.fsnSelectorHorizontalLayout.addWidget(QtWidgets.QLabel('Load single exposure:'))
        self.fsnselector = FSNSelector(self)
        self.fsnselector.fsnSelected.connect(self.onFSNSelected)
        self.fsnSelectorHorizontalLayout.addWidget(self.fsnselector)
        self.fsnSelectorHorizontalLayout.addSpacing(6)
        self.fsnSelectorHorizontalLayout.addWidget(QtWidgets.QLabel('Load averaged image:'))
        self.h5selector = H5Selector(self)
        self.h5selector.datasetSelected.connect(self.onH5DatasetSelected)
        self.fsnSelectorHorizontalLayout.addWidget(self.h5selector)
        self.fsnSelectorHorizontalLayout.addStretch(1)
        bg1 = QtWidgets.QButtonGroup(self)
        for button in [self.maskToolButton, self.unMaskToolButton, self.flipMaskToolButton]:
            bg1.addButton(button)
        bg1.setExclusive(True)
        self.newMaskToolButton.clicked.connect(self.onNewMask)
        self.loadMaskToolButton.clicked.connect(self.onLoadMask)
        self.saveMaskToolButton.clicked.connect(self.onSaveMask)
        self.saveMaskAsToolButton.clicked.connect(self.onSaveMaskAs)
        self.undoToolButton.clicked.connect(self.onUndo)
        self.redoToolButton.clicked.connect(self.onRedo)
        bg2 = QtWidgets.QButtonGroup(self)
        for selectorbutton in [self.zoomModeToolButton, self.selectRectangleToolButton, self.selectCircleToolButton,
                               self.selectLassoToolButton, self.selectPolygonToolButton, self.selectByPixelToolButton]:
            selectorbutton.toggled.connect(self.selectModeChanged)
            bg2.addButton(selectorbutton)
        bg2.setExclusive(True)

        self.undoStack.pointerChanged.connect(self.onUndoStackPointerChanged)
        self.undoStack.stackChanged.connect(self.onUndoStackChanged)
        self._plotimage_connection = [
            self.plotimage.canvas.mpl_connect('button_press_event', self.on2DCanvasButtonPress)]
        self.onUndoStackPointerChanged()  # update the enabled state of the undo buttons
        self._pixelhuntcursor = Cursor(self.plotimage.axes, color='white', lw=1, linestyle=':', zorder=100)
        self._pixelhuntcursor.set_active(False)
        self.plotcurve.setShowErrors(False)

    def on2DCanvasButtonPress(self, event: MouseEvent) -> bool:
        """Handle button presses on the canvas in pixel selection mode."""
        if self.selectByPixelToolButton.isChecked() and (not self.plotimage.figToolbar.mode):
            if not event.inaxes == self.plotimage.axes:
                return False
            mask = self.undoStack.get()
            assert isinstance(mask, np.ndarray)
            column = int(round(event.xdata))
            row = int(round(event.ydata))
            if (column >= 0) and (column < mask.shape[1]) and (row >= 0) and (row < mask.shape[0]):
                mask = mask.copy()
                mask[row, column] = (mask[row, column] == 0)
            self.undoStack.push(mask)
        return False

    def onFSNSelected(self, prefix: str, fsn: int):
        exposure = self.instrument.io.loadExposure(prefix, fsn, raw=True, check_local=True)
        self.setExposure(exposure)

    def onH5DatasetSelected(self, filename:str, samplename:str, distkey: str):
        exposure = self.h5selector.loadExposure()
        self.setExposure(exposure)

    def confirmChanges(self) -> bool:
        if self.isWindowModified():
            return QtWidgets.QMessageBox.question(
                self, 'Confirm discarding changes?',
                'You have made changes to the current mask. Do you want to discard them?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No
            ) == QtWidgets.QMessageBox.Yes
        else:
            return True

    def onNewMask(self):
        if self.confirmChanges():
            self.undoStack.push(np.ones(self.exposure.mask.shape, np.bool))
            self.setWindowModified(True)
            self.setWindowFilePath('')

    def onLoadMask(self):
        if not self.confirmChanges():
            return
        filename, filter_ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Load a mask file...', self.windowFilePath(),
            'Mask files (*.mat);;All files (*)', 'Mask files (*.mat)')
        if filename is None:
            return
        mat = scipy.io.loadmat(filename)
        maskkey = [k for k in mat.keys() if not k.startswith('_')][0]
        self.undoStack.push(mat[maskkey])
        self.setWindowModified(False)
        self.setWindowFilePath(filename)

    def onSaveMask(self):
        if not self.windowFilePath():
            return self.onSaveMaskAs()
        filename = self.windowFilePath()
        maskname = os.path.splitext(os.path.split(filename)[1])[0]
        scipy.io.savemat(filename, {maskname: self.undoStack.get()}, appendmat=True)
        self.instrument.io.invalidateMaskCache()
        self.setWindowModified(False)

    def onSaveMaskAs(self):
        filename, filter_ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save the mask...', self.windowFilePath(),
            'Mask files (*.mat);;All files (*)',
            'Mask files (*.mat)')
        if not filename:
            return
        self.setWindowFilePath(filename)
        self.onSaveMask()

    def onUndo(self):
        self.undoStack.back()

    def onRedo(self):
        self.undoStack.forward()

    def selectModeChanged(self):
        # selection mode is changed
        self._pixelhuntcursor.set_active(self.selectByPixelToolButton.isChecked())
        if not self.zoomModeToolButton.isChecked():
            # we are in some selector mode: disable zoom / pan / etc. modes of the figure toolbar.
            while self.plotimage.figToolbar.mode:
                self.plotimage.figToolbar.zoom()
        # the selecting mode changed: clean up the selector if present.
        if self.areaselector is not None:
            self.areaselector.set_active(False)
            self.areaselector.set_visible(False)
            self.areaselector = None
            self.plotimage.canvas.draw_idle()
        # now create the appropriate area selector if needed
        if self.selectRectangleToolButton.isChecked():
            self.areaselector = RectangleSelector(
                self.plotimage.axes,
                self.selectedRectangle,
                lineprops={'zorder': 10, 'color': 'white'},
                rectprops={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.7, 'fill': True, 'zorder': 10},
                interactive=False,
            )
        elif self.selectCircleToolButton.isChecked():
            self.areaselector = EllipseSelector(
                self.plotimage.axes,
                self.selectedCircle,
                lineprops={'zorder': 10, 'color': 'white'},
                rectprops={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.7, 'fill': True, 'zorder': 10},
                interactive=False,
            )
            self.areaselector.state.add('square')
            self.areaselector.state.add('center')
        elif self.selectLassoToolButton.isChecked():
            self.areaselector = LassoSelector(
                self.plotimage.axes,
                self.selectedFreeHand,
                lineprops={'zorder': 10, 'color': 'white'},
            )
        elif self.selectPolygonToolButton.isChecked():
            self.areaselector = PolygonSelector(
                self.plotimage.axes,
                self.selectedFreeHand,
                lineprops={'zorder': 10, 'color': 'white'},
            )
        elif self.zoomModeToolButton.isChecked() or self.selectByPixelToolButton.isChecked():
            # no selector needed
            pass
        else:
            assert False

    def _getMaskingMode(self) -> int:
        if self.maskToolButton.isChecked():
            return mm_mask
        elif self.unMaskToolButton.isChecked():
            return mm_unmask
        elif self.flipMaskToolButton.isChecked():
            return mm_flip
        else:
            assert False

    def selectedCircle(self, pos1, pos2):
        # pos1 and pos2 are mouse button press and release events, with xdata and ydata carrying
        # the two opposite corners of the bounding box of the circle. These are NOT the exact
        # button presses and releases!
        mask = self.undoStack.get()
        mask = mask.copy()
        row0 = 0.5 * (pos1.ydata + pos2.ydata)
        col0 = 0.5 * (pos1.xdata + pos2.xdata)
        r2 = ((pos2.xdata - pos1.xdata) ** 2 + (pos2.ydata - pos1.ydata) ** 2) / 8
        maskCircle(mask, row0, col0, r2**0.5, self._getMaskingMode())
        self.undoStack.push(mask)

    def selectedRectangle(self, pos1, pos2):
        # pos1 and pos2 are mouse button press and release events, with xdata and ydata
        # carrying the two opposite corners of the bounding box of the rectangle. These
        # are NOT the exact button presses and releases!
        mask = self.undoStack.get()
        mask = mask.copy()
        maskRectangle(mask, min(pos1.ydata, pos2.ydata), min(pos1.xdata, pos2.xdata), max(pos1.ydata, pos2.ydata), max(pos1.xdata, pos2.xdata), self._getMaskingMode())
        self.undoStack.push(mask)

    def selectedFreeHand(self, vertices):
        logger.debug(vertices)
        logger.debug(type(vertices))
        vertices.append(vertices[0])
        mask = self.undoStack.get()
        mask = mask.copy()
        maskPolygon(mask, np.array(vertices, dtype=np.double), self._getMaskingMode())
        self.undoStack.push(mask)
        self.areaselector.set_visible(False)
        self.selectModeChanged()  # create a new selector

    def onUndoStackChanged(self):
        self.undoToolButton.setEnabled(self.undoStack.canGoBack())
        self.redoToolButton.setEnabled(self.undoStack.canGoForward())

    def onUndoStackPointerChanged(self):
        self.undoToolButton.setEnabled(self.undoStack.canGoBack())
        self.redoToolButton.setEnabled(self.undoStack.canGoForward())
        try:
            mask = self.undoStack.get()
            self.exposure.mask = mask
            self.plotcurve.clear()
            self.plotcurve.addCurve(self.exposure.radial_average(), label = self.exposure.header.title)
            self.plotcurve.setPixelMode(True)
            self.plotimage.setMask(mask)
        except IndexError:
            pass
        self.setWindowModified(True)

    def setExposure(self, exposure: Exposure):
        self.exposure = exposure
        self.plotimage.setExposure(exposure)
        self.undoStack.reset()
        self.undoStack.push(exposure.mask)
        self.newMaskToolButton.setEnabled(True)
        self.loadMaskToolButton.setEnabled(True)
        self.saveMaskAsToolButton.setEnabled(True)
        self.maskToolButton.setEnabled(True)
        self.unMaskToolButton.setEnabled(True)
        self.flipMaskToolButton.setEnabled(True)
        self.selectByPixelToolButton.setEnabled(True)
        self.selectRectangleToolButton.setEnabled(True)
        self.selectPolygonToolButton.setEnabled(True)
        self.selectLassoToolButton.setEnabled(True)
        self.selectCircleToolButton.setEnabled(True)
        self.setWindowModified(False)
