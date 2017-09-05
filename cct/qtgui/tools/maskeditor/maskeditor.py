import numpy as np
from PyQt5 import QtWidgets, QtCore
from matplotlib.path import Path
from matplotlib.widgets import Cursor, EllipseSelector, RectangleSelector, LassoSelector
from sastool.classes2.exposure import Exposure
from scipy.io import savemat, loadmat

from .maskeditor_ui import Ui_MainWindow
from ...core.fsnselector import FSNSelector
from ...core.mixins import ToolWindow
from ...core.plotimage import PlotImage


class MaskEditor(QtWidgets.QMainWindow, Ui_MainWindow, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)
        self.undoStack = []
        self.undoStackPointer = 0
        self.lastFileName = None

    def setupUi(self, Form):
        Ui_MainWindow.setupUi(self, Form)
        self.operationsGroup = QtWidgets.QActionGroup(self.toolBar)
        # self.operationsGroup.triggered.connect(self.setOperation)
        for action in [self.actionMask, self.actionUnmask, self.actionFlip_mask]:
            self.operationsGroup.addAction(action)
        for action in [self.actionUndo, self.actionRedo, self.actionSave_mask]:
            action.setEnabled(False)
        self.actionMask.setChecked(True)
        self.plotimage = PlotImage(register_instance=False)
        self.plotimage.axesComboBox.setCurrentIndex(self.plotimage.axesComboBox.findText('abs. pixel'))
        while self.plotimage.axesComboBox.count() > 1:
            for i in range(self.plotimage.axesComboBox.count()):
                # try to remove an item, which is not 'abs. pixel'
                if self.plotimage.axesComboBox.itemText(i) != 'abs. pixel':
                    self.plotimage.axesComboBox.removeItem(i)
                    break
        self.plotimage.axesComboBox.setCurrentIndex(0)
        w = QtWidgets.QWidget(self)
        self.setCentralWidget(w)

        self.addToolBar(QtCore.Qt.BottomToolBarArea, self.plotimage.figtoolbar)
        w.setObjectName('plotimageCanvas')
        l = QtWidgets.QVBoxLayout(w)
        w.setLayout(l)
        l.setContentsMargins(0, 0, 0, 0)
        self.fsnSelector = FSNSelector(w, credo=self.credo, horizontal=True)
        l.addWidget(self.fsnSelector)
        l.addWidget(self.plotimage.canvas)
        self.fsnSelector.FSNSelected.connect(self.onFSNSelected)
        self.actionLasso_selector.toggled.connect(self.selectPolygon)
        self.actionPixel_hunt.toggled.connect(self.pixelHunt)
        self.actionSelect_a_circle.toggled.connect(self.selectCircle)
        self.actionSelect_rectangle.toggled.connect(self.selectRectangle)
        self.actionSave_mask.triggered.connect(self.saveMask)
        self.actionSave_mask_as.triggered.connect(self.saveAsMask)
        self.actionOpen_mask.triggered.connect(self.loadMask)
        self.actionNew_mask.triggered.connect(self.createNewMask)
        self.actionUndo.triggered.connect(self.undo)
        self.actionRedo.triggered.connect(self.redo)

    def cleanup(self):
        self.fsnSelector.close()
        super().cleanup()

    def onFSNSelected(self, prefix:str, fsn:int, exposure:Exposure):
        self.setExposure(exposure)
        del exposure

    def setExposure(self, exposure: Exposure):
        self.undoStack = [exposure.mask]
        self.undoStackPointer = 0
        return self.plotimage.setExposure(exposure)

    def exposure(self) -> Exposure:
        return self.plotimage.exposure()

    def createNewMask(self):
        self.updateMask(np.ones_like(self.exposure().mask))

    def loadMask(self):
        filename, filter = QtWidgets.QFileDialog.getOpenFileName(self, "Load mask from...", filter='*.mat')
        if not filename: return
        mat = loadmat(filename)
        matkey = [m for m in mat.keys() if not (m.startswith('_') or m.endswith('_'))][0]
        self.updateMask(mat[matkey])

    def saveMask(self):
        if self.lastFileName is None:
            self.saveAsMask()
        else:
            savemat(self.lastFileName, {'mask': self.exposure().mask}, appendmat=False, do_compression=True)

    def saveAsMask(self):
        filename, filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save mask to...", filter="*.mat"
        )
        if filename is None:
            return
        self.lastFileName = filename
        self.saveMask()

    def undo(self):
        self.undoStackPointer = max(0, self.undoStackPointer - 1)
        self.actionUndo.setEnabled(self.undoStackPointer > 0)
        self.actionRedo.setEnabled(self.undoStackPointer < len(self.undoStack) - 1)
        self.plotimage.exposure().mask = self.undoStack[self.undoStackPointer]
        self.plotimage.replot_mask()
        self.plotimage.canvas.draw()

    def redo(self):
        self.undoStackPointer = min(len(self.undoStack) - 1, self.undoStackPointer + 1)
        self.actionUndo.setEnabled(self.undoStackPointer > 0)
        self.actionUndo.setEnabled(self.undoStackPointer < len(self.undoStack) - 1)
        self.plotimage.exposure().mask = self.undoStack[self.undoStackPointer]
        self.plotimage.replot_mask()
        self.plotimage.canvas.draw()

    def pixelHunt(self):
        if self.actionPixel_hunt.isChecked():
            # start pixel hunt mode.
            self.crossHair = Cursor(self.plotimage.axes, useblit=False, color='white', lw=1)
            self.crossHair.connect_event('button_press_event', self.cursorClicked)
            while self.plotimage.figtoolbar.mode != '':
                self.plotimage.figtoolbar.zoom()
            for action in self.actions():
                action.setEnabled(False)
            self.actionPixel_hunt.setEnabled(True)
        elif hasattr(self, 'crossHair'):
            self.crossHair.disconnect_events()
            del self.crossHair
            self.plotimage.replot()
            for action in self.actions():
                action.setEnabled(True)

    def cursorClicked(self, event):
        if (event.inaxes == self.plotimage.axes) and (self.plotimage.figtoolbar.mode == ''):
            mask = self.exposure().mask.copy()
            mask[round(event.ydata), round(event.xdata)] ^= True
            self.updateMask(mask)
            self.crossHair.disconnect_events()
            del self.crossHair
            self.plotimage.replot_mask()
            self.plotimage.canvas.draw()
            self.pixelHunt()

    def operation(self):
        return self.operationsGroup.checkedAction().iconText()

    def initializeSelector(self, action:QtWidgets.QAction, selectorclass, callbackfunction, **kwargs):
        if action.isChecked():
            while self.plotimage.figtoolbar.mode != '':
                # turn off zoom, pan, etc. modes in the matplotlib figure toolbar
                self.plotimage.figtoolbar.zoom()
            if selectorclass in [RectangleSelector, EllipseSelector]:
                kwargs['rectprops'] = {'facecolor': 'white', 'edgecolor': 'none',
                                       'alpha': 0.7, 'fill': True, 'zorder': 10}
                kwargs['interactive'] = False
            self.selector = selectorclass(self.plotimage.axes,
                                          callbackfunction,
                                          button=[1, ],
                                          lineprops={'zorder': 10, 'color': 'white'},
                                          **kwargs)
            for act in self.actions():
                act.setEnabled(False)
            action.setEnabled(True)
        else:
            self.finalizeSelector()

    def finalizeSelector(self):
        if hasattr(self, 'selector'):
            self.selector.set_active(False)
            self.selector.set_visible(False)
            del self.selector
            # self.plotimage.replot()
        for action in [self.actionSelect_a_circle, self.actionSelect_rectangle, self.actionLasso_selector]:
            action.setChecked(False)
        for action in self.actions():
            action.setEnabled(True)

    def selectCircle(self):
        self.initializeSelector(self.actionSelect_a_circle, EllipseSelector, self.selectedCircle)
        if hasattr(self, 'selector'):
            self.selector.state.add('square')
            self.selector.state.add('center')

    def selectRectangle(self):
        self.initializeSelector(self.actionSelect_rectangle, RectangleSelector, self.selectedRectangle)

    def selectPolygon(self):
        self.initializeSelector(self.actionLasso_selector, LassoSelector, self.selectedPolygon)

    def selectedCircle(self, pos1, pos2):
        # pos1 and pos2 are mouse button press and release events, with xdata and ydata carrying
        # the two opposite corners of the bounding box of the circle. These are NOT the exact
        # button presses and releases!
        mask = self.exposure().mask.copy()
        row = np.arange(mask.shape[0])[:, np.newaxis]
        column = np.arange(mask.shape[1])[np.newaxis, :]
        row0 = 0.5 * (pos1.ydata + pos2.ydata)
        col0 = 0.5 * (pos1.xdata + pos2.xdata)
        r2 = ((pos2.xdata - pos1.xdata) ** 2 + (pos2.ydata - pos1.ydata) ** 2) / 8
        tobemasked = (row - row0) ** 2 + (column - col0) ** 2 <= r2
        if self.operation() == 'Mask':
            mask &= ~tobemasked
        elif self.operation() == 'Unmask':
            mask |= tobemasked
        elif self.operation() == 'Flip mask':
            mask[tobemasked] = ~mask[tobemasked]
        else:
            return
        self.updateMask(mask)
        self.finalizeSelector()

    def selectedRectangle(self, pos1, pos2):
        # pos1 and pos2 are mouse button press and release events, with xdata and ydata
        # carrying the two opposite corners of the bounding box of the rectangle. These
        # are NOT the exact button presses and releases!
        mask = self.exposure().mask.copy()
        row = np.arange(mask.shape[0])[:, np.newaxis]
        column = np.arange(mask.shape[1])[np.newaxis, :]
        tobemasked = ((row >= min(pos1.ydata, pos2.ydata)) & (row <= max(pos1.ydata, pos2.ydata)) &
                      (column >= min(pos1.xdata, pos2.xdata)) & (column <= max(pos1.xdata, pos2.xdata)))
        if self.operation() == 'Mask':
            mask = mask & (~tobemasked)
        elif self.operation() == 'Unmask':
            mask = mask | tobemasked
        elif self.operation() == 'Flip mask':
            mask[tobemasked] = ~mask[tobemasked]
        else:
            return
        self.updateMask(mask)
        self.finalizeSelector()

    def selectedPolygon(self, vertices):
        path = Path(vertices)
        mask = self.exposure().mask.copy()
        col, row = np.meshgrid(np.arange(mask.shape[1]),
                               np.arange(mask.shape[0]))
        points = np.vstack((col.flatten(), row.flatten())).T
        tobemasked = path.contains_points(points).reshape(mask.shape)
        if self.operation() == 'Mask':
            mask = mask & (~tobemasked)
        elif self.operation() == 'Unmask':
            mask = mask | tobemasked
        elif self.operation() == 'Flip mask':
            mask[tobemasked] = ~mask[tobemasked]
        else:
            return
        self.updateMask(mask)
        self.finalizeSelector()

    def updateMask(self, mask):
        if mask.shape != self.exposure().shape:
            QtWidgets.QMessageBox.critical(
                self, 'Invalid mask size',
                'This mask ({0[0]:d}x{0[0]:d}) is incompatible with the exposure ({1[0]:d}x{1[0]:d})'.format(
                    mask.shape, self.exposure().shape
                ), QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Ok)
            return
        self.undoStack = self.undoStack[:self.undoStackPointer + 1]
        self.undoStack.append(mask)
        self.undoStackPointer += 1
        self.exposure().mask = mask
        self.plotimage.replot_mask()
        self.plotimage.canvas.draw()
        self.actionRedo.setEnabled(False)
        self.actionUndo.setEnabled(True)
        self.actionSave_mask.setEnabled(True)
