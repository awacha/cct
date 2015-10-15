import cct.instrument.instrument
import logging
logger = logging.root
logging.basicConfig()


def callbackfunc(obj, *args, **kwargs):
    print('callbackfunc(' + str(obj.__class__) + ', '.join(str(a) for a in args) +
          ', '.join(k + '=' + str(kwargs[k]) for k in kwargs) + ')')

ins = cct.instrument.instrument.Instrument()
ins.connect_devices()
# ins.execute_command("shutter('open')")
