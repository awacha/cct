import logging
import os
import pickle
from typing import List, Any

from PySide6 import QtCore, QtWidgets

from .project import Project
from ..auth import Privilege, needsprivilege
from ..component import Component

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ProjectManager(Component, QtCore.QAbstractItemModel):
    _projects: List[Project]
    _currentproject: Project

    def __init__(self, **kwargs):
        self._projects = []
        super().__init__(**kwargs)

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._projects)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 3

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        prj = self._projects[index.row()]
        if (index.column() == 0) and (role in [QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole]):
            return prj.projectid
        elif (index.column() == 1) and (role in [QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole]):
            return prj.proposer
        elif (index.column() == 2) and (role in [QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole]):
            return prj.title
        elif role == QtCore.Qt.ItemDataRole.UserRole:
            return prj
        elif (role == QtCore.Qt.ItemDataRole.UserRole) and (index.column() == 0):
            return QtWidgets.QApplication.instance().style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_DialogOkButton) if self._currentproject is prj else None

    @needsprivilege(Privilege.ProjectManagement, 'Insufficient privileges')
    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if role != QtCore.Qt.ItemDataRole.EditRole:
            return False
        prj = self._projects[index.row()]
        if (index.column() == 0) and (value not in self):
            prj.projectid = str(value)
        elif index.column() == 1:
            prj.proposer = value
        elif index.column() == 2:
            prj.title = value
        else:
            return False
        self.dataChanged.emit(index, index)
        if index.column() == 0:
            self.beginResetModel()
            self._projects = sorted(self._projects, key=lambda p: p.projectid)
            self.endResetModel()
        self.saveToConfig()
        return True

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if not self.instrument.auth.hasPrivilege(Privilege.ProjectManagement):
            return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
        return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEditable

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Orientation.Horizontal) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return ['ID', 'Proposer', 'Title'][section]

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    @needsprivilege(Privilege.ProjectManagement, 'Insufficient privileges')
    def addProject(self, projectid: str):
        if projectid in self:
            raise RuntimeError(f'Project {projectid} already exists')
        row = max([i for i, p in enumerate(self._projects) if p.projectid < projectid] + [-1]) + 1
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._projects.insert(row, Project(projectid))
        self.endInsertRows()
        self.saveToConfig()

    @needsprivilege(Privilege.ProjectManagement, 'Insufficient privileges')
    def removeProject(self, projectid: str):
        row = [i for i, p in enumerate(self._projects) if p.projectid == projectid][0]
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._projects[row]
        self.endRemoveRows()
        self.saveToConfig()

#    def __getitem__(self, item) -> Project:
#        try:
#            return [p for p in self._projects if p.projectid == item][0]
#        except IndexError:
#            raise KeyError(item)

#    def __contains__(self, item) -> bool:
#        return bool([p for p in self._projects if p.projectid == item])

    def saveToConfig(self):
        logger.debug('SaveToConfig() starting')
        self.cfg['projects', 'current'] = self._currentproject.projectid
        self.cfg['projects', 'projects'] = {p.projectid: p.__getstate__() for p in self._projects}
        logger.debug('SaveToConfig() ended.')

    def loadFromConfig(self):
        if ('projects', 'projects') in self.cfg:
            # new-style config
            self.beginResetModel()
            for prjname in self.cfg['projects',  'projects']:
                prj = Project('')
                prj.__setstate__(self.cfg['projects',  'projects',  prjname])
                self._projects.append(prj)
            self._projects = sorted(self._projects, key=lambda p: p.projectid)
            self.setProject(self.cfg['projects',  'current'])
            self.endResetModel()
        elif ('services', 'accounting') in self.cfg:
            dbfile = self.cfg['services',  'accounting',  'dbfile']
            currentprojectid = self.cfg['services',  'accounting',  'projectid']
            self.beginResetModel()
            with open(os.path.join('config', dbfile), 'rb') as f:
                prjdb = pickle.load(f)['projects']
            for prj in prjdb:
                self._projects.append(Project(prj.projectid, prj.proposer, prj.projectname))
            self._projects = sorted(self._projects, key=lambda p: p.projectid)
            self.setProject(currentprojectid)
            self.endResetModel()
        else:
            self.beginResetModel()
            self._projects = [Project('Untitled', 'Anonymous', 'Untitled')]
            self.setProject('Untitled')
            self.endResetModel()
            self.saveToConfig()

    def setProject(self, projectid: str):
        logger.debug(f'Setting project to {projectid}')
        try:
            self._currentproject = [p for p in self._projects if p.projectid == projectid][0]
        except IndexError:
            return
        logger.info(f'Current project changed to {self._currentproject}')
        self.saveToConfig()

    def projectID(self) -> str:
        return self._currentproject.projectid

    def project(self) -> Project:
        return self._currentproject
