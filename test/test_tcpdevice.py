import cct.devices.vacuumgauge
import cct.devices.detector
import cct.devices.xray_source
import cct.devices.motor
import logging
logger = logging.root
logging.basicConfig()


def callbackfunc(obj, *args, **kwargs):
    print('callbackfunc(' + str(obj.__class__) + ', '.join(str(a) for a in args) +
          ', '.join(k + '=' + str(kwargs[k]) for k in kwargs) + ')')
genix = cct.devices.xray_source.GeniX('genix')
genix.connect('error', callbackfunc)
genix.connect('variable-change', callbackfunc)
genix.connect_device('genix.credo', 502, 1)

vacgauge = cct.devices.vacuumgauge.VacuumGauge('vacgauge')
vacgauge.connect('error', callbackfunc)
vacgauge.connect('variable-change', callbackfunc)
vacgauge.connect_device('devices.credo', 2006, 0.01, 0.01)

pilatus = cct.devices.detector.Pilatus('pilatus')
pilatus.connect('error', callbackfunc)
pilatus.connect('variable-change', callbackfunc)
pilatus.connect_device('pilatus300k.credo', 41234, 0.01, 0.01)

tmc1 = cct.devices.motor.TMCM351('tmcm351a')
tmc1.connect('error', callbackfunc)
tmc1.connect('variable_change', callbackfunc)
tmc1.connect_device('devices.credo', 2003, 0.01, 0.01)

tmc2 = cct.devices.motor.TMCM351('tmcm351b')
tmc2.connect('error', callbackfunc)
tmc2.connect('variable_change', callbackfunc)
tmc2.connect_device('devices.credo', 2004, 0.01, 0.01)

tmc3 = cct.devices.motor.TMCM6110('tmcm6110')
tmc3.connect('error', callbackfunc)
tmc3.connect('variable_change', callbackfunc)
tmc3.connect_device('devices.credo', 2005, 0.01, 0.01)
