import os

import numpy as np
import scipy.io
from PyQt5 import QtWidgets, QtCore
from matplotlib.backend_bases import MouseEvent
from matplotlib.patches import Circle
from matplotlib.path import Path
from matplotlib.widgets import Cursor, EllipseSelector, RectangleSelector, LassoSelector, PolygonSelector, SpanSelector
from sastool.classes2.exposure import Exposure

from .maskeditor_ui import Ui_MainWindow
from .stack import Stack
from ...core.fsnselector import FSNSelector
from ...core.h5selector import H5Selector
from ...core.mixins import ToolWindow
from ...core.plotcurve import PlotCurve
from ...core.plotimage import PlotImage


class MaskEditor(QtWidgets.QMainWindow, Ui_MainWindow, ToolWindow):
    def __init__(self, *args, **kwargs):
        try:
            credo = kwargs.pop('credo')
        except KeyError:
            credo = None
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.undoStack = Stack(self)
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.setWindowTitle('Mask Editor [*]')
        self.plotimage = PlotImage(self, False)
        self.plotimage.setPixelMode(True)
        self.plotcurve = PlotCurve(self)
        #self.centralwidget.setLayout(QtWidgets.QVBoxLayout(self))
        if self.credo is not None:
            self.fsnSelector = FSNSelector(self, credo=self.credo, horizontal=True)
            self.centralwidget.layout().addWidget(self.fsnSelector)
            self.fsnSelector.FSNSelected.connect(self.onFSNSelected)
        self.h5Selector = H5Selector(self, horizontal=True)
        self.centralwidget.layout().addWidget(self.h5Selector)
        self.h5Selector.H5Selected.connect(self.onH5Selected)
        self.hsplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self.centralwidget)
        self.centralwidget.layout().addWidget(self.hsplitter)
        self.hsplitter.setChildrenCollapsible(False)
        self.hsplitter.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.hsplitter.addWidget(self.plotimage)
        self.hsplitter.addWidget(self.plotcurve)
        ag = QtWidgets.QActionGroup(self.toolBar)
        for ac in [self.actionMasking, self.actionUnmasking, self.actionFlipping]:
            ag.addAction(ac)
        self.actionNew_mask.triggered.connect(self.onNewMask)
        self.actionLoad_mask.triggered.connect(self.onLoadMask)
        self.actionSave_mask.triggered.connect(self.onSaveMask)
        self.actionSave_mask_as.triggered.connect(self.onSaveMaskAs)
        self.actionUndo.triggered.connect(self.onUndo)
        self.actionRedo.triggered.connect(self.onRedo)
        #self.actionMasking
        #self.actionUnmasking
        #self.actionFlipping
        self.actionPixel_hunting.triggered.connect(self.onPixelHunt)
        self.actionSelect_a_circle.triggered.connect(self.onSelectCircle)
        self.actionSelect_a_polygon.triggered.connect(self.onSelectPolygon)
        self.actionSelect_free_hand.triggered.connect(self.onSelectFreeHand)
        self.actionSelect_rectangle.triggered.connect(self.onSelectRectangle)
        self.actionQ_range_cursor.triggered.connect(self.onQRangeCursor)
        self.undoStack.pointerChanged.connect(self.onUndoStackPointerChanged)
        self.undoStack.stackChanged.connect(self.onUndoStackChanged)
        self._plotimage_connection = [self.plotimage.canvas.mpl_connect('button_press_event', self.on2DCanvasButtonPress)]
        self.onUndoStackPointerChanged() # update the enabled state of the undo buttons
        self.spanSelector = None
        self.helpLabel.setVisible(False)
        self._circles = []
        self._pixelhuntcursor = None
        self.setExposure(self.exposure())

    def cleanup(self):
        for c in self._plotimage_connection:
            self.plotimage.canvas.mpl_disconnect(c)
        self._plotimage_connection=[]
        self.fsnSelector.close()
        self.h5Selector.close()
        return super().cleanup()

    def deleteLater(self):
        self.cleanup()
        return super().deleteLater()

    def on2DCanvasButtonPress(self, event:MouseEvent) -> bool:
        if (self._pixelhuntcursor is not None) and (not self.plotimage.figtoolbar.mode):
            if not event.inaxes == self.plotimage.axes:
                return False
            mask = self.maskMatrix.copy()
            column = int(round(event.xdata))
            row = int(round(event.ydata))
            mask[row, column] = 1-mask[row, column]
            self.updateMask(mask)
        return False

    def onH5Selected(self, filename:str, sample:str, dist:float, exposure:Exposure):
        self.setExposure(exposure)

    def onFSNSelected(self, fsn:int, prefix:str, exposure:Exposure):
        self.setExposure(exposure)
        # ToDo: what to do with the just loaded mask? Size mismatch?

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
            self.undoStack.reset()
            self.updateMask(np.zeros(self.plotimage.exposure().shape, np.bool))
            self.setWindowFilePath('')

    def onLoadMask(self):
        if not self.confirmChanges():
            return
        filename, filter = QtWidgets.QFileDialog.getOpenFileName(self, 'Load a mask file...', self.windowFilePath(), 'Mask files (*.mat);;All files (*)', 'Mask files (*.mat)')
        if filename is None:
            return
        mat=scipy.io.loadmat(filename)
        maskkey = [k for k in mat.keys() if not k.startswith('_')][0]
        self.undoStack.reset()
        self.updateMask(mat[maskkey])
        self.setWindowFilePath(filename)

    def onSaveMask(self):
        if not self.windowFilePath():
            return self.onSaveMaskAs()
        filename = self.windowFilePath()
        maskname = os.path.splitext(os.path.split(filename)[1])[0]
        scipy.io.savemat(filename, {maskname:self.maskMatrix}, appendmat = True)
        self.setWindowModified(False)

    def onSaveMaskAs(self):
        filename, filter = QtWidgets.QFileDialog.getSaveFileName(self, 'Save the mask...', self.windowFilePath(), 'Mask files (*.mat);;All files (*)', 'Mask files (*.mat)')
        if not filename:
            return
        self.setWindowFilePath(filename)
        self.onSaveMask()

    def onUndo(self):
        self.undoStack.back()
        self.maskMatrix = self.undoStack.get()

    def onRedo(self):
        self.undoStack.forward()
        self.maskMatrix = self.undoStack.get()

    def onPixelHunt(self, checked:bool):
        if checked:
            self._pixelhuntcursor = Cursor(self.plotimage.axes, color='white', lw=1, linestyle='-', zorder=100)
            self._pixelhuntcursor.set_active(True)
            for act in self.toolBar.actions():
                act.setEnabled(False)
            self.actionPixel_hunting.setEnabled(True)
        else:
            self._pixelhuntcursor.set_active(False)
            del self._pixelhuntcursor
            self._pixelhuntcursor = None
            for act in self.toolBar.actions():
                act.setEnabled(True)
            self.onUndoStackPointerChanged()

    def initializeSelector(self, action: QtWidgets.QAction, selectorclass, callbackfunction, helptext, **kwargs):
        if action.isChecked():
            while self.plotimage.figtoolbar.mode != '':
                # turn off zoom, pan, etc. modes in the matplotlib figure toolbar
                self.plotimage.figtoolbar.zoom()
            if selectorclass in [RectangleSelector, EllipseSelector]:
                kwargs['rectprops'] = {'facecolor': 'white', 'edgecolor': 'none',
                                       'alpha': 0.7, 'fill': True, 'zorder': 10}
                kwargs['interactive'] = False
            if selectorclass!=PolygonSelector:
                kwargs['button'] = [1,]
            self.selector = selectorclass(self.plotimage.axes,
                                          callbackfunction,
                                          lineprops={'zorder': 10, 'color': 'white'},
                                          **kwargs)
            for act in self.toolBar.actions():
                act.setEnabled(False)
            action.setEnabled(True)
            self.helpLabel.setText(helptext)
            self.helpLabel.setVisible(True)
        else:
            self.finalizeSelector()

    def finalizeSelector(self):
        if hasattr(self, 'selector'):
            self.selector.set_active(False)
            self.selector.set_visible(False)
            del self.selector
            self.plotimage.canvas.draw()
        for action in self.toolBar.actions():
            action.setEnabled(True)
        self.onUndoStackPointerChanged() # update the enabled state of the undo buttons
        for action in [self.actionSelect_a_circle, self.actionSelect_rectangle, self.actionSelect_free_hand, self.actionSelect_a_polygon]:
            action.setChecked(False)
        self.helpLabel.setVisible(False)

    def onSelectCircle(self):
        self.initializeSelector(
            self.actionSelect_a_circle, EllipseSelector, self.selectedCircle,
            '<p>Draw a circle  opposite corners of a rectangle by dragging the mouse.<br>'
            'If you want to cancel selecting, click the rectangle selector button above (<img src=":/icons/selectrectangle.svg" width="24" height="24">) once again.</p>'
                                )
        if hasattr(self, 'selector'):
            self.selector.state.add('square')
            self.selector.state.add('center')

    def onSelectRectangle(self):
        self.initializeSelector(
            self.actionSelect_rectangle, RectangleSelector, self.selectedRectangle,
            '<p>Select the two opposite corners of a rectangle by dragging the mouse.<br>'
            'If you want to cancel selecting, click the rectangle selector button above (<img src=":/icons/selectrectangle.svg" width="24" height="24">) once again.</p>')

    def onSelectFreeHand(self):
        self.initializeSelector(
            self.actionSelect_free_hand, LassoSelector, self.selectedFreeHand,
            '<p>Draw a free-hand line with the pointer while keeping the left button pressed.<br>'
            'If you want to cancel selecting, click the lasso selector button above (<img src=":/icons/selectlasso.svg" width="24" height="24">) once again.</p>')

    def onSelectPolygon(self):
        self.initializeSelector(
            self.actionSelect_a_polygon, PolygonSelector, self.selectedFreeHand,
            '<p>Select the vertices of the polygon with clicking the left button of the mouse.<br>'
            'In order to finish the polygon, select the first vertex.<br>'
            'If you want to cancel selecting, click the polygon selector button above (<img src=":/icons/selectpolygon.svg" width="24" height="24">) once again.</p>'
        )

    def selectedCircle(self, pos1, pos2):
        # pos1 and pos2 are mouse button press and release events, with xdata and ydata carrying
        # the two opposite corners of the bounding box of the circle. These are NOT the exact
        # button presses and releases!
        mask = self.maskMatrix.copy()
        row = np.arange(mask.shape[0])[:, np.newaxis]
        column = np.arange(mask.shape[1])[np.newaxis, :]
        row0 = 0.5 * (pos1.ydata + pos2.ydata)
        col0 = 0.5 * (pos1.xdata + pos2.xdata)
        r2 = ((pos2.xdata - pos1.xdata) ** 2 + (pos2.ydata - pos1.ydata) ** 2) / 8
        tobemasked = (row - row0) ** 2 + (column - col0) ** 2 <= r2
        if self.actionMasking.isChecked():
            mask = mask & (~tobemasked)
        elif self.actionUnmasking.isChecked():
            mask = mask | tobemasked
        elif self.actionFlipping.isChecked():
            mask[tobemasked] = ~mask[tobemasked]
        else:
            return
        self.updateMask(mask)
        self.finalizeSelector()

    def selectedRectangle(self, pos1, pos2):
        # pos1 and pos2 are mouse button press and release events, with xdata and ydata
        # carrying the two opposite corners of the bounding box of the rectangle. These
        # are NOT the exact button presses and releases!
        mask = self.maskMatrix.copy()
        row = np.arange(mask.shape[0])[:, np.newaxis]
        column = np.arange(mask.shape[1])[np.newaxis, :]
        tobemasked = ((row >= min(pos1.ydata, pos2.ydata)) & (row <= max(pos1.ydata, pos2.ydata)) &
                      (column >= min(pos1.xdata, pos2.xdata)) & (column <= max(pos1.xdata, pos2.xdata)))
        if self.actionMasking.isChecked():
            mask = mask & (~tobemasked)
        elif self.actionUnmasking.isChecked():
            mask = mask | tobemasked
        elif self.actionFlipping.isChecked():
            mask[tobemasked] = ~mask[tobemasked]
        else:
            return
        self.updateMask(mask)
        self.finalizeSelector()

    def selectedFreeHand(self, vertices):
        path = Path(vertices)
        mask = self.maskMatrix.copy()
        col, row = np.meshgrid(np.arange(mask.shape[1]),
                               np.arange(mask.shape[0]))
        points = np.vstack((col.flatten(), row.flatten())).T
        tobemasked = path.contains_points(points).reshape(mask.shape)
        if self.actionMasking.isChecked():
            mask = mask & (~tobemasked)
        elif self.actionUnmasking.isChecked():
            mask = mask | tobemasked
        elif self.actionFlipping.isChecked():
            mask[tobemasked] = ~mask[tobemasked]
        else:
            return
        self.updateMask(mask)
        self.finalizeSelector()

    @property
    def maskMatrix(self) -> np.ndarray:
        return self.plotimage.maskMatrix()

    @maskMatrix.setter
    def maskMatrix(self, newmask:np.ndarray):
        self.plotimage.setMaskMatrix(newmask)
        self.plotcurve.clear()
        self.plotcurve.addCurve(self.exposure().radial_average(pixel=True), self.exposure().header.title, marker='.', linestyle='-')
        self.plotcurve.setXLabel('Pixel')
        self.plotcurve.setYLabel('Intensity')
        self.onQRangeCursor(self.actionQ_range_cursor.isChecked())

    def updateMask(self, mask:np.ndarray):
        self.undoStack.push(mask)
        self.maskMatrix = mask
        self.setWindowModified(True)

    def onQRangeCursor(self, checked:bool):
        if checked:
            self.spanSelector = SpanSelector(self.plotcurve.axes, self.onSpanSelected, "horizontal", span_stays=True)
            self.spanSelector.active=True
            self.plotcurve.axes.set_title('Select a range with dragging the pointer')
        else:
            try:
                self.spanSelector.span_stays = False
                self.spanSelector.active = False
                del self.spanSelector
                self.spanSelector = None
            except AttributeError:
                pass
            self.plotcurve.axes.set_title('')
        self.plotcurve.canvas.draw()

    def onSpanSelected(self, xmin, xmax):
        self.plotimage.replot()
        for c in self._circles:
            c.remove()
        self._circles=[
            Circle([self.exposure().header.beamcenterx, self.exposure().header.beamcentery], xmin, color='white', linestyle= '--', fill=False,zorder=100),
            Circle([self.exposure().header.beamcenterx, self.exposure().header.beamcentery], xmax, color='white', linestyle= '--', fill=False, zorder=100)
        ]
        for c in self._circles:
            self.plotimage.axes.add_patch(c)
        self.plotimage.canvas.draw()


    def onUndoStackChanged(self):
        # this currently does nothing
        pass

    def onUndoStackPointerChanged(self):
        self.actionUndo.setEnabled(self.undoStack.canGoBack())
        self.actionRedo.setEnabled(self.undoStack.canGoForward())
        try:
            self.maskMatrix = self.undoStack.get()
        except IndexError:
            pass

    def setExposure(self, exposure:Exposure):
        for c in self._circles:
            c.remove()
        self._circles = []
        result = self.plotimage.setExposure(exposure)
        self.undoStack.reset()
        self.updateMask(exposure.mask)
        return result

    def exposure(self) -> Exposure:
        return self.plotimage.exposure()

