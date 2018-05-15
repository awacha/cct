from configparser import ConfigParser
import logging

from PyQt5 import QtCore

from .backgroundsubtractionmodel import BackgroundSubtractionModel, ComboBoxDelegate
from .backgroundtool_ui import Ui_Form
from ..toolbase import ToolBase, HeaderModel

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class BackgroundTool(ToolBase, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.backgroundList = BackgroundSubtractionModel()
        self.backgroundListTreeView.setModel(self.backgroundList)
        self.backgroundListDelegate = ComboBoxDelegate()
        self.backgroundListTreeView.setItemDelegateForColumn(0, self.backgroundListDelegate)
        self.backgroundListTreeView.setItemDelegateForColumn(1, self.backgroundListDelegate)
        self.backgroundListAddPushButton.clicked.connect(self.onAddBackgroundListElement)
        self.backgroundListDeletePushButton.clicked.connect(self.onDeleteBackgroundListElement)
        self.backgroundListClearPushButton.clicked.connect(self.onClearBackgroundList)
        self.configWidgets = []

    def onAddBackgroundListElement(self):
        self.backgroundList.addSample(None)

    def onDeleteBackgroundListElement(self):
        while self.backgroundListTreeView.selectedIndexes():
            sel = self.backgroundListTreeView.selectedIndexes()
            self.backgroundList.removeRow(sel[0].row(), QtCore.QModelIndex())

    def onClearBackgroundList(self):
        self.backgroundList.clear()

    def updateBackgroundList(self):
        self.backgroundList.setSampleNameList(sorted(self.headerModel.sampleNames()))
        for c in range(self.backgroundList.columnCount()):
            self.backgroundListTreeView.resizeColumnToContents(c)

    def setHeaderModel(self, headermodel: HeaderModel):
        super().setHeaderModel(headermodel)
        self.updateBackgroundList()

    def getBackgroundSubtractionList(self):
        return self.backgroundList.getBackgroundSubtractionList()

    def getEnabledSampleNameList(self):
        return self.backgroundList.getEnabledSampleNameList()

    def save_state(self, config: ConfigParser):
        super().save_state(config)
        config['background']={}
        for i, bgl in enumerate(self.backgroundList.getBackgroundSubtractionList()):
            sample, bgname, factor = bgl
            config['background']['{:02d}'.format(i)] = '({}, {}, {:.8f})'.format(sample,bgname, factor)

    def load_state(self, config: ConfigParser):
        super().load_state(config)
        if config.has_section('background'):
            bglist=[]
            for key in sorted(config.options('background')):
                line = config['background'][key].strip()
                if not line.startswith('(') and line.endswith(')'):
                    logger.warning('Cannont load background specification from an invalid line in the config file (background section): {}'.format(line))
                    continue
                sample, bg, factor= line[1:-1].split(',')
                try:
                    factor = float(factor)
                except ValueError:
                    logger.warning('Invalid background scaling factor in the line: {}'.format(line))
                bglist.append((sample, bg, factor))
            self.backgroundList.clear()
            for sam, bg, fac in bglist:
                self.backgroundList.addSample(sam, bg, fac)
