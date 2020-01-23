import logging
import re
import typing
from multiprocessing.managers import SyncManager
from multiprocessing.pool import Pool

from PyQt5 import QtCore

from .backgroundrunner import JobRecord, BackgroundRunner
from ...core.processing.subtractingjob import SubtractingJob

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SubtractionJobRecord(JobRecord):
    ValidMethods = ['None', 'Constant', 'Interval', 'Power-law']
    samplename: str
    backgroundname: typing.Optional[str]
    _scalingmethod: str  # 'None', 'Constant', 'Interval', 'Power-law'
    scalingparameters: typing.Any

    def __init__(self, lockmanager: SyncManager, samplename: str,
                 backgroundname: typing.Optional[str] = None, scalingmethod: str = 'None',
                 scalingparameters: typing.Any = None):
        super().__init__(lockmanager)
        self.samplename = samplename
        self.backgroundname = backgroundname
        self.scalingmethod = scalingmethod
        self.scalingparameters = scalingparameters

    @property
    def scalingmethod(self) -> str:
        return self._scalingmethod

    @scalingmethod.setter
    def scalingmethod(self, newvalue: str):
        if newvalue not in ['None', 'Constant', 'Interval', 'Power-law']:
            raise ValueError('Invalid scaling method: "{}" (type: {})'.format(newvalue, type(newvalue)))
        self._scalingmethod = newvalue
        if newvalue == 'None':
            self.scalingparameters = None
        elif newvalue == 'Constant':
            self.scalingparameters = 0
        elif newvalue == 'Interval':
            self.scalingparameters = (0, 0, 10)  # qmin, qmax, qcount
        elif newvalue == 'Power-law':
            self.scalingparameters = (0, 0, 10, None)  # qmin, qmax, qcount, exponent
        else:
            assert False

    def formatParameters(self) -> str:
        if self._scalingmethod == 'None':
            return '--'
        elif self._scalingmethod == 'Constant':
            return '{:.6f}'.format(self.scalingparameters)
        elif self._scalingmethod == 'Interval':
            return '[{:.3f}, {:.3f}]'.format(*self.scalingparameters)
        elif self._scalingmethod == 'Power-law':
            return '[{:.3f}, {:.3f}]'.format(*self.scalingparameters)
        else:
            raise ValueError('Invalid scaling method: {}'.format(self._scalingmethod))

    def submit(self, jobid: int, pool: Pool, project: "Project"):
        super().submit(jobid, pool, project)
        if self.backgroundname is None:
            return
        self.asyncresult = pool.apply_async(
            SubtractingJob.run,
            kwds={'jobid': jobid,
                  'h5writerLock': project.h5Lock,
                  'killswitch': self.killswitch,
                  'resultsqueue': self.messageQueue,
                  'h5file': project.config.hdf5,
                  'samplename': self.samplename,
                  'backgroundname': self.backgroundname,
                  'subtractmode': self.scalingmethod,
                  'subtractparameters': self.scalingparameters
                  })

    def reap(self, project: "Project"):
        self.lastProcessingResult = self.asyncresult.get()
        self.statusmessage = 'Finished in {:.2f} seconds.'.format(self.lastProcessingResult.time_total)
        self.asyncresult = None
        super().reap(project)

    def __repr__(self) -> str:
        if self.scalingmethod == 'None':
            subtractparameters = '()'
        elif self.scalingmethod == 'Constant':
            subtractparameters = '{:.16g}'.format(self.scalingparameters)
        elif self.scalingmethod == 'Interval':
            subtractparameters = '(qmin={:.16g}, qmax={:.16g}, qcount={:d})'.format(*self.scalingparameters)
        elif self.scalingmethod == 'Power-law':
            subtractparameters = '(qmin={:.16g}, qmax={:.16g}, qcount={:d}, exponent={})'.format(
                self.scalingparameters[0],
                self.scalingparameters[1],
                self.scalingparameters[2],
                '{:.16g}'.format(self.scalingparameters[3] if self.scalingparameters[3] is not None else 'None')
            )
        else:
            raise ValueError('Unknown scaling method: {}'.format(self.scalingmethod))
        return "SubtractionJobRecord(sample='{}', background='{}', mode='{}', params='{}')".format(
            self.samplename,
            self.backgroundname if self.backgroundname is not None else '-- None --',
            self.scalingmethod,
            subtractparameters)

    @classmethod
    def fromString(cls, string: str, lockManager: SyncManager):
        m = re.match(r"SubtractionJobRecord\(sample='(?P<samplename>.+)', background='(?P<backgroundname>.+)'"
                     r", mode='(?P<mode>.+)', params='(?P<params>.+)'\)", string)
        if m is None:
            raise ValueError('Error interpreting linearized subtraction job record: {}'.format(string))
        samplename = m['samplename']
        backgroundname = m['backgroundname']
        if backgroundname == '-- None --':
            backgroundname = None
        mode = m['mode']
        if mode not in ['None', 'Constant', 'Interval', 'Power-law']:
            raise ValueError('Unknown subtraction mode: {}'.format(mode))
        if mode == 'None':
            if m['params'] != '()':
                raise ValueError('Subtraction mode "None" does not need any parameters.')
            params = None
        elif mode == 'Constant':
            params = float(m['params'])
        elif mode == 'Interval':
            m1 = re.match(r'\(qmin=(?P<qmin>.+), qmax=(?P<qmax>.+), qcount=(?P<qcount>.+)\)', m['params'])
            params = (float(m1['qmin']), float(m1['qmax']), int(m1['qcount']))
        elif mode == 'Power-law':
            m1 = re.match(r'\(qmin=(?P<qmin>.+), qmax=(?P<qmax>.+), qcount=(?P<qcount>.+), exponent=(?P<exponent>)\)',
                          m['params'])
            params = (float(m1['qmin']), float(m1['qmax']), int(m1['qcount']),
                      None if m1['exponent'] == 'None' else float(m1['exponent']))
        else:
            assert False
        return cls(lockManager, samplename, backgroundname, mode, params)


class Subtractor(BackgroundRunner):
    _columnnames = ['Sample', 'Background', 'Scaling method', 'Scaling parameters', 'Result']  # fill this
    _jobs = typing.List[SubtractionJobRecord]

    def __init__(self, project: "Project"):
        super().__init__(project)
        self.fromConfig()

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> typing.Any:
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return self._jobs[index.row()].samplename
            elif index.column() == 1:
                return self._jobs[index.row()].backgroundname if self._jobs[
                                                                     index.row()].backgroundname is not None else '-- None --'
            elif index.column() == 2:
                return self._jobs[index.row()].scalingmethod
            elif index.column() == 3:
                return self._jobs[index.row()].formatParameters()
            elif index.column() == 4:
                return self._jobs[index.row()].statusmessage
        elif role == QtCore.Qt.EditRole:
            if index.column() == 3:
                return self._jobs[index.row()].scalingparameters
        return super().data(index, role)

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = None) -> bool:
        if index.column() == 3 and role == QtCore.Qt.EditRole:
            self._jobs[index.row()].scalingparameters = value
            self.dataChanged.emit(self.index(index.row(), index.column()), self.index(index.row(), index.column()))
            self.toConfig()
            return True
        elif index.column() == 1 and role == QtCore.Qt.EditRole:
            self._jobs[index.row()].backgroundname = value
            self.dataChanged.emit(self.index(index.row(), index.column()), self.index(index.row(), index.column()))
            self.toConfig()
            return True
        elif index.column() == 2 and role == QtCore.Qt.EditRole:
            self._jobs[index.row()].scalingmethod = value
            self.dataChanged.emit(self.index(index.row(), index.column()), self.index(index.row(), self.columnCount()))
            self.toConfig()
            return True
        return super().setData(index, value, role)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        # edit this to your needs
        if index.column() == 0:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable
        elif index.column() == 1:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled
        elif index.column() == 2:
            if self[index].backgroundname is not None:
                return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled
            else:
                return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable
        elif index.column() == 3:
            if self[index].backgroundname is not None and self[index].scalingmethod != 'None':
                return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEditable
            else:
                return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable
        elif index.column() == 4:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled

    def removeRow(self, row: int, parent: QtCore.QModelIndex = None, updateConfig: bool = True) -> bool:
        return self.removeRows(row, 1, parent, updateConfig=updateConfig)

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = None, updateConfig: bool = True) -> bool:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        self.beginRemoveRows(QtCore.QModelIndex(), row, row + count)
        for i in reversed(range(row, row + count)):
            del self._jobs[i]
        self.endRemoveRows()
        if updateConfig:
            self.toConfig()
        return True

    def add(self, samplename: str, updateConfig: bool = True):
        # edit this to your needs
        self.beginInsertRows(QtCore.QModelIndex(), self.rowCount(), self.rowCount() + 1)
        self._jobs.append(SubtractionJobRecord(self.project.multiprocessingmanager, samplename))
        self.endInsertRows()
        if updateConfig:
            self.toConfig()

    def __contains__(self, item: str):
        return bool([d for d in self._jobs if d.samplename == item])

    def samplenames(self) -> typing.List[str]:
        return sorted(set([d.samplename for d in self._jobs]))

    def __getitem__(self, item):
        return self._jobs[item] if not isinstance(item, QtCore.QModelIndex) else self._jobs[item.row()]

    def _recreateJobs(self):
        # we don't need this.
        samplenames = sorted(self.project.headerList.samples())
        self.fromConfig()
        # add missing samples
        for sn in samplenames:
            if sn not in self:
                self.add(sn, updateConfig=False)
        # remove invalid samples
        for invalidjob in [j for j in self._jobs if j.samplename not in samplenames]:
            rowindex = self._jobs.index(invalidjob)
            self.beginRemoveRows(QtCore.QModelIndex(), rowindex, rowindex)
            self._jobs.remove(invalidjob)
            self.endRemoveRows()
        # set background name to None where the original background name is now invalid
        for invalidbg in [j for j in self._jobs if j.backgroundname not in samplenames]:
            rowindex = self._jobs.index(invalidbg)
            invalidbg.backgroundname = None
            self.dataChanged.emit(self.index(rowindex, 0), self.index(rowindex, self.columnCount()))
        self.toConfig()

    def updateList(self):
        """Update the list with new sample names and remove invalid ones."""
        self._recreateJobs()

    def toConfig(self):
        logger.debug('Subtractor.toConfig')
        if len(list(self.project.headerList.samples())) == 0:
            logger.debug('Not clobbering config')
            return  # do not clobber the config
        self.project.config.subtraction = '; '.join([repr(j) for j in self._jobs])

    def fromConfig(self):
        self.beginResetModel()
        self._jobs = []
        for string in self.project.config.subtraction.split(';'):
            if not string:
                continue
            self._jobs.append(SubtractionJobRecord.fromString(string.strip(), self.project.multiprocessingmanager))
        self.endResetModel()

    def configItemChanged(self, section: str, itemname: str, newvalue: typing.Any):
        if itemname == 'subtraction':
            self.fromConfig()
