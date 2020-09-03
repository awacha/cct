import os
import pickle
from typing import List, Any

from PyQt5 import QtCore

from .project import Project
from ..auth import Privilege
from ..component import Component


class ProjectManager(QtCore.QAbstractItemModel, Component):
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
        if (index.column() == 0) and (role in [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]):
            return prj.projectid
        elif (index.column() == 1) and (role in [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]):
            return prj.proposer
        elif (index.column() == 2) and (role in [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]):
            return prj.title
        elif role == QtCore.Qt.UserRole:
            return prj

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if not self.instrument.auth.hasPrivilege(Privilege.ProjectManagement):
            raise RuntimeError('Insufficient privileges')
        if role != QtCore.Qt.EditRole:
            return
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
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['ID', 'Proposer', 'Title'][section]

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def addProject(self, projectid: str):
        if not self.instrument.auth.hasPrivilege(Privilege.ProjectManagement):
            raise RuntimeError('Insufficient privileges')
        if projectid in self:
            raise RuntimeError(f'Project {projectid} already exists')
        row = max([i for i, p in enumerate(self._projects) if p.projectid < projectid] + [-1]) + 1
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._projects.insert(row, Project(projectid))
        self.endInsertRows()
        self.saveToConfig()

    def removeProject(self, projectid: str):
        if not self.instrument.auth.hasPrivilege(Privilege.ProjectManagement):
            raise RuntimeError('Insufficient privileges')
        row = [i for i, p in enumerate(self._projects) if p.projectid == projectid][0]
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._projects[row]
        self.endRemoveRows()
        self.saveToConfig()

    def __getitem__(self, item) -> Project:
        try:
            return [p for p in self._projects if p.projectid == item][0]
        except IndexError:
            raise KeyError(item)

    def __contains__(self, item) -> bool:
        return bool([p for p in self._projects if p.projectid == item])

    def saveToConfig(self):
        self.config['projects'] = {
            'projects': {p.projectid: p.__getstate__() for p in self._projects},
            'current': self._currentproject.projectid,
        }
        removedprojects = [p for p in self.config['projects']['projects'] if p not in self]
        for p in removedprojects:
            del self.config['projects']['projects'][p]

    def loadFromConfig(self):
        if ('projects' in self.config) and ('projects' in self.config['projects']):
            # new-style config
            self.beginResetModel()
            for prjname in self.config['projects']['projects']:
                prj = Project('')
                prj.__setstate__(self.config['projects']['projects'][prjname])
                self._projects.append(prj)
            self._projects = sorted(self._projects, key=lambda p: p.projectid)
            self.setProject(self.config['projects']['current'])
            self.endResetModel()
        elif ('services' in self.config) and ('accounting' in self.config['services']):
            dbfile = self.config['services']['accounting']['dbfile']
            currentprojectid = self.config['services']['accounting']['projectid']
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

    def setProject(self, projectid: str):
        self._currentproject = self[projectid]

    def projectID(self) -> str:
        return self._currentproject.projectid

    def project(self) -> Project:
        return self._currentproject
