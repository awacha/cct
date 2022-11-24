import hashlib
import logging
import os
import pickle
from typing import Any, List, Optional

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from .privilege import Privilege
from .user import User
from ..component import Component

logger = logging.getLogger(__name__)


class UserManager(QtCore.QAbstractItemModel, Component):
    _users: List[User]
    _currentuser: Optional[User] = None
    currentUserChanged = Signal(str)
    instance = None

    def __init__(self, **kwargs):
        if UserManager.instance is None:
            UserManager.instance = self
        else:
            raise ValueError('Only a single instance can be created of this class')
        self._users = []
        self._currentuser = None
        super().__init__(**kwargs)

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._users)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 5

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemNeverHasChildren

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        user = self._users[index.row()]
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return user
        elif (index.column() == 0) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return user.username
        elif (index.column() == 1) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return user.firstname
        elif (index.column() == 2) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return user.lastname
        elif (index.column() == 3) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return user.email
        elif (index.column() == 4) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return '|'.join(sorted([str(p.value) for p in user.privileges]))
        elif (index.column() == 4) and (role == QtCore.Qt.ItemDataRole.ToolTipRole):
            return '\n'.join(sorted([str(p.name) for p in user.privileges]))
        else:
            return None

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Orientation.Horizontal) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return ['User name', 'First name', 'Last name', 'E-mail', 'Privileges'][section]

    def addUser(self, username: str):
        if not self.hasPrivilege(Privilege.UserManagement):
            raise RuntimeError(f'User {self._currentuser.username} is not permitted to add new users.')
        if username in self:
            raise ValueError(f'Cannot add user {username}: another user exists with this name. ')
        idx = max([i for i, u in enumerate(self._users) if u.username < username] + [-1]) + 1
        self.beginInsertRows(QtCore.QModelIndex(), idx, idx)
        self._users.insert(idx, User(username))
        self.endInsertRows()
        self.saveToConfig()

    def removeUser(self, username: str):
        if not self.hasPrivilege(Privilege.UserManagement):
            raise RuntimeError(f'User {self._currentuser.username} is not permitted to remove users.')
        if username == self._currentuser.username:
            raise RuntimeError(f'You cannot delete yourself.')
        row = [i for i, u in enumerate(self._users) if u.username == username][0]
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._users[row]
        self.endRemoveRows()
        self.saveToConfig()

    def changePassword(self, password: str, username: Optional[str] = None):
        if username is None:
            username = self._currentuser.username
        if (username == self._currentuser) or self.hasPrivilege(Privilege.UserManagement):
            user = self[username]
            user.setPassword(password)
            logger.info(f'Password updated for user {username}')
            self.saveToConfig()
        else:
            raise ValueError(
                f'User {self._currentuser.username} not permitted to change the password of user {username}.')

    def changeLDAPdn(self, ldapdn: str, username: str):
        if not self.hasPrivilege(Privilege.UserManagement):
            raise ValueError(f'User {self._currentuser.username} is not permitted to change LDAP distinguished names.')
        else:
            user = self[username]
            user.ldapdn = ldapdn
            logger.info(f'LDAP distinguished name updated for user {username}')
            self.saveToConfig()

    def changeKRBPrincipal(self, principal: str, username: str):
        if not self.hasPrivilege(Privilege.UserManagement):
            raise ValueError(f'User {self._currentuser.username} is not permitted to change Kerberos principal names.')
        else:
            user = self[username]
            user.kerberosprincipal = principal
            logger.info(f'Kerberos principal name updated for user {username}')
            self.saveToConfig()

    def hasPrivilege(self, privilege: Privilege) -> bool:
        if self._currentuser is None:
            return True
        return self._currentuser.hasPrivilege(privilege)

    def __contains__(self, item: str) -> bool:
        return bool([u.username for u in self._users if item == u.username])

    def __getitem__(self, item: str) -> User:
        try:
            return [u for u in self._users if u.username == item][0]
        except IndexError:
            raise KeyError(f'Nonexistent user {item}.')

    def setUser(self, username: str, password: str):
        user = self[username]
        if user.authenticateLDAP(password) or user.authenticateKerberos(password) or user.authenticatePWHash(password):
            self._currentuser = user
            self.currentUserChanged.emit(user.username)
        else:
            raise RuntimeError(f'Could not authenticate user {username}.')

    def username(self) -> str:
        return self._currentuser.username

    def currentUser(self) -> User:
        return self._currentuser

    def loadFromConfig(self):
        if 'auth' in self.config:
            logger.debug('Loading Auth component state from new-style config.')
            self.beginResetModel()
            self._users = []
            for username in self.config['auth']['users']:
                user = User(username)
                user.__setstate__(self.config['auth']['users'][username])
                self._users.append(user)
            self._users = sorted(self._users, key=lambda u: u.username)
            self.endResetModel()
        elif ('services' in self.config) and ('accounting' in self.config['services']):
            # old-style config file
            logger.debug('Loading Auth component state from old-style config.')
            with open(os.path.join('config', self.config['services']['accounting']['dbfile']), 'rb') as f:
                userdb = pickle.load(f)
                self.beginResetModel()
                self._users = []
                for u in userdb['users']:
                    user = User(u.username)
                    user.firstname = u.firstname
                    user.lastname = u.lastname
                    user.setPasswordHash(u.passwordhash)
                    user.email = u.email
                    user.setLDAPdn(f'uid={u.username},{self.config["services"]["accounting"]["ldap_dn"]}')
                    user.setKerberosPrincipal(f'{u.username}@{self.config["services"]["accounting"]["default_realm"]}')
                    if u.privlevel.normalizedname == 'LAYMAN':
                        continue
                    for normalizedname, privilege in [
                        ('USE_BEAM_SHUTTER', Privilege.Shutter),
                        ('MOVE_MOTORS', Privilege.MoveMotors),
                        ('BEAMSTOP', Privilege.MoveBeamstop),
                        ('(DIS)CONNECT_DEVICES', Privilege.ConnectDevices),
                        ('PINHOLE', Privilege.MovePinholes),
                        ('MANAGE_PROJECTS', Privilege.ProjectManagement),
                        ('CALIBRATE_MOTORS', Privilege.MotorCalibration),
                        ('CONFIGURE_MOTORS', Privilege.MotorConfiguration),
                        ('CONFIGURE_DEVICES', Privilege.DeviceConfiguration),
                        ('MANAGE_USERS', Privilege.UserManagement),
                        ('SUPERUSER', Privilege.SuperUser)
                    ]:
                        user.grantPrivilege(privilege)
                        if u.privlevel.normalizedname == normalizedname:
                            # do not add further privileges
                            break
                    self._users.append(user)
                self._users = sorted(self._users, key=lambda u: u.username)
                self.endResetModel()
        else:
            logger.debug('No AUTH config.')
            self.beginResetModel()
            self._users = []
            self.endResetModel()

    def saveToConfig(self):
        self.config['auth'] = {}
        self.config['auth']['users'] = {user.username: user.__getstate__() for user in self._users}
        removedusers = [k for k in self.config['auth']['users'] if k not in self]
        for uname in removedusers:
            del self.config['auth']['users'][uname]

    def isAuthenticated(self) -> bool:
        return self._currentuser is not None

    def setRoot(self):
        try:
            self._currentuser = self['root']
        except KeyError:
            root = User('root')
            root.firstname = 'Rootus'
            root.lastname = 'sysadminus'
            root.grantPrivilege(Privilege.SuperUser)
            root.email = ''
            self._users.append(root)
            self._currentuser = root
