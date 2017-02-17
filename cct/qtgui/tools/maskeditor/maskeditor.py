import numpy as np
import pkg_resources
from PyQt5 import QtWidgets, QtGui
from matplotlib.path import Path
from matplotlib.widgets import Cursor, EllipseSelector, RectangleSelector, LassoSelector
from sastool.classes2.exposure import Exposure
from scipy.io import savemat, loadmat

from ...core.plotimage import PlotImage


#ToDo: define actions in Qt .ui file.


class MaskEditor(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        self.credo=kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupUi(self)
        self.undoStack = []
        self.undoStackPointer = 0
        self.lastFileName = None

    def setupUi(self, Form=None):
        layout = QtWidgets.QVBoxLayout(self)
        self.setLayout(layout)
        self.toolbar = QtWidgets.QToolBar(self)
        layout.addWidget(self.toolbar)
        self.operationsGroup = QtWidgets.QActionGroup(self.toolbar)
        # self.operationsGroup.triggered.connect(self.setOperation)
        self.actions = {
            'new': self.toolbar.addAction(QtGui.QIcon.fromTheme('document-new'), 'New', self.createNewMask),
            'open': self.toolbar.addAction(QtGui.QIcon.fromTheme('document-open'), 'Open', self.loadMask),
            'save': self.toolbar.addAction(QtGui.QIcon.fromTheme('document-save'), 'Save', self.saveMask),
            'saveas': self.toolbar.addAction(QtGui.QIcon.fromTheme('document-save-as'), 'Save as', self.saveAsMask),
            'separator1': self.toolbar.addSeparator(),
            'undo': self.toolbar.addAction(QtGui.QIcon.fromTheme('edit-undo'), 'Undo', self.undo),
            'redo': self.toolbar.addAction(QtGui.QIcon.fromTheme('edit-redo'), 'Redo', self.redo),
            'separator2': self.toolbar.addSeparator(),
            'mask': self.toolbar.addAction(QtGui.QIcon(pkg_resources.resource_filename(
                'cct', 'resource/icons/mask.svg')), 'Mask'),
            'unmask': self.toolbar.addAction(
                QtGui.QIcon(pkg_resources.resource_filename('cct', 'resource/icons/unmask.svg')),
                'Unmask'),
            'flipmask': self.toolbar.addAction(
                QtGui.QIcon(pkg_resources.resource_filename('cct', 'resource/icons/flipmask.svg')),
                'Flip mask'),
            'separator3': self.toolbar.addSeparator(),
            'selectrectangle': self.toolbar.addAction(
                QtGui.QIcon(pkg_resources.resource_filename('cct', 'resource/icons/selectrectangle.svg')),
                'Select rectangle', self.selectRectangle),
            'selectcircle': self.toolbar.addAction(
                QtGui.QIcon(pkg_resources.resource_filename('cct', 'resource/icons/selectcircle.svg')),
                'Select circle', self.selectCircle),
            'selectpolygon': self.toolbar.addAction(
                QtGui.QIcon(pkg_resources.resource_filename('cct', 'resource/icons/selectpolygon.svg')),
                'Select polygon', self.selectPolygon),
            'separator4': self.toolbar.addSeparator(),
            'pixelhunt': self.toolbar.addAction(
                QtGui.QIcon(pkg_resources.resource_filename('cct', 'resource/icons/pixelhunt.svg')),
                'Pixel hunt', self.pixelHunt),
        }
        for action in ['mask', 'unmask', 'flipmask']:
            self.actions[action].setCheckable(True)
            self.operationsGroup.addAction(self.actions[action])
        for action in ['selectcircle', 'selectrectangle', 'selectpolygon']:
            self.actions[action].setCheckable(True)
        for action in ['undo', 'redo', 'save']:
            self.actions[action].setEnabled(False)
        self.actions['pixelhunt'].setCheckable(True)
        self.actions['mask'].setChecked(True)
        self.plotimage = PlotImage(self)
        self.plotimage.axesComboBox.setCurrentIndex(self.plotimage.axesComboBox.findText('abs. pixel'))
        while self.plotimage.axesComboBox.count() > 1:
            for i in range(self.plotimage.axesComboBox.count()):
                # try to remove an item, which is not 'abs. pixel'
                if self.plotimage.axesComboBox.itemText(i) != 'abs. pixel':
                    self.plotimage.axesComboBox.removeItem(i)
                    break
        self.plotimage.axesComboBox.setCurrentIndex(0)
        layout.addWidget(self.plotimage)

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
        self.actions['undo'].setEnabled(self.undoStackPointer > 0)
        self.actions['redo'].setEnabled(self.undoStackPointer < len(self.undoStack) - 1)
        self.plotimage.exposure().mask = self.undoStack[self.undoStackPointer]
        self.plotimage.replot_mask()
        self.plotimage.canvas.draw()

    def redo(self):
        self.undoStackPointer = min(len(self.undoStack) - 1, self.undoStackPointer + 1)
        self.actions['undo'].setEnabled(self.undoStackPointer > 0)
        self.actions['redo'].setEnabled(self.undoStackPointer < len(self.undoStack) - 1)
        self.plotimage.exposure().mask = self.undoStack[self.undoStackPointer]
        self.plotimage.replot_mask()
        self.plotimage.canvas.draw()

    def pixelHunt(self):
        if self.actions['pixelhunt'].isChecked():
            # start pixel hunt mode.
            self.crossHair = Cursor(self.plotimage.axes, useblit=False, color='white', lw=1)
            self.crossHair.connect_event('button_press_event', self.cursorClicked)
            while self.plotimage.figtoolbar.mode != '':
                self.plotimage.figtoolbar.zoom()
            for name in self.actions:
                self.actions[name].setEnabled(False)
            self.actions['pixelhunt'].setEnabled(True)
        elif hasattr(self, 'crossHair'):
            self.crossHair.disconnect_events()
            del self.crossHair
            self.plotimage.replot()
            for name in self.actions:
                self.actions[name].setEnabled(True)

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

    def initializeSelector(self, actionname, selectorclass, callbackfunction, **kwargs):
        if self.actions[actionname].isChecked():
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
            for action in self.actions:
                self.actions[action].setEnabled(False)
            self.actions[actionname].setEnabled(True)
        else:
            self.finalizeSelector()

    def finalizeSelector(self):
        if hasattr(self, 'selector'):
            self.selector.set_active(False)
            self.selector.set_visible(False)
            del self.selector
            # self.plotimage.replot()
        for name in [k for k in self.actions if k.startswith('select')]:
            self.actions[name].setChecked(False)
        for name in self.actions:
            self.actions[name].setEnabled(True)


    def selectCircle(self):
        self.initializeSelector('selectcircle', EllipseSelector, self.selectedCircle)
        if hasattr(self, 'selector'):
            self.selector.state.add('square')
            self.selector.state.add('center')

    def selectRectangle(self):
        self.initializeSelector('selectrectangle', RectangleSelector, self.selectedRectangle)

    def selectPolygon(self):
        self.initializeSelector('selectpolygon', LassoSelector, self.selectedPolygon)

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
        self.undoStack = self.undoStack[:self.undoStackPointer + 1]
        self.undoStack.append(mask)
        self.undoStackPointer += 1
        self.exposure().mask = mask
        self.plotimage.replot_mask()
        self.plotimage.canvas.draw()
        self.actions['redo'].setEnabled(False)
        self.actions['undo'].setEnabled(True)
        self.actions['save'].setEnabled(True)
