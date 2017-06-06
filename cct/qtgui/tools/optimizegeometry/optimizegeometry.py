import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
from PyQt5 import QtWidgets, QtCore, QtGui
from .optimizegeometry_ui import Ui_Form
from .resultsstore import PinholeConfigurationStore
from ...core.mixins import ToolWindow
from .simpleeditablelist import SimpleEditableList
from .pinholeconfiguration import PinholeConfiguration
from multiprocessing import Queue, Process
from queue import Empty


def worker(queue: Queue, spacers, pinholes, ls, lbs, sd, mindist_l1, mindist_l2, sealringwidth, wavelength,
           crit_sample, crit_beamstop, crit_l1, crit_l2, keep_best_n=200):
    try:
        results=[]
        for phc in PinholeConfiguration.enumerate(spacers, pinholes, ls, lbs, sd, mindist_l1, mindist_l2, sealringwidth,
                                                  wavelength):
            assert isinstance(phc, PinholeConfiguration)
            if phc.l1 < crit_l1:
#                print('L1 not OK: {} < {}'.format(phc.l1, crit_l1))
                continue
            if phc.l2 < crit_l2:
#                print('L2 not OK: {} < {}'.format(phc.l2, crit_l2))
                continue
            if phc.Dbs < crit_beamstop[0] or phc.Dbs > crit_beamstop[1]:
#                print('BS not OK: {} not between {} and {}'.format(phc.Dbs, crit_beamstop[0], crit_beamstop[1]))
                continue
            if phc.Dsample < crit_sample[0] or phc.Dsample > crit_sample[1]:
#                print('Sample not OK: {} not between {} and {}'.format(phc.Dsample, crit_sample[0], crit_sample[1]))
                continue
#            print('OK: {}'.format(phc))
            results.append(phc)
    finally:
        queue.put_nowait(sorted(results, key=lambda phc:-phc.intensity)[:keep_best_n])


class OptimizeGeometry(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.progressBar.hide()
        self.pinholeList = SimpleEditableList(self.groupBox)
        self.pinholeList.setTitle('Apertures (\u03bcm):')
        l = self.groupBox.layout()
        assert isinstance(l, QtWidgets.QHBoxLayout)
        l.insertWidget(0, self.pinholeList)
        self.spacerList = SimpleEditableList(self.groupBox)
        self.spacerList.setTitle('Spacers (mm):')
        l.insertWidget(0, self.spacerList)
        self.pinholeList.addItems(self.credo.config['gui']['optimizegeometry']['pinholes'])
        self.spacerList.addItems(self.credo.config['gui']['optimizegeometry']['spacers'])
        self.resultsStore = PinholeConfigurationStore()
        self.treeView.setModel(self.resultsStore)
        self.optimizePushButton.clicked.connect(self.calculate)
        self.copyToClipboardPushButton.clicked.connect(self.copyToHTML)
        self.updateSetupParametersPushButton.clicked.connect(self.updateSetupParameters)
        self.sealingRingWidthdoubleSpinBox.setValue(self.credo.config['gui']['optimizegeometry']['sealingringwidth'])
        self.wavelengthDoubleSpinBox.setValue(self.credo.config['geometry']['wavelength'])
        self.L1WithoutSpacersDoubleSpinBox.setValue(self.credo.config['gui']['optimizegeometry']['L1withoutspacers'])
        self.L2WithoutSpacersDoubleSpinBox.setValue(self.credo.config['gui']['optimizegeometry']['L2withoutspacers'])
        self.sampleDetectorDistanceDoubleSpinBox.setValue(self.credo.config['geometry']['dist_sample_det'])
        self.detectorBeamstopDistanceDoubleSpinBox.setValue(
            self.credo.config['gui']['optimizegeometry']['detector_beamstop_distance'])
        self.ph3SampleDistanceDoubleSpinBox.setValue(
            self.credo.config['gui']['optimizegeometry']['ph3_sample_distance'])
        self.minPh1Ph2DistanceDoubleSpinBox.setValue(
            self.credo.config['gui']['optimizegeometry']['minimum_ph1_ph2_distance'])
        self.minPh2Ph3DistanceDoubleSpinBox.setValue(
            self.credo.config['gui']['optimizegeometry']['minimum_ph2_ph3_distance'])
        self.minSampleSizeDoubleSpinBox.setValue(
            self.credo.config['gui']['optimizegeometry']['minimum_sample_diameter'])
        self.maxSampleSizeDoubleSpinBox.setValue(
            self.credo.config['gui']['optimizegeometry']['maximum_sample_diameter'])
        self.minBeamStopSizeDoubleSpinBox.setValue(
            self.credo.config['gui']['optimizegeometry']['minimum_beamstop_diameter'])
        self.maxBeamStopSizeDoubleSpinBox.setValue(
            self.credo.config['gui']['optimizegeometry']['maximum_beamstop_diameter'])

    def setBusy(self):
        super().setBusy()
        self.optimizePushButton.setEnabled(False)
        self.updateSetupParametersPushButton.setEnabled(False)
        self.copyToClipboardPushButton.setEnabled(False)
        self.groupBox.setEnabled(False)
        self.treeView.setEnabled(False)
        self.progressBar.show()

    def setIdle(self):
        super().setIdle()
        self.optimizePushButton.setEnabled(True)
        self.updateSetupParametersPushButton.setEnabled(True)
        self.copyToClipboardPushButton.setEnabled(True)
        self.groupBox.setEnabled(True)
        self.treeView.setEnabled(True)
        self.progressBar.hide()

    def calculate(self):
        if hasattr(self, 'process'):
            return
        spacers = [float(x) for x in self.spacerList.items()]
        pinholes = [float(x) for x in self.pinholeList.items()]
        ls = self.ph3SampleDistanceDoubleSpinBox.value()
        lbs = self.detectorBeamstopDistanceDoubleSpinBox.value()
        sd = self.sampleDetectorDistanceDoubleSpinBox.value()
        mindist_l1 = self.L1WithoutSpacersDoubleSpinBox.value()
        mindist_l2 = self.L2WithoutSpacersDoubleSpinBox.value()
        sealringwidth = self.sealingRingWidthdoubleSpinBox.value()
        wavelength = self.wavelengthDoubleSpinBox.value()
        crit_sample = self.minSampleSizeDoubleSpinBox.value(), self.maxSampleSizeDoubleSpinBox.value()
        crit_beamstop = self.minBeamStopSizeDoubleSpinBox.value(), self.maxBeamStopSizeDoubleSpinBox.value()
        crit_l1 = self.minPh1Ph2DistanceDoubleSpinBox.value()
        crit_l2 = self.minPh2Ph3DistanceDoubleSpinBox.value()
        n_max_results = self.nResultsSpinBox.value()
        self.resultsQueue = Queue()
        self.process = Process(target=worker,
                               args=(self.resultsQueue, spacers, pinholes, ls, lbs, sd, mindist_l1, mindist_l2,
                                     sealringwidth, wavelength, crit_sample, crit_beamstop, crit_l1, crit_l2,
                                     n_max_results))
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100)
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.checkWorkerResults)
        self.process.start()
        self.timer.start()
        self.setBusy()

    def checkWorkerResults(self):
        try:
            result = self.resultsQueue.get_nowait()
            #logger.debug('Finished processing.')
            self.process.join()
            self.timer.stop()
            del self.resultsQueue
            del self.process
            del self.timer
            self.resultsStore.addConfigurations(result)
            for i in range(self.resultsStore.columnCount()):
                self.treeView.resizeColumnToContents(i)
            self.setIdle()
        except Empty:
            return

    def copyToHTML(self):
        html="""<table>\n"""
        html+="  <tr>\n"
        html+="     <th><i>l<sub>1</sub></i> parts (mm)</th>\n"
        html+="     <th><i>l<sub>2</sub></i> parts (mm)</th>\n"
        html+="     <th>1<sup>st</sup> aperture (\u03bcm)</th>\n"
        html+="     <th>2<sup>nd</sup> aperture (\u03bcm)</th>\n"
        html+="     <th>3<sup>rd</sup> aperture (\u03bcm)</th>\n"
        html+="     <th>Intensity (\u03bcm<sup>4</sup>mm<sup>-2</sup>)</th>\n"
        html+="     <th>Sample size (mm)</th>\n"
        html+="     <th>Beamstop size (mm)</th>\n"
        html+="     <th><i>l<sub>1</sub></i> (mm)</th>\n"
        html+="     <th><i>l<sub>2</sub></i> (mm)</th>\n"
        html+="     <th>S-D distance (mm)</th>\n"
        html+="     <th>Divergence (mrad)</th>\n"
        html+="     <th>Smallest <i>q</i> (nm<sup>-1</sup>)</th>\n"
        html+="     <th>Largest <i>d</i> (nm)</th>\n"
        html+="     <th>Largest <i>R<sub>g</sub></i> (nm)</th>\n"
        html+="     <th>Largest sphere size (nm)</th>\n"
        html+="     <th>Dominant constraint</th>\n"
        html+="  </tr>\n"
        selectedrows=sorted({index.row() for index in self.treeView.selectedIndexes()})
        for index in selectedrows:
            phc=self.resultsStore.getConfiguration(index)
            html+="  <tr>\n"
            html+="    <td>{}</td>\n".format(", ".join([str(x) for x in phc.l1_elements]))
            html+="    <td>{}</td>\n".format(", ".join([str(x) for x in phc.l2_elements]))
            html+="    <td>{:.0f}</td>\n".format(phc.D1)
            html+="    <td>{:.0f}</td>\n".format(phc.D2)
            html+="    <td>{:.0f}</td>\n".format(phc.D3)
            html+="    <td>{:.1f}</td>\n".format(phc.intensity)
            html+="    <td>{:.3f}</td>\n".format(phc.Dsample)
            html+="    <td>{:.3f}</td>\n".format(phc.Dbs)
            html+="    <td>{:.0f}</td>\n".format(phc.l1)
            html+="    <td>{:.0f}</td>\n".format(phc.l2)
            html+="    <td>{:.2f}</td>\n".format(phc.sd)
            html+="    <td>{:.3f}</td>\n".format(phc.alpha*1000)
            html+="    <td>{:.4f}</td>\n".format(phc.qmin)
            html+="    <td>{:.1f}</td>\n".format(phc.dmax)
            html+="    <td>{:.1f}</td>\n".format(phc.Rgmax)
            html+="    <td>{:.1f}</td>\n".format(phc.dspheremax)
            html+="    <td>{}</td>\n".format(phc.dominant_constraint)
            html+="  </tr>\n"
        html+="</table>\n"
        clipboard=QtGui.QGuiApplication.clipboard()
        assert isinstance(clipboard, QtGui.QClipboard)
        mimedata=QtCore.QMimeData()
        mimedata.setHtml(html)
        clipboard.setMimeData(mimedata)
        QtWidgets.QMessageBox.information(self, "Configurations copied", "{} pinhole configuration(s) copied to the clipboard.".format(selectedrows))


    def updateSetupParameters(self):

        pass
