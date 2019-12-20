"""Interface class for the background processing task"""
import logging
from multiprocessing import Manager
from multiprocessing.pool import Pool
from typing import Sequence, Optional, List, Any

import numpy as np
from PyQt5 import QtCore
from sastool.classes2 import Header

from .backgroundrunner import JobRecord, BackgroundRunner
from ...core.processing import ProcessingJob

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ProcessingJobRecord(JobRecord):
    samplename: str
    distance: float
    temperature: Optional[float]
    fsns: List[int]

    def __init__(self, samplename: str, distance: float, temperature: Optional[float], fsns: Sequence[int],
                 lockmanager: Manager):
        super().__init__(lockmanager)
        self.samplename = samplename
        self.distance = distance
        self.temperature = temperature
        self.fsns = list(fsns)

    def submit(self, jobid: int, pool: Pool, project: "Project"):
        if project.config.autoq:
            if project.config.customqlogscale:
                qrange = np.logspace(np.log10(project.config.customqmin), np.log10(project.config.customqmax),
                                     project.config.customqcount)
            else:
                qrange = np.linspace(project.config.customqmin, project.config.customqmax, project.config.customqcount)
        else:
            qrange = None
        self.asyncresult = pool.apply_async(
            ProcessingJob.run,
            kwds={'jobid': jobid,
                  'h5writerLock': project.h5Lock,
                  'killswitch': self.killswitch,
                  'resultsqueue': self.messageQueue,
                  'h5file': project.config.hdf5,
                  'rootdir': project.config.datadir,
                  'fsnlist': self.fsns,
                  'badfsns': project.badfsns,
                  'ierrorprop': project.config.errorpropagation,
                  'qerrorprop': project.config.abscissaerrorpropagation,
                  'outliermethod': project.config.outliermethod,
                  'outliermultiplier': project.config.std_multiplier,
                  'logcmat': project.config.logcorrelmatrix,
                  'qrange': qrange,
                  'bigmemorymode': False,
                  })

    def reap(self, project:"Project"):
        self.lastProcessingResult = self.asyncresult.get()
        self.statusmessage = 'Finished in {:.2f} seconds.'.format(self.lastProcessingResult.time_total)
        self.asyncresult = None
        if self.lastProcessingResult.success:
            project.addBadFSNs(self.lastProcessingResult.badfsns)


class Processor(BackgroundRunner):
    """A front-end and scheduler for background data processing jobs.

    This is implemented as an item model, to be used in treeviews.

    Columns are:
        0: sample name (user checkable)
        1: distance
        2: temperature
        3: number of exposures
        4: progress bar
    """
    _columnnames: List[str] = ['Sample name', 'Distance', 'Temperature', 'Count', 'Status']
    TEMPERATURETOLERANCE: float = 0.5  # ToDo: make this a config item
    _headers: List[Header]
    classifyByTemperature: bool = False  # ToDo: make this some kind of property

    def __init__(self, project: "Project"):
        self._headers = []
        super().__init__(project)

    def setHeaders(self, headers: Sequence[Header]):
        if self.isBusy():
            raise RuntimeError('Cannot change the headers while busy.')
        self._headers = list(headers)  # make a copy
        self._recreateJobs()

    def _recreateJobs(self):
        self.beginResetModel()
        self._jobs = []
        try:
            for title in sorted({h.title for h in self._headers}):
                for distance in sorted({float(h.distance) for h in self._headers if h.title == title}):
                    if self.classifyByTemperature:
                        temperatures = {}
                        for h in self._headers:
                            if h.title != title or float(h.distance) != distance:
                                continue
                            if h.temperature is None:
                                try:
                                    temperatures[None].append(h)
                                except KeyError:
                                    temperatures[None] = [h]
                            else:
                                # find the nearest temperature
                                try:
                                    nearest = sorted([k for k in temperatures if (k is not None) and
                                                      abs(float(h.temperature) - k) <= self.TEMPERATURETOLERANCE],
                                                     key=lambda k: abs(float(h.temperature) - k))[0]
                                    temperatures[nearest].append(h)
                                except IndexError:
                                    temperatures[float(h.temperature)] = [h]
                        for temp in temperatures:
                            self._jobs.append(
                                ProcessingJobRecord(title, distance, temp, [h.fsn for h in temperatures[temp]],
                                                    lockmanager=self.project.multiprocessingmanager
                                                    ))
                    else:
                        self._jobs.append(ProcessingJobRecord(title, distance, None,
                                                              [h.fsn for h in self._headers
                                                               if h.title == title
                                                               and float(h.distance) == float(distance)],
                                                              lockmanager=self.project.multiprocessingmanager))
        finally:
            self.endResetModel()

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return self._jobs[index.row()].samplename
            elif index.column() == 1:
                return '{:.2f}'.format(self._jobs[index.row()].distance)
            elif index.column() == 2:
                return '{:.2f}°C'.format(self._jobs[index.row()].temperature) \
                    if self._jobs[index.row()].temperature is not None else '--'
            elif index.column() == 3:
                return '{:d}'.format(len(self._jobs[index.row()].fsns))
            elif index.column() == 4:
                return self._jobs[index.row()].statusmessage if self._jobs[index.row()].errormessage is None else \
                    self._jobs[index.row()].errormessage  # the custom item delegate takes care of this
        return super().data(index, role)

    def newBadFSNs(self) -> List[int]:
        ret = []
        for j in self._jobs:
            if (j.lastProcessingResult is not None) and j.lastProcessingResult.success:
                ret.extend(j.lastProcessingResult.badfsns)
        return ret
