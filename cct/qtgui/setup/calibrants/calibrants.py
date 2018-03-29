import logging
from ....core.utils.inhibitor import Inhibitor
from PyQt5 import QtWidgets, QtCore
from ....core.instrument.instrument import Instrument
from ...core.mixins.toolwindow import ToolWindow
from .calibrants_ui import Ui_Form
from .peakstore import PeakStore, DoubleSpinBoxDelegate

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class CalibrantsDB(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        self._updating = Inhibitor()
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.addCalibrantPushButton.clicked.connect(self.onAddCalibrant)
        self.removeCalibrantPushButton.clicked.connect(self.onRemoveCalibrant)
        self.addPeakPushButton.clicked.connect(self.onAddPeak)
        self.removePeakPushButton.clicked.connect(self.onRemovePeak)
        self.listWidget.currentItemChanged.connect(self.onCalibrantChanged)
        self.listWidget.itemChanged.connect(self.onCalibrantEdited)
        self.peakmodel = PeakStore()
        self.treeView.setModel(self.peakmodel)
        self._delegates=[DoubleSpinBoxDelegate(self.treeView), DoubleSpinBoxDelegate(self.treeView)]
        self.treeView.setItemDelegateForColumn(1, self._delegates[0])
        self.treeView.setItemDelegateForColumn(2, self._delegates[1])
        self.peakmodel.dataChanged.connect(self.onPeakDataChanged)
        self.populateList()

    def update_credo_config(self):
        with self._updating:
            self.credo.save_state()

    def onCalibrantEdited(self, item:QtWidgets.QListWidgetItem):
        logger.debug('onCalibrantEdited({})'.format(item.text()))
        if self._updating:
            return
        logger.debug('onCalibrantEdited({}) going'.format(item.text()))
        newcalibrants = {}
        for k in self.credo.config['calibrants']:
            if self.listWidget.findItems(k, QtCore.Qt.MatchExactly):
                newcalibrants[k] = self.credo.config['calibrants'][k]
        newcalibrants[item.text()]= self.peakmodel.toDict()
        self.credo.config['calibrants'] = newcalibrants
        self.update_credo_config()

    def calibrantName(self) -> str:
        return self.listWidget.currentItem().text()

    def onPeakDataChanged(self):
        logger.debug('onPeakDataChanged()')
        if self._updating:
            return
        logger.debug('onPeakDataChanged() going')
        self.credo.config['calibrants'][self.calibrantName()] = self.peakmodel.toDict()
        with self._updating:
            self.credo.save_state()

    def updateUiFromConfig(self, credo):
        logger.debug('updateUiFromConfig()')
        self.populateList()

    def cleanup(self):
        super().cleanup()

    def onAddCalibrant(self):
        i = 0
        assert isinstance(self.credo, Instrument)
        while True:
            name = 'Untitled{}'.format(i)
            if name not in self.credo.config['calibrants']:
                self.credo.config['calibrants'][name] = {}
                self.credo.save_state()
                break
            i+=1

    def onRemoveCalibrant(self):
        try:
            del self.credo.config['calibrants'][self.calibrantName()]
            self.credo.save_state()
        except AttributeError:
            pass

    def onAddPeak(self):
        i = 0
        assert isinstance(self.credo, Instrument)
        while True:
            try:
                name = 'Untitled peak {}'.format(i)
                if name not in self.credo.config['calibrants'][self.calibrantName()]:
                    self.credo.config['calibrants'][self.calibrantName()][name] = {'val':0.0,'err':0.0}
                    self.credo.save_state()
                    break
                i+=1
            except AttributeError:
                return


    def onRemovePeak(self):
        try:
            row = self.treeView.currentIndex().row()
            peakname = self.peakmodel.index(row, 0).data(QtCore.Qt.DisplayRole)
            calibrantname = self.calibrantName()
        except AttributeError:
            return
        del self.credo.config['calibrants'][calibrantname][peakname]
        self.credo.save_state()

    def onCalibrantChanged(self, current:QtWidgets.QListWidgetItem, previous:QtWidgets.QListWidgetItem):
        try:
            logger.debug('Calibrant selection changed: from {} to {}'.format(previous.text(), current.text()))
            self.populatePeakList(current.text())
        except AttributeError:
            pass

    def populateList(self):
        logger.debug('populateList')
        if self._updating:
            return
        try:
            selected=self.calibrantName()
        except AttributeError:
            selected = ''
        with self._updating:
            self.listWidget.clear()
            assert isinstance(self.credo, Instrument)
            self.listWidget.addItems(sorted(self.credo.config['calibrants']))
            for row in range(self.listWidget.count()):
                self.listWidget.item(row).setFlags(self.listWidget.item(row).flags() | QtCore.Qt.ItemIsEditable)
            try:
                self.listWidget.setCurrentItem(self.listWidget.findItems(selected, QtCore.Qt.MatchExactly)[0])
            except IndexError:
                self.listWidget.setCurrentRow(0)
        self.populatePeakList()

    def populatePeakList(self, calibrantname=None):
        logger.debug('populatePeakList({})'.format(calibrantname))
        if self._updating:
            return
        logger.debug('populatePeakList({}) going'.format(calibrantname))
        try:
            if calibrantname is None:
                calibrantname = self.calibrantName()
            with self._updating:
                self.peakmodel.fromDict(self.credo.config['calibrants'][calibrantname])
        except AttributeError:
            return


