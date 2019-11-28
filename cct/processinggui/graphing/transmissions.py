import logging
from typing import Tuple, Union, List

from PyQt5 import QtWidgets
from sastool.misc.errorvalue import ErrorValue

from .transmissions_ui import Ui_Form
from ..models.modeltoxlsx import model2xlsx
from ..models.transmissions import TransmissionModel

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class TransmissionList(QtWidgets.QWidget, Ui_Form):
    _samplesanddists = List[Tuple[str, Union[float, str]]]

    def __init__(self, parent: QtWidgets.QWidget = None, project: "Project" = None):
        super().__init__(parent)
        self._samplesanddists = []
        if project is None:
            raise ValueError('TransmissionList needs a project')
        self.project = project
        self.project.newResultsAvailable.connect(self.updateList)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.model = TransmissionModel()
        self.treeView.setModel(self.model)
        self.model.modelReset.connect(self.resizeTreeViewColumns)
        self.model.rowsInserted.connect(self.resizeTreeViewColumns)
        self.model.rowsRemoved.connect(self.resizeTreeViewColumns)
        self.exportTablePushButton.clicked.connect(self.exportTable)
        self.setWindowTitle('Transmissions')
        self.updateList()

    def resizeTreeViewColumns(self):
        for c in range(self.model.columnCount()):
            self.treeView.resizeColumnToContents(c)

    def updateList(self):
        self.model.clear()
        for samplename, distance in self._samplesanddists:
            try:
                transm = self.project.h5reader.getCurveParameter(samplename, distance, 'transmission')
                transmerr = self.project.h5reader.getCurveParameter(samplename, distance, 'transmission.err')
                thickness = self.project.h5reader.getCurveParameter(samplename, distance, 'thickness')
                thicknesserr = self.project.h5reader.getCurveParameter(samplename, distance, 'thickness.err')
            except KeyError:
                continue
            fsns = sorted(transm)
            transm = [transm[f] for f in fsns]
            transmerr = [transmerr[f] for f in fsns]
            thickness = [thickness[f] for f in fsns]
            thicknesserr = [thicknesserr[f] for f in fsns]
            # get the unique results
            for tm, tme, th, the in set(zip(transm, transmerr, thickness, thicknesserr)):
                self.model.add(samplename, float(distance), ErrorValue(tm, tme), ErrorValue(th, the))

    def exportTable(self):
        filename, filter_ = QtWidgets.QFileDialog.getSaveFileName(self, 'Write table...', '',
                                                                  'Excel 2007- (*.xlsx);;All files (*)',
                                                                  'Excel 2007- (*.xlsx)')
        if not filename:
            return
        model2xlsx(filename, 'Transmissions', self.model)

    def addSampleAndDist(self, samplename: str, dist: Union[str, float], updatelist:bool=True):
        self._samplesanddists.append((samplename, float(dist)))
        if updatelist:
            self.updateList()
