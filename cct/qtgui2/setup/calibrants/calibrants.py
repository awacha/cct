from typing import Optional

from PyQt5 import QtCore, QtWidgets

from .calibrants_ui import Ui_Form
from .peakeditor import PeakEditor
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.calibrants.calibrant import Calibrant
from ....core2.instrument.components.calibrants.intensity import IntensityCalibrant
from ....core2.instrument.components.calibrants.q import QCalibrant
from ...utils.filebrowsers import getOpenFile


class Calibrants(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    peakeditor: Optional[PeakEditor] = None

    def __init__(self, **kwargs ):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.calibrantsTreeView.setModel(self.instrument.calibrants)
        self.addCalibrantToolButton.clicked.connect(self.addCalibrant)
        self.instrument.calibrants.modelReset.connect(self.expandTreeView)
        self.removeCalibrantToolButton.clicked.connect(self.removeCalibrant)
        self.calibrantsTreeView.selectionModel().selectionChanged.connect(self.onCalibrantSelectionChanged)
        self.expandTreeView()
        self.browseDataFileToolButton.clicked.connect(self.browseForDataFile)
        self.editPeaksToolButton.clicked.connect(self.editPeaks)

    def browseForDataFile(self):
        current = self.calibrantsTreeView.selectionModel().currentIndex().internalPointer()
        if not isinstance(current, IntensityCalibrant):
            return
        filename = getOpenFile(
            self, 'Select a scattering curve file', '',
            'ASCII files (*.txt; *.dat);;All files (*)'
        )
        if not filename:
            return
        current.datafile = filename
        self.instrument.calibrants.saveToConfig()

    def editPeaks(self):
        assert self.peakeditor is None
        current = self.calibrantsTreeView.selectionModel().currentIndex().internalPointer()
        if not isinstance(current, QCalibrant):
            return
        self.peakeditor = PeakEditor(self, current.peaks)
        self.peakeditor.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.peakeditor.setWindowTitle(f'Edit peaks for calibrant {current.name}')
        self.peakeditor.finished.connect(self.onPeakEditorFinished)
        self.peakeditor.open()

    def onPeakEditorFinished(self, result):
        if result == QtWidgets.QDialog.Accepted:
            current = self.calibrantsTreeView.selectionModel().currentIndex().internalPointer()
            assert isinstance(current, QCalibrant)
            current.peaks = self.peakeditor.peaks()
            self.instrument.calibrants.saveToConfig()
        self.peakeditor.close()
        self.peakeditor.deleteLater()
        self.peakeditor = None

    def onCalibrantSelectionChanged(self):
        currentindex = self.calibrantsTreeView.selectionModel().currentIndex()
        calibrant = currentindex.internalPointer()
        self.addCalibrantToolButton.setEnabled(currentindex.isValid())
        self.removeCalibrantToolButton.setEnabled(isinstance(calibrant, Calibrant))
        self.browseDataFileToolButton.setEnabled(isinstance(calibrant, IntensityCalibrant))
        self.editPeaksToolButton.setEnabled(isinstance(calibrant, QCalibrant))

    def expandTreeView(self):
        self.calibrantsTreeView.expandAll()
        for c in range(self.instrument.calibrants.columnCount()):
            self.calibrantsTreeView.resizeColumnToContents(c)

    def addCalibrant(self):
        currentindex = self.calibrantsTreeView.selectionModel().currentIndex()
        if not currentindex.isValid():
            return
        if ((currentindex.internalPointer() is None) and (currentindex.row() == 0)) or (isinstance(currentindex.internalPointer(), QCalibrant)):
            self.instrument.calibrants.addQCalibrant()
        elif ((currentindex.internalPointer() is None) and (currentindex.row() == 1)) or (isinstance(currentindex.internalPointer(), IntensityCalibrant)):
            self.instrument.calibrants.addIntensityCalibrant()
        else:
            assert False

    def removeCalibrant(self):
        currentindex = self.calibrantsTreeView.selectionModel().currentIndex()
        if not currentindex.isValid():
            return
        if isinstance(currentindex.internalPointer(), Calibrant):
            self.instrument.calibrants.removeCalibrant(currentindex.internalPointer().name)
