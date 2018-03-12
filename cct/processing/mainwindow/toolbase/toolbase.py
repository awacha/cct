from matplotlib.figure import Figure
from PyQt5.QtWidgets import QTreeView, QLineEdit, QComboBox, QGroupBox, QCheckBox, QSpinBox, QDoubleSpinBox, QStatusBar, QWidget
from PyQt5.QtCore import pyqtSignal
from configparser import ConfigParser
from typing import List, Union, Dict
from .headermodel import HeaderModel
import h5py
import weakref
import logging
import time

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class ToolBase(QWidget):
    busy = pyqtSignal(bool)
    figureDrawn = pyqtSignal()
    tableShown = pyqtSignal()
    cctConfig:Dict
    figure:Figure
    treeView:QTreeView
    configWidgets:List=[]
    h5FileName:str=None
    headerModel:HeaderModel=None
    headersTreeView:QTreeView=None
    statusBar:QStatusBar=None
    exportFolder:str=''

    siblings = {}

    def __init__(self, parent, name):
        super().__init__(parent)
        type(self).siblings[name] = weakref.proxy(self)
        self.setupUi(self)

    def setFigure(self, figure:Figure):
        self.figure = figure

    def setTreeView(self, treeview:QTreeView):
        self.treeView = treeview

    def setH5FileName(self, h5filename:str):
        self.h5FileName = h5filename

    def setHeaderModel(self, headermodel:HeaderModel):
        self.headerModel=headermodel

    def setHeadersTreeView(self, headerstreeview:QTreeView):
        self.headersTreeView=headerstreeview

    def setStatusBar(self, statusbar:QStatusBar):
        self.statusBar=statusbar

    def setExportFolder(self, exportfolder:str):
        self.exportFolder=exportfolder

    def setCCTConfig(self, cctconfig:Dict):
        self.cctConfig = cctconfig

    def clearFigure(self):
        self.figure.clear()


    def save_state(self, config:ConfigParser):
        for widget, section, item in self.configWidgets:
            if section not in config:
                config[section] = {}
            if isinstance(widget, QLineEdit):
                config[section][item] = widget.text()
            elif isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                config[section][item] = str(widget.value())
            elif isinstance(widget, (QCheckBox, QGroupBox)):
                config[section][item] = str(widget.isChecked())
            elif isinstance(widget, (QComboBox,)):
                config[section][item] = widget.currentText()
            else:
                raise ValueError(
                    'Unknown widget type for config section {} item {}: {}'.format(section, item, type(widget)))

    def load_state(self, config:ConfigParser):
        for widget, section, key in self.configWidgets:
            try:
                value = config[section][key]
            except KeyError:
                continue
            if isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QComboBox):
                idx = widget.findText(config[section][key])
                if idx < 0:
                    continue
                widget.setCurrentIndex(idx)
            elif isinstance(widget, QGroupBox):
                widget.setChecked(config[section][key].lower() == 'true')
            elif isinstance(widget, QCheckBox):
                widget.setChecked(config[section][key].lower() == 'true')
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            else:
                raise ValueError('Unknown widget type for section {} key {}: {}'.format(section, key, type(widget)))
        return True

    def h5GetSamples(self) -> List[str]:
        with h5py.File(self.h5FileName, 'r') as f:
            samples = list(f['Samples'].keys())
        return list(sorted(samples))

    def h5GetDistances(self, samplename:str) -> List[str]:
        with h5py.File(self.h5FileName, 'r') as f:
            dists = list(f['Samples'][samplename].keys())
        return list(sorted(dists))

    def getHDF5Group(self, sample:str, distance:Union[str, float]):
#        logger.debug('getHDF5Group')
        class workerclass:
            def __init__(self, h5file=self.h5FileName, sample=sample, distance=distance):
                if isinstance(distance, float):
                    distance = '{:.2f}'.format(distance)
                self.sample = sample
                self.distance = distance
                self.hdf5 = None
                self.h5filename = h5file

            def __enter__(self):
#                logger.debug('getHDF5Group, __enter__ ({}, {}, {})'.format(self.h5filename, self.sample, self.distance))
                exc=None
                for i in range(10):
                    try:
                        self.hdf5 = h5py.File(self.h5filename, 'r+')
                        return self.hdf5['Samples'][self.sample][self.distance]
                    except OSError as ose:
#                        logger.debug('Trying to recover from unable locking HDF5')
                        exc=ose
                else:
                    raise exc

            def __exit__(self, exc_type, exc_val, exc_tb):
 #               logger.debug('getHDF5Group, __exit__ ({}, {}, {})'.format(self.h5filename, self.sample, self.distance))
                self.hdf5.close()
                self.hdf5 = None
        return workerclass()
