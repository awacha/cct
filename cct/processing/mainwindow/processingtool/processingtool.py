import logging
import queue
import threading
from typing import Iterable, List, Optional

import numpy as np
from PyQt5 import QtWidgets, QtCore

from .processingtool_ui import Ui_Form
from ..toolbase import ToolBase
from ....core.processing.summarize import Summarizer
from ....core.utils.timeout import IdleFunction

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ProcessingTool(ToolBase, Ui_Form):
    processingDone = QtCore.pyqtSignal()

    def setupUi(self, Form):
        super().setupUi(Form)
        self.progressGroupBox.setVisible(False)
        self.processPushButton.clicked.connect(self.onProcess)
        self.configWidgets = [
            (self.errorPropagationComboBox, 'processing', 'errorpropagation'),
            (self.abscissaErrorPropagationComboBox, 'processing', 'abscissaerrorpropagation'),
            (self.stdMultiplierDoubleSpinBox, 'processing', 'std_multiplier'),
            (self.qMaxDoubleSpinBox, 'processing', 'customqmax'),
            (self.qMinDoubleSpinBox, 'processing', 'customqmin'),
            (self.qBinCountSpinBox, 'processing', 'customqcount'),
            (self.logarithmicCorrelMatrixCheckBox, 'processing', 'logcorrelmatrix'),
            (self.sanitizeCurvesCheckBox, 'processing', 'sanitizecurves'),
            (self.logarithmicQCheckBox, 'processing', 'customqlogscale'),
            (self.qRangeOverrideGroupBox, 'processing', 'customq'),
            (self.corrmatOutlierMethodComboBox, 'processing', 'corrmatmethod'),
        ]

    def onProcess(self):
        self.queue = queue.Queue()
        badfsns = self.headerModel.get_badfsns()
        if self.qRangeOverrideGroupBox.isChecked():
            qmin = self.qMinDoubleSpinBox.value()
            qmax = self.qMaxDoubleSpinBox.value()
            nq = self.qBinCountSpinBox.value()
            if self.logarithmicQCheckBox.isChecked():
                qrange = np.logspace(np.log10(qmin), np.log10(qmax), nq)
            else:
                qrange = np.linspace(qmin, qmax, nq)
        else:
            qrange = None
        kwargs = {
            'fsns': self.headerModel.goodfsns(),
            'exppath': self.headerModel.eval2d_pathes,
            'parampath': self.headerModel.eval2d_pathes,
            'maskpath': self.headerModel.mask_pathes,
            'outputfile': self.h5FileName,
            'prefix': self.cctConfig['path']['prefixes']['crd'],
            'ndigits': self.cctConfig['path']['fsndigits'],
            'errorpropagation': self.errorPropagationComboBox.currentIndex(),
            'abscissaerrorpropagation': self.abscissaErrorPropagationComboBox.currentIndex(),
            'sanitize_curves': self.sanitizeCurvesCheckBox.isChecked(),
            'logarithmic_correlmatrix': self.logarithmicCorrelMatrixCheckBox.isChecked(),
            'std_multiplier': self.stdMultiplierDoubleSpinBox.value(),
            'queue': self.queue,
            'qrange': qrange,
            'backgroundsubtraction': self.siblings['background'].getBackgroundSubtractionList(),
            'samplenamelist': self.siblings['background'].getEnabledSampleNameList(),
            'corrmatoutliermethod': ['zscore', 'zscore_mod', 'iqr'][self.corrmatOutlierMethodComboBox.currentIndex()]
        }
        self.processingprocess = threading.Thread(target=self.do_processing, name='Summarization', kwargs=kwargs)
        self.idlefcn = IdleFunction(self.check_processing_progress, 100)
        self.processingprocess.start()
        self.progressGroupBox.setVisible(True)
        self.processPushButton.setEnabled(False)
        self.busy.emit(True)
        self.progressGroupBox.setEnabled(True)

    def do_processing(self, queue: queue.Queue,
                      fsns: Iterable[int], exppath: Iterable[str], parampath: Iterable[str], maskpath: Iterable[str],
                      outputfile: str, prefix: str, ndigits: int, errorpropagation: int, abscissaerrorpropagation: int,
                      sanitize_curves: bool, logarithmic_correlmatrix: bool, std_multiplier: int,
                      qrange: Optional[np.ndarray], backgroundsubtraction: List, samplenamelist: List[str],
                      corrmatoutliermethod: str):
        s = Summarizer(fsns, exppath, parampath, maskpath, outputfile, prefix, ndigits, errorpropagation,
                       abscissaerrorpropagation, sanitize_curves, logarithmic_correlmatrix, std_multiplier, qrange,
                       samplenamelist, corrmatoutliermethod)
        queue.put_nowait(('__init_loadheaders__', len(fsns)))
        for msg1, msg2 in s.load_headers(yield_messages=True):
            queue.put_nowait((msg1, msg2))
        for msg1, msg2 in s.summarize(True, yield_messages=True):
            queue.put_nowait((msg1, msg2))
        for msg1, msg2 in s.backgroundsubtraction(backgroundsubtraction, yield_messages=True):
            queue.put_nowait((msg1, msg2))
        queue.put_nowait(('__done__', None))
        return True

    @property
    def stdMultiplier(self):
        return self.stdMultiplierDoubleSpinBox.value()

    @property
    def corrMatMethod(self):
        return self.corrmatOutlierMethodComboBox.currentText()

    @property
    def corrMatMethodIdx(self):
        return self.corrmatOutlierMethodComboBox.currentIndex()

    def processing_finished(self):
        if self.processingprocess is not None:
            self.processingprocess.join()
            self.processingprocess = None
        self.progressGroupBox.setVisible(False)
        if self.idlefcn is not None:
            self.idlefcn.stop()
            self.idlefcn = None
        self.processPushButton.setEnabled(True)
        self.updateBadFSNs(processingfinished=True)
        self.queue = None
        self.processingDone.emit()
        self.busy.emit(False)

    def check_processing_progress(self):
        if self.processingprocess is None:
            self.processing_finished()
            return False
        try:
            assert isinstance(self.queue, queue.Queue)
            for imessage in range(20):
                msg1, msg2 = self.queue.get_nowait()
                if msg1 == '__init_summarize__':
                    assert isinstance(msg2, int)  # msg2 is the number of samples times the number of distances
                    self.progressBar1.setMinimum(0)
                    self.progressBar1.setMaximum(msg2)
                    self.progressbar1StatusLabel.setText('')
                    self.progressbar1TitleLabel.setText('Processed sample:')
                    self.progressbar2TitleLabel.setText('Processed exposure:')
                    self.progressBar2.setMinimum(0)
                    self.progressBar2.setMaximum(0)
                    self.progressBar2.setVisible(True)
                    self.progressbar2TitleLabel.setVisible(True)
                    self.progressbar2StatusLabel.setVisible(True)
                elif msg1 == '__init_loadheaders__':
                    assert isinstance(msg2, int)  # the number of headers to load
                    self.progressBar2.setVisible(False)
                    self.progressbar2StatusLabel.setVisible(False)
                    self.progressbar2TitleLabel.setVisible(False)
                    self.progressbar1TitleLabel.setText('Loaded header:')
                    self.progressbar1StatusLabel.setText('')
                    self.progressBar1.setMinimum(0)
                    self.progressBar1.setMaximum(msg2)
                    self.progressBar1.setValue(0)
                elif msg1 in ['__header_loaded__', '__header_notfound__']:
                    # loaded a header for FSN
                    assert isinstance(msg2, int)  # msg2 is the FSN of the header just loaded or not found.
                    self.progressBar1.setValue(self.progressBar1.value() + 1)
                    self.progressbar1StatusLabel.setText('{:d}'.format(msg2))
                elif msg1 in ['__exposure_loaded__', '__exposure_notfound__']:
                    self.progressBar2.setValue(self.progressBar2.value() + 1)
                    self.progressbar2StatusLabel.setText('{:d}'.format(msg2))
                elif msg1 == '__init_collect_exposures__':
                    self.progressbar2TitleLabel.setText('Processed exposure:')
                    self.progressbar2StatusLabel.setText('')
                    self.progressBar2.setMinimum(0)
                    self.progressBar2.setMaximum(msg2)
                elif msg1 == '__init_stabilityassessment__':
                    self.progressBar2.setMinimum(0)
                    self.progressBar2.setMaximum(0)
                    self.progressbar2StatusLabel.setText('')
                    self.progressbar2TitleLabel.setText('Stability assessment...')
                elif msg1 == '__done__':
                    self.processing_finished()
                    return False
                elif msg1 == '__init_backgroundsubtraction__':
                    self.progressbar1TitleLabel.setText('Background subtraction')
                    self.progressbar1StatusLabel.setText('')
                    self.progressbar2StatusLabel.setVisible(False)
                    self.progressbar2TitleLabel.setVisible(False)
                    self.progressBar2.setVisible(False)
                    self.progressBar1.setMinimum(0)
                    self.progressBar1.setMaximum(msg2)
                elif msg1.startswith('__'):
                    pass
                else:
                    assert isinstance(msg1, str)  # sample
                    if isinstance(msg2, float):  # distance
                        self.progressbar1StatusLabel.setText('{} ({:.2f} mm)'.format(msg1, msg2))
                    elif isinstance(msg2, str):  # background name
                        self.progressbar1StatusLabel.setText('{} - {}'.format(msg1, msg2))
                    self.progressBar1.setValue(self.progressBar1.value() + 1)
        except queue.Empty:
            return True
        return True

    def updateBadFSNs(self, processingfinished: bool = False):
        newbadfsns = []
        try:
            for sn in self.h5GetSamples():
                #            logger.debug('updateBadFSNs: sample {}'.format(sn))
                for d in self.h5GetDistances(sn):
                    #                logger.debug('updateBadFSNs: dist {}'.format(d))
                    with self.getHDF5Group(sn, d) as grp:
                        if 'curves' not in grp:
                            continue
                        #                    logger.debug('Reading curves...')
                        newbadfsns.extend(
                            [dset.attrs['fsn'] for dset in grp['curves'].values() if dset.attrs['correlmat_bad']])
            #                    logger.debug('...Read curves.')
        except OSError:
            # happens when the .h5 file is not present
            pass
        if self.autoMarkBadExposuresCheckBox.isChecked():
            try:
                self.headerModel.update_badfsns(newbadfsns)
            except AttributeError:
                pass
        if processingfinished:
            if newbadfsns:
                QtWidgets.QMessageBox.information(
                    self, 'Processing finished',
                    'Found and marked new bad exposures:\n' + ', '.join(
                        [str(f) for f in sorted(newbadfsns)]),
                )
            else:
                QtWidgets.QMessageBox.information(
                    self, 'Processing finished',
                    'No new bad exposures found',
                )

    def setH5FileName(self, h5filename: str):
        super().setH5FileName(h5filename)
        self.processPushButton.setEnabled(True)
        self.updateBadFSNs()
