import kerberos
import logging
import pickle

from gi.repository import GObject

from .service import Service, ServiceError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)




class PrivilegeLevel(object):

    _instances=[]

    @classmethod
    def register(cls, instance):
        if not [i for i in cls._instances if i.normalizedname==instance.normalizedname]:
            cls._instances.append(instance)
        cls._instances.sort(key=lambda x:x.ordinal)

    @classmethod
    def get_priv(cls, priv):
        if isinstance(priv, str):
            priv=priv.upper().replace(' ','_').replace('-','_')
            lis=[i for i in cls._instances if i.normalizedname==priv]
            assert(len(lis)<=1)
            return lis[0]
        elif isinstance(priv, int):
            lis=[i for i in cls._instances if i.ordinal==priv]
            return lis[0]
        else:
            raise TypeError(priv)

    def __init__(self, name, ordinal):
        self.name=name
        self.ordinal=ordinal
        self.normalizedname=name.upper().replace(' ','_').replace('-','_')
        self.register(self)

    def __eq__(self, privlevel):
        if isinstance(privlevel,type(self)):
            return privlevel.ordinal==self.ordinal
        else:
            return NotImplemented

    def __lt__(self, privlevel):
        if isinstance(privlevel,type(self)):
            return self.ordinal<privlevel.ordinal
        else:
            return NotImplemented

    def __gt__(self, privlevel):
        if isinstance(privlevel,type(self)):
            return self.ordinal>privlevel.ordinal
        else:
            return NotImplemented

    def __le__(self, privlevel):
        if isinstance(privlevel, type(self)):
            return self.ordinal <= privlevel.ordinal
        else:
            return NotImplemented

    def __ge__(self, privlevel):
        if isinstance(privlevel, type(self)):
            return self.ordinal >= privlevel.ordinal
        else:
            return NotImplemented

    def __ne__(self, privlevel):
        if isinstance(privlevel, type(self)):
            return self.ordinal != privlevel.ordinal
        else:
            return NotImplemented

    def is_allowed(self, privlevel):
        return privlevel<=self

    def get_allowed(self):
        return [i for i in type(self)._instances if self.is_allowed(i)]

    @classmethod
    def all_privileges(cls):
        return cls._instances

PRIV_LAYMAN=PrivilegeLevel('Layman',0)
PRIV_BEAMSTOP=PrivilegeLevel('Beamstop',10)
PRIV_PINHOLE=PrivilegeLevel('Pinhole',20)
PRIV_PROJECTMAN=PrivilegeLevel('Manage Projects',30)
PRIV_MOTORCALIB=PrivilegeLevel('Calibrate Motors',40)
PRIV_MOTORCONFIG=PrivilegeLevel('Configure Motors',50)
PRIV_USERMAN=PrivilegeLevel('Manage Users',60)
PRIV_SUPERUSER=PrivilegeLevel('Superuser',100)

class User(object):
    username = None
    firstname = None
    lastname = None
    privlevel = None

    def __init__(self, uname, firstname, lastname, privlevel=PRIV_LAYMAN):
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
    __gsignals__ = {'privlevel-changed': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'project-changed': (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self._user = User('root', 'System', 'System', PRIV_SUPERUSER)
        self._privlevel = PRIV_SUPERUSER

    def authenticate(self, username, password):
        if '@' not in username:
            username = username + '@' + self.get_default_realm()
        try:
            if kerberos.checkPassword(username, password, '', '', 0):
                try:
                    self._user = [u for u in self._users if u.username == username.split('@', 1)[0]][0]
                except IndexError:
                    self.add_user(username.split('@', 1)[0], 'Firstname', 'Lastname', PRIV_LAYMAN)
                    self._user = self._users[-1]
                self.set_privilegelevel(self._user.privlevel)
                self.instrument.config['services']['accounting']['operator'] = self._user.username
                logger.info('Authenticated user %s.' % self._user.username)
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

    def get_user(self, username=None) -> User:
        if username is None:
            return self._user
        else:
            user = [u for u in self._users if u.username == username]
            assert (len(user) == 1)
            return user[0]

    def get_usernames(self):
        return sorted([u.username for u in self._users])

    def get_privilegelevel(self) -> PrivilegeLevel:
        return self._privlevel

    def has_privilege(self, what):
        logger.debug(
            'Checking privilege: %s (%s) <=? %s (%s)' % (what, type(what), self._privlevel, type(self._privlevel)))
        return self._privlevel.is_allowed(what)

    def set_privilegelevel(self, level):
        level = PrivilegeLevel.get_priv(level)
        if self._user.privlevel.is_allowed(level):
            self._privlevel = level
            self.emit('privlevel-changed', self._privlevel)
        else:
            raise ServiceError('Insufficient privileges')

    def get_accessible_privlevels_str(self):
        return [p.name for p in self._privlevel.get_allowed()]

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
            for u in self._users:
                if not isinstance(u.privlevel,PrivilegeLevel):
                    u.privlevel=PrivilegeLevel.get_priv(u.privlevel)
            self._projects = userdb['projects']
        except FileNotFoundError:
            logger.debug('Could not load dbfile.')
            self._users = [User('root', 'System', 'Administrator', PRIV_SUPERUSER)]
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
        assert (self.has_privilege(PRIV_PROJECTMAN))
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
        self.emit('project-changed')

    def get_project(self, projectid=None) -> Project:
        if projectid is None:
            projectid = self._project.projectid
        projects = [p for p in self._projects if p.projectid == projectid]
        if not projects:
            prj = self.new_project('MS 01', 'Machine Studies', 'System')
            projects = [prj]
        assert (len(projects) == 1)
        return projects[0]

    def update_user(self, username, firstname=None, lastname=None, maxpriv=None):
        user = [u for u in self._users if u.username == username][0]
        if firstname is not None:
            user.firstname = firstname
        if lastname is not None:
            user.lastname = lastname
        if maxpriv is not None:
            if user.username == self.get_user().username:
                raise ServiceError('Setting privileges of the current user is not allowed.')
            assert (self.has_privilege(PRIV_USERMAN))
            user.privlevel=PrivilegeLevel.get_priv(maxpriv)
        self.instrument.save_state()
        logger.info('Updated user %s' % username)

    def delete_user(self, username):
        if username == self.get_user().username:
            raise ServiceError('Cannot delete current user')
        assert (self.has_privilege(PRIV_USERMAN))
        self._users = [u for u in self._users if u.username != username]
        self.instrument.save_state()

    def add_user(self, username, firstname, lastname, privlevel):
        assert (not [u for u in self._users if u.username == username])
        assert (self.has_privilege(PRIV_USERMAN))
        self._users.append(User(username, firstname, lastname, privlevel))
        self.instrument.save_state()

    def delete_project(self, projectid):
        assert(not projectid==self._project.projectid)
        assert(self.has_privilege(PRIV_PROJECTMAN))
        self._projects=[p for p in self._projects if p.projectid != projectid]
        self.instrument.save_state()