from .service import Service


class User(object):
    userid = None
    username = None
    kerberosprincipal = None
    firstname = None
    familyname = None


class Project(object):
    projectid = None
    projecttype = None  # Inhouse, Industrial, HUNSAS
    projectname = None
    mainproposer = None
    owner = None


class Group(object):
    groupid = None
    groupname = None
    members = None


class Accounting(Service):
    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self._currentuser = None

    def authenticate(self, username, password):
        pass

    def can_i(self, group):
        pass

    def _load_state(self, dictionary):
        self._dbfilename = dictionary['dbfile']

        pass
