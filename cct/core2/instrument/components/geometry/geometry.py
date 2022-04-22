import json
import logging
import os
import pickle
from typing import Any, Optional, Final, List, Dict, Union

import numpy as np
from PyQt5 import QtCore

from .choices import GeometryChoices
from ..component import Component

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Geometry(QtCore.QObject, Component):
    """Describes current and possible geometries

    The current values of the geometry settings are stored in config['geometry'], to be accessed there by the rest of
    the program.
    """
    choices: GeometryChoices

    def __init__(self, **kwargs):
        self.presets = {}
        super().__init__(**kwargs)  # this implies self.loadFromConfig()
        self.choices = GeometryChoices(config=self.config)
        # if some values are missing, add them
        for parameter, defaultvalue in [
            ('l1_elements', []),
            ('l2_elements', []),
            ('pinhole_1', 0.0),
            ('pinhole_2', 0.0),
            ('pinhole_3', 0.0),
            ('flightpipes', []),
            ('beamstop', 4.0),
            ('l1base', 104.0),
            ('l2base', 104.0),
            ('isoKFspacer', 4.0),
            ('ph3toflightpipes', 304.0),
            ('lastflightpipetodetector', 89.0),
            ('ph3tosample', 126.0),
            ('beamstoptodetector', 78.0),
            ('wavelength', 0.1542),
            ('wavelength.err', 0.0),
            ('sourcetoph1', 200.0),
            ('dist_sample_det', 100.0),
            ('dist_sample_det.err', 0.1),
            ('beamposx', 300.0),
            ('beamposx.err', 1.0),
            ('beamposy', 240.0),
            ('beamposy.err', 1.0),
            ('mask', 'mask.mat'),
            ('description', 'Unspecified geometry'),
            ('pixelsize', 0.172),
            ('pixelsize.err', 0.0002),
        ]:
            if parameter not in self.config['geometry']:
                self.config['geometry'][parameter] = defaultvalue

        # remove obsolete parameters
        for parameter in [
            'dist_source_ph1',  # -> sourcetoph1
            'dist_ph3_sample',  # -> ph3tosample
            'dist_det_beamstop',  # -> beamstoptodetector
            'pinhole1',  # -> pinhole_1
            'pinhole2',  # -> pinhole_2
            'pinhole3',  # -> pinhole_3
        ]:
            if parameter in self.config['geometry']:
                del self.config['geometry'][parameter]

        if 'presets' in self.config['geometry']:
            logger.info('Converting presets to external files.')
            # presets are obsolete, write simple geometry files
            os.makedirs('geo', exist_ok=True)
            for presetname in self.config['geometry']['presets']:
                logger.debug(f'Converting preset {presetname}')
                presetconf = self.config['geometry']['presets'][presetname]
                filename = presetname
                for forbiddenchar in " <>:\"/\\|?*'":
                    filename = filename.replace(forbiddenchar, '_')
                geoconf = self.config['geometry'].asdict()
                del geoconf['choices']
                del geoconf['presets']
                geoconf['l1_elements'] = presetconf['l1_elements']
                geoconf['l2_elements'] = presetconf['l2_elements']
                geoconf['pinhole_1'] = presetconf['pinhole1']
                geoconf['pinhole_2'] = presetconf['pinhole2']
                geoconf['pinhole_3'] = presetconf['pinhole3']
                geoconf['beamstop'] = presetconf['beamstop']
                geoconf['flightpipes'] = presetconf['flightpipes']
                geoconf['dist_sample_det'] = presetconf['dist_sample_det'][0]
                geoconf['dist_sample_det.err'] = presetconf['dist_sample_det'][1]
                geoconf['beamposx'] = presetconf['beamposx'][0]
                geoconf['beamposx.err'] = presetconf['beamposx'][1]
                geoconf['beamposy'] = presetconf['beamposy'][0]
                geoconf['beamposy.err'] = presetconf['beamposy'][1]
                geoconf['mask'] = presetconf['mask']
                geoconf['description'] = presetconf['description']
                self.saveGeometry(os.path.join('geo', filename + '.geoj'), geoconf)
                self.saveGeometry(os.path.join('geo', filename + '.geop'), geoconf)

    #        del self.config['geometry']['presets']
        self.recalculateDerivedParameters()

    def onConfigChanged(self, path, value):
        if path[0] != 'geometry':
            return
        if path[1] in ['l1_elements', 'l2_elements', 'l1base', 'isoKFspacer', 'pinhole_1', 'pinhole_2', 'pinhole_3',
                       'dist_sample_det', 'ph3tosample', 'beamstoptodetector', 'beamstop', 'wavelength']:
            self.recalculateDerivedParameters()

    def recalculateDerivedParameters(self):
        l1 = self.config['geometry']['l1'] = \
            len(self.config['geometry']['l1_elements']) * self.config['geometry']['isoKFspacer'] + \
            sum(self.config['geometry']['l1_elements']) + self.config['geometry']['l1base']
        l2 = self.config['geometry']['l2'] = \
            len(self.config['geometry']['l2_elements']) * self.config['geometry']['isoKFspacer'] + \
            sum(self.config['geometry']['l2_elements']) + self.config['geometry']['l2base']
        ph1 = self.config['geometry']['pinhole_1']
        ph2 = self.config['geometry']['pinhole_2']
        ph3 = self.config['geometry']['pinhole_3']

        sd = self.config['geometry']['dist_sample_det']
        ph3tosample = self.config['geometry']['ph3tosample']
        ph3todetector = ph3tosample + sd
        beamstoptodetector = self.config['geometry']['beamstoptodetector']
        ph3tobeamstop = ph3todetector - beamstoptodetector
        beamstopradius = self.config['geometry']['beamstop']
        self.config['geometry']['intensity'] = ph1 ** 2 * ph2 ** 2 / l1 ** 2
        self.config['geometry']['dbeam_at_ph3'] = ((ph1 + ph2) * (l1 + l2) / l1 - ph1) / 1000
        dbeamsample = self.config['geometry']['dbeam_at_sample'] = ((ph1 + ph2) * (
                l1 + l2 + ph3tosample) / l1 - ph1) / 1000
        self.config['geometry']['dbeam_at_bs'] = ((ph1 + ph2) * (1 + l2 + ph3tobeamstop) / l1 - ph1) / 1000
        self.config['geometry']['dparasitic_at_bs'] = ((ph2 + ph3) * (l2 + ph3tobeamstop) / l2 - ph2) / 1000
        beamstopshadowradius = ((dbeamsample + beamstopradius) * sd / (sd - beamstoptodetector) - dbeamsample) * 0.5
        self.config['geometry']['qmin'] = 4 * np.pi * np.sin(0.5 * np.arctan(beamstopshadowradius / sd)) / \
                                          self.config['geometry']['wavelength']

    def saveGeometry(self, filename: str, configdict: Optional[Dict[str, Any]] = None):
        """Save the current settings under a preset name"""
        if configdict is None:
            configdict = self.config['geometry']
        dic = {key:configdict[key] for key in [
            'l1_elements', 'l2_elements',
            'pinhole_1', 'pinhole_2', 'pinhole_3', 'flightpipes', 'beamstop', 'dist_sample_det', 'dist_sample_det.err',
            'beamposx', 'beamposx.err', 'beamposy', 'beamposy.err', 'mask', 'description', 'l1base', 'l2base',
            'isoKFspacer', 'ph3tosample', 'beamstoptodetector', 'ph3toflightpipes', 'pixelsize', 'pixelsize.err',
            'wavelength', 'wavelength.err', 'sourcetoph1', 'lastflightpipetodetector']}
        if filename.lower().endswith('.geoj'):
            with open(filename, 'wt') as f:
                json.dump(dic, f)
        elif filename.lower().endswith('.geop'):
            with open(filename, 'wb') as f:
                pickle.dump(dic, f)
        else:
            raise ValueError(f'Unknown file extension: {os.path.splitext(filename)[-1]}')
        logger.info(f'Saved current geometry to file {filename}.')

    def loadGeometry(self, filename: str):
        """Load the geometry from a file"""
        if filename.lower().endswith('.geoj'):
            with open(filename, 'rt') as f:
                dic = json.load(f)
        elif filename.lower().endswith('.geop'):
            with open(filename, 'rb') as f:
                dic = pickle.load(f)
        else:
            raise ValueError(f'Unknown file extension: {os.path.splitext(filename)[-1]}')
        for key in dic:
            self.config['geometry'][key] = dic[key]
        self.recalculateDerivedParameters()
        logger.info(f'Loaded geometry from file {filename}.')

    def l1(self, geometrydict: Optional[Dict[str, Any]] = None) -> float:
        if geometrydict is None:
            geometrydict = self.config['geometry']
        print(geometrydict)
        return geometrydict['l1base'] + geometrydict['isoKFspacer'] * len(geometrydict['l1_elements']) + sum(
            'l1_elements')

    def l2(self, geometrydict: Optional[Dict[str, Any]] = None) -> float:
        if geometrydict is None:
            geometrydict = self.config['geometry']
        return geometrydict['l2base'] + geometrydict['isoKFspacer'] * len(geometrydict['l2_elements']) + sum(
            'l2_elements')

    def updateFromOptimizerResult(self, optresult: Dict[str, Any]):
        for key in ['l1_elements', 'l2_elements', 'pinhole_1', 'pinhole_2', 'pinhole_3', 'flightpipes', 'beamstop',
                    'l1', 'l2', 'ph3todetector', 'dbeam_at_ph3', 'dbeam_at_bs', 'dbeam_at_sample', 'dparasitic_at_bs',
                    'qmin', 'intensity']:
            self.config['geometry'][key] = optresult[key]
