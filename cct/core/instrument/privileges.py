from typing import Union


class PrivilegeError(Exception):
    pass

class PrivilegeLevel(object):
    _instances = []

    @classmethod
    def register(cls, instance: 'PrivilegeLevel'):
        if not [i for i in cls._instances if i.normalizedname == instance.normalizedname]:
            cls._instances.append(instance)
        else:
            raise ValueError('Another instance exists with normalized name ' + instance.normalizedname)
        cls._instances.sort(key=lambda x: x.ordinal)

    @classmethod
    def get_priv(cls, priv: Union['PrivilegeLevel', str, int]):
        if isinstance(priv, cls):
            return priv
        elif isinstance(priv, str):
            priv = cls.normalizename(priv)
            lis = [i for i in cls._instances if i.normalizedname == priv]
            assert len(lis) <= 1  # the normalized name is a "key".
            return lis[0]
        elif isinstance(priv, int):
            lis = [i for i in cls._instances if i.ordinal == priv]
            return lis[0]
        else:
            raise TypeError(priv)

    @staticmethod
    def normalizename(name: str):
        return name.upper().replace(' ', '_').replace('-', '_')

    def __init__(self, name: str, ordinal: int):
        self.name = name
        self.ordinal = ordinal
        self.normalizedname = self.normalizename(self.name)
        self.register(self)

    def __eq__(self, privlevel: 'PrivilegeLevel'):
        if isinstance(privlevel, type(self)):
            return privlevel.ordinal == self.ordinal
        else:
            return NotImplemented

    def __lt__(self, privlevel: 'PrivilegeLevel'):
        if isinstance(privlevel, type(self)):
            return self.ordinal < privlevel.ordinal
        else:
            return NotImplemented

    def __gt__(self, privlevel: 'PrivilegeLevel'):
        if isinstance(privlevel, type(self)):
            return self.ordinal > privlevel.ordinal
        else:
            return NotImplemented

    def __le__(self, privlevel: 'PrivilegeLevel'):
        if isinstance(privlevel, type(self)):
            return self.ordinal <= privlevel.ordinal
        else:
            return NotImplemented

    def __ge__(self, privlevel: 'PrivilegeLevel'):
        if isinstance(privlevel, type(self)):
            return self.ordinal >= privlevel.ordinal
        else:
            return NotImplemented

    def __ne__(self, privlevel: 'PrivilegeLevel'):
        if isinstance(privlevel, type(self)):
            return self.ordinal != privlevel.ordinal
        else:
            return NotImplemented

    def is_allowed(self, privlevel: 'PrivilegeLevel'):
        return privlevel <= self

    def get_allowed(self):
        return [i for i in type(self)._instances if self.is_allowed(i)]

    @classmethod
    def all_privileges(cls):
        return cls._instances


PRIV_LAYMAN = PrivilegeLevel('Layman', 0)
PRIV_BEAMSTOP = PrivilegeLevel('Beamstop', 10)
PRIV_CONNECTDEVICES = PrivilegeLevel('(Dis)connect Devices', 15)
PRIV_PINHOLE = PrivilegeLevel('Pinhole', 20)
PRIV_PROJECTMAN = PrivilegeLevel('Manage Projects', 30)
PRIV_MOTORCALIB = PrivilegeLevel('Calibrate Motors', 40)
PRIV_MOTORCONFIG = PrivilegeLevel('Configure Motors', 50)
PRIV_DEVICECONFIG = PrivilegeLevel('Configure Devices', 55)
PRIV_USERMAN = PrivilegeLevel('Manage Users', 60)
PRIV_SUPERUSER = PrivilegeLevel('Superuser', 100)
