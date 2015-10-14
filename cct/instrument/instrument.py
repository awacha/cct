import json
import os

from gi.repository import GObject


class Instrument(GObject.GObject):
    configdir = 'config'

    def __init__(self):
        GObject.GObject.__init__(self)
        self.xray_source = None
        self.detector = None
        self.motorcontrollers = None
        self.motors = None
        self.configfile = os.path.join(self.configdir, 'cct.conf')

    def save_state(self, file):
        dic = {'xray_source': self.xray_source._save_state(),
               'detector': self.detector._save_state()}
        for m in self.motorcontrollers:
            dic[m._instancename] = m.save_state()
        with open(self.configfile, 'wt', encoding='utf-8') as f:
            json.dump(dic, f)

    def load_state(self, file):
        with open(self.configfile, 'rt', encoding='utf-8') as f:
            json.load(f)
