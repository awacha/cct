from ..devices.detector import Pilatus
from ..devices.xray_source import GeniX
from ..devices.motor import TMCM551, TMCM6110
from ..devices.vacuumgauge import VacuumGauge
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
        self.configfile = os.path.join(self.configdir, 'cct.json')
        self._initialize_config()
        
    def _initialize_config(self):
        """Create a sane configuration in `self.config` from sratch."""
        self.config = {}
        self.config['connections'] = {}
        self.config['connections']['xray_source'] = {'host':'genix.credo',
                                                     'port':502,
                                                     'timeout':1,
                                                     'name':'pilatus'}
        self.config['connections']['detector'] = {'host':'pilatus300k.credo',
                                                  'port':41234,
                                                  'timeout':0.01,
                                                  'poll_timeout':0.01,
                                                  'name':'genix'}
        self.config['connections']['vacgauge'] = {'host':'devices.credo',
                                                  'port':2006,
                                                  'timeout':0.01,
                                                  'poll_timeout':0.01,
                                                  'name':'tpg201'}
        self.config['connections']['motorcontrollers'] = {}
        self.config['connections']['motorcontrollers']['tmcm351a'] = {
            'host':'devices.credo',
            'port':2003,
            'timeout':0.01,
            'poll_timeout':0.01,
            'name':'tmcm351a'}
        self.config['connections']['motorcontrollers']['tmcm351b'] = {
            'host':'devices.credo',
            'port':2004,
            'timeout':0.01,
            'poll_timeout':0.01,
            'name':'tmcm351b'}
        self.config['connections']['motorcontrollers']['tmcm6110'] = {
            'host':'devices.credo',
            'port':2005,
            'timeout':0.01,
            'poll_timeout':0.01,
            'name':'tmcm6110'}
            
    
    def save_state(self):
        dic = {'xray_source': self.xray_source._save_state(),
               'detector': self.detector._save_state()}
        for m in self.motorcontrollers:
            dic[m._instancename] = m.save_state()
        with open(self.configfile, 'wt', encoding='utf-8') as f:
            json.dump(dic, f)

    def load_state(self):
        try:
            with open(self.configfile, 'rt', encoding='utf-8') as f:
                dic=json.load(f)
        except IOError:
            return
        self.config['connection
        dic['connections']['xray_source']['host']
            
