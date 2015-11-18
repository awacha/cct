import kerberos
import logging
import pickle

from .service import Service, ServiceError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class PrivilegeLevel(object):
    LAYMAN = 0
    BEAMSTOP = 10
    PINHOLE = 20
    CALIBRATE_MOTORS = 30
    CONFIGURE_MOTORS = 40
    MANAGE_USERS = 50
    SUPERUSER = 100

    @classmethod
    def tostr(cls, level):
        for levelname in cls.all_levels():
            if cls.__dict__[levelname] == level:
                return levelname.replace('_', ' ').title()
        raise NotImplementedError(level)

    @classmethod
    def fromstr(cls, levelname):
        return cls.__dict__[levelname.replace(' ', '_').upper()]

    @classmethod
    def all_levels(cls):
        return sorted([k for k in cls.__dict__ if k.upper() == k and not (k.startswith('__') or k.endswith('__'))],
                      key=lambda x: cls.fromstr(x))

    @classmethod
    def levels_below(cls, level):
        if isinstance(level, str):
            level = cls.fromstr(level)
            returnstr = True
        else:
            returnstr = False
        levels = [cls.fromstr(l) for l in cls.all_levels() if cls.fromstr(l) <= level]
        if returnstr:
            return [cls.tostr(l) for l in levels]
        else:
            return levels


class User(object):
    username = None
    firstname = None
    lastname = None
    privlevel = None

    def __init__(self, uname, firstname, lastname, privlevel=PrivilegeLevel.LAYMAN):
        self.username = uname
        self.firstname = firstname
        self.lastname = lastname
        self.privlevel = privlevel

class Project(object):
    projectid = None
    projectname = None
    proposer = None

    def __init__(self, pid, pname, proposer):
        self.projectid = pid
        self.projectname = pname
        self.proposer = proposer



class Accounting(Service):
    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self._user = None
        self._privlevel = None

    def authenticate(self, username, password):
        if '@' not in username:
            username = username + '@' + self.get_default_realm()
        try:
            if kerberos.checkPassword(username, password, '', '', 0):
                try:
                    self._user = [u for u in self._users if u.username == username.split('@', 1)[0]][0]
                except IndexError:
                    self._users.append(User(username.split('@', 1)[0], 'Firstname', 'Lastname', PrivilegeLevel.LAYMAN))
                    self._user = self._users[-1]
                    self._privlevel = self._user.privlevel
                    self.instrument.config['services']['accounting']['operator'] = self._user.username
                return True
        except kerberos.BasicAuthError:
            return False

    def get_default_realm(self):
        try:
            return self.instrument.config['services']['accounting']['default_realm']
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

    def get_user(self):
        return self._user

    def get_privilegelevel(self):
        return self._privlevel

    def set_privilegelevel(self, level):
        if isinstance(level, str):
            level = PrivilegeLevel.fromstr(level)
        if level <= self._user.privlevel:
            self._privlevel = level
        else:
            raise ServiceError('Insufficient privileges')

    def get_accessible_privlevels_str(self):
        return PrivilegeLevel.levels_below(PrivilegeLevel.tostr(self._user.privlevel))

    def _load_state(self, dictionary):
        logger.debug('Accounting: load state')
        try:
            self._dbfilename = dictionary['dbfile']
        except KeyError:
            logger.debug('No dbfilename, using default')
            self._dbfilename = 'config/userdb'
        try:
            with open(self._dbfilename, 'rb') as f:
                userdb = pickle.load(f)
            self._users = userdb['users']
            self._projects = userdb['projects']
        except FileNotFoundError:
            logger.debug('Could not load dbfile.')
            self._users = [User('root', 'System', 'Administrator', PrivilegeLevel.SUPERUSER)]
            self._projects = [Project('MS 01', 'Machine Studies', 'System')]
        try:
            self.select_project(dictionary['projectid'])
        except KeyError:
            logger.debug('Could not select project')

    def _save_state(self):
        logger.debug('Saving state for accounting')
        dic = Service._save_state(self)
        dic['dbfile'] = self._dbfilename
        dic['projectid'] = self._project.projectid
        dic['operator'] = self._user.username
        dic['projectname'] = self._project.projectname
        dic['proposer'] = self._project.proposer
        try:
            with open(self._dbfilename, 'wb') as f:
                pickle.dump({'users': self._users, 'projects': self._projects}, f)
        finally:
            return dic

    def get_projectids(self):
        return sorted([p.projectid for p in self._projects])

    def new_project(self, projectid, projectname, proposer):
        self._projects = [p for p in self._projects if p.projectid != projectid]
        prj = Project(projectid, projectname, proposer)
        self._projects.append(prj)
        logger.debug('Added project: %s, %s, %s' % (projectid, projectname, proposer))
        self.select_project(projectid)
        return prj

    def select_project(self, projectid):
        self._project = self.get_project(projectid)
        logger.debug('Selected project: %s' % self._project.projectid)
        self.instrument.config['services']['accounting']['projectid'] = self._project.projectid
        self.instrument.config['services']['accounting']['projectname'] = self._project.projectname
        self.instrument.config['services']['accounting']['proposer'] = self._project.proposer

    def get_project(self, projectid=None):
        if projectid is None:
            projectid = self._project.projectid
        projects = [p for p in self._projects if p.projectid == projectid]
        if not projects:
            prj = self.new_project('MS 01', 'Machine Studies', 'System')
            projects = [prj]
        assert (len(projects) == 1)
        return projects[0]
