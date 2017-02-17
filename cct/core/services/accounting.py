import kerberos
import logging
import os
import pickle
import time
from typing import Optional, List, Dict, Union

from .service import Service, ServiceError
from ..instrument.privileges import PRIV_LAYMAN, PRIV_SUPERUSER, PRIV_PROJECTMAN, PRIV_USERMAN, PrivilegeLevel, \
    PrivilegeError
from ..utils.callback import SignalFlags

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class User(object):
    username = None
    firstname = None
    lastname = None
    privlevel = None

    def __init__(self, uname: str, firstname: str, lastname: str, privlevel: PrivilegeLevel = PRIV_LAYMAN):
        self.username = uname
        self.firstname = firstname
        self.lastname = lastname
        self.privlevel = privlevel


class Project(object):
    projectid = None
    projectname = None
    proposer = None

    def __init__(self, pid: str, pname: str, proposer: str):
        self.projectid = pid
        self.projectname = pname
        self.proposer = proposer


class Accounting(Service):
    __signals__ = {'privlevel-changed': (SignalFlags.RUN_FIRST, None, (object,)),
                   'project-changed': (SignalFlags.RUN_FIRST, None, ()),
                   'user-changed': (SignalFlags.RUN_FIRST, None, (object,))}

    state = {'dbfile': 'userdb',
             'projectid': 'MachineStudies 01',
             'operator': 'CREDOoperator',
             'default_realm': 'MTATTKMFIBNO',
             }

    name = 'accounting'

    def __init__(self, *args, **kwargs):
        self.current_user = None
        # start with superuser privileges, these will be dropped when someone authenticates
        self.privlevel = PRIV_SUPERUSER
        self.users = []
        self.project = None
        self.projects = []
        super().__init__(*args, **kwargs)

    def authenticate(self, username, password):
        if '@' not in username:
            username = username + '@' + self.get_default_realm()
        try:
            if kerberos.checkPassword(username, password, '', '', 0):
                logger.info('Authenticated user ' + username + '.')
                if username.split('@', 1)[0] not in [u.username for u in self.users]:
                    self.add_user(username.split('@', 1)[0], 'Firstname', 'Lastname', PRIV_LAYMAN)
                self.select_user(username)
                return True
        except kerberos.BasicAuthError as bae:
            logger.info('Failed to authenticate user {}: {}'.format(username, str(bae)))
            return False

    def select_user(self, username: str):
        self.current_user = [u for u in self.users if u.username == username.split('@', 1)[0]][0]
        self.emit('user-changed', self.current_user)
        self.set_privilegelevel(self.current_user.privlevel)
        self.instrument.config['services']['accounting']['operator'] = self.current_user.username

    def get_default_realm(self):
        try:
            return self.state['default_realm']
        except KeyError:
            try:
                with open('/etc/krb5.conf', 'rt', encoding='utf-8') as f:
                    defaultrealm = None
                    l = f.readline()
                    libdefaults_seen = False
                    while l:
                        l = l.strip()
                        if l.replace(' ', '').startswith('[libdefaults]'):
                            libdefaults_seen = True
                        elif l.startswith('['):
                            libdefaults_seen = False
                        if libdefaults_seen and ('=' in l) and l.split('=', 1)[0].strip() == 'default_realm':
                            return l.split('=', 1)[1].strip()
                        l = f.readline()
                    return None
            except FileNotFoundError:
                return None

    def get_user(self, username: Optional[str] = None) -> User:
        if username is None:
            return self.current_user
        else:
            user = [u for u in self.users if u.username == username]
            assert (len(user) == 1)  # the username is a "key": duplicates are not allowed
            return user[0]

    def get_users(self):
        return self.users

    def get_usernames(self) -> List[str]:
        return sorted([u.username for u in self.users])

    def get_privilegelevel(self) -> PrivilegeLevel:
        return self.privlevel

    def has_privilege(self, what):
        logger.debug(
            'Checking privilege: {} ({}) <=? {} ({})'.format(what, type(what), self.privlevel, type(self.privlevel)))
        return self.privlevel.is_allowed(what)

    def set_privilegelevel(self, level: Union[PrivilegeLevel, str, int]):
        level = PrivilegeLevel.get_priv(level)
        if self.current_user.privlevel.is_allowed(level):
            self.privlevel = level
            self.emit('privlevel-changed', self.privlevel)
        else:
            raise ServiceError('Insufficient privileges')

    def get_accessible_privlevels_str(self, privlevel=None):
        if privlevel is None:
            privlevel = self.privlevel
        return [p.name for p in privlevel.get_allowed()]

    def load_state(self, dictionary: Dict):
        super().load_state(dictionary)
        dbfile_last = os.path.split(self.state['dbfile'])[-1]
        if self.state['dbfile'] != dbfile_last:
            logger.warning('Stripping path from userdb file: {} -> {}'.format(self.state['dbfile'], dbfile_last))
            self.state['dbfile'] = dbfile_last
        logger.debug('Accounting: load state')
        try:
            logger.debug('Trying to load userdb from ' + os.path.join(self.configdir, self.state['dbfile']))
            with open(os.path.join(self.configdir, self.state['dbfile']), 'rb') as f:
                userdb = pickle.load(f)
            self.users = userdb['users']
            #            for u in self.users:
            #                if not isinstance(u.privlevel, PrivilegeLevel):
            #                    u.privlevel = PrivilegeLevel.get_priv(u.privlevel)
            self.projects = userdb['projects']
        except FileNotFoundError:
            logger.warning('Could not load dbfile, creating default user and project.')
            self.users = [User('root', 'System', 'Administrator', PRIV_SUPERUSER)]
            self.projects = [Project('MachineStudies {:2d}/01'.format(time.localtime().tm_year % 100),
                                     'Machine Studies', 'System')]
        try:
            self.select_project(self.state['projectid'])
        except KeyError:
            assert isinstance(self.projects[0], Project)
            self.select_project(self.projects[0].projectid)
            logger.warning('Could not select project, selected the first one.')

    def save_state(self):
        dic = super().save_state()
        try:
            with open(os.path.join(self.configdir, self.state['dbfile']), 'wb') as f:
                pickle.dump({'users': self.users, 'projects': self.projects}, f)
        finally:
            return dic

    def get_projectids(self):
        return sorted([p.projectid for p in self.projects])

    def new_project(self, projectid: str, projectname: str, proposer: str):
        if not self.has_privilege(PRIV_PROJECTMAN):
            raise PrivilegeError(PRIV_PROJECTMAN)
        self.projects = [p for p in self.projects if p.projectid != projectid]
        prj = Project(projectid, projectname, proposer)
        self.projects.append(prj)
        logger.debug('Added project: {}, {}, {}'.format(projectid, projectname, proposer))
        self.select_project(projectid)
        return prj

    def select_project(self, projectid: str):
        self.project = self.get_project(projectid)
        logger.info('Selected project: ' + self.project.projectid)
        self.state['projectid'] = self.project.projectid
        self.state['projectname'] = self.project.projectname
        self.state['proposer'] = self.project.proposer
        self.emit('project-changed')

    def get_project(self, projectid: Optional[str] = None) -> Project:
        """Get the project instance with the given ID. If no ID is given, get
        the default (current) project instance."""
        if projectid is None:
            assert self.project in self.projects
            return self.project
        projects = [p for p in self.projects if p.projectid == projectid]
        if not projects:
            raise KeyError(projectid)
        assert (len(projects) == 1)
        return projects[0]

    def update_user(self, username: str, firstname: Optional[str] = None, lastname: Optional[str] = None,
                    maxpriv: Optional[PrivilegeLevel] = None):
        if not self.has_privilege(PRIV_USERMAN):
            raise PrivilegeError(PRIV_USERMAN)
        user = [u for u in self.users if u.username == username][0]
        assert len(user) == 1
        if firstname is not None:
            user.firstname = firstname
        if lastname is not None:
            user.lastname = lastname
        if maxpriv is not None:
            if user.username == self.get_user().username:
                raise ServiceError('Setting privileges of the current user is not allowed.')
            assert (self.has_privilege(PRIV_USERMAN))
            user.privlevel = PrivilegeLevel.get_priv(maxpriv)
        self.instrument.save_state()
        logger.info('Updated user ' + username)

    def delete_user(self, username: str):
        if not self.has_privilege(PRIV_USERMAN):
            raise PrivilegeError(PRIV_USERMAN)
        if username == self.get_user().username:
            raise ServiceError('Cannot delete current user')
        self.users = [u for u in self.users if u.username != username]
        self.instrument.save_state()

    def add_user(self, username: str, firstname: str, lastname: str, privlevel: Optional[PrivilegeLevel] = PRIV_LAYMAN):
        if not self.has_privilege(PRIV_USERMAN):
            raise PrivilegeError(PRIV_USERMAN)
        if [u for u in self.users if u.username == username]:
            raise ValueError('Duplicate username {}'.format(username))
        self.users.append(User(username, firstname, lastname, privlevel))
        self.instrument.save_state()

    def delete_project(self, projectid: str):
        if not self.has_privilege(PRIV_PROJECTMAN):
            raise PrivilegeError(PRIV_PROJECTMAN)
        if projectid == self.project.projectid:
            raise ValueError('Cannot delete current project')
        self.projects = [p for p in self.projects if p.projectid != projectid]
        self.instrument.save_state()

    # noinspection PyMethodMayBeStatic
    def do_privlevel_changed(self, new_privlevel: PrivilegeLevel):
        logger.info('Privilege level changed to: ' + new_privlevel.name)
