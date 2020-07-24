from .backend import TMCM351Backend, TMCM6110Backend
from ..generic.frontend import MotorController


class TMCM351(MotorController):
    backendclass = TMCM351Backend
    devicename = 'TMCM351'


class TMCM6110(MotorController):
    backendclass = TMCM6110Backend
    devicename = 'TMCM6110'
