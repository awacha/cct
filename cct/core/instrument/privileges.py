class PrivilegeLevel(object):

    _instances=[]

    @classmethod
    def register(cls, instance):
        if not [i for i in cls._instances if i.normalizedname==instance.normalizedname]:
            cls._instances.append(instance)
        cls._instances.sort(key=lambda x:x.ordinal)

    @classmethod
    def get_priv(cls, priv):
        if isinstance(priv, cls):
            return priv
        elif isinstance(priv, str):
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
