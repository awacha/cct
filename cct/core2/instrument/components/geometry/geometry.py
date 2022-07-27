import json
import logging
import os
import pickle
import math
from typing import Any, Optional, Final, List, Dict, Union

import h5py
import numpy as np
from PyQt5 import QtCore

from .choices import GeometryChoices
from ..component import Component

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Geometry(QtCore.QObject, Component):
    """Describes current and possible geometries

    The current values of the geometry settings are stored in config['geometry'], to be accessed there by the rest of
    the program.
    """
    choices: GeometryChoices

    def __init__(self, **kwargs):
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

            del self.config['geometry']['presets']
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

        sd = float(self.config['geometry']['dist_sample_det'])
        ph3tosample = self.config['geometry']['ph3tosample']
        ph3todetector = ph3tosample + sd
        beamstoptodetector = self.config['geometry']['beamstoptodetector']
        ph3tobeamstop = ph3todetector - beamstoptodetector
        beamstopradius = self.config['geometry']['beamstop']
        self.config['geometry']['intensity'] = ph1 ** 2 * ph2 ** 2 / l1 ** 2
        self.config['geometry']['dbeam_at_ph3'] = ((ph1 + ph2) * (l1 + l2) / l1 - ph1) / 1000
        dbeamsample = self.config['geometry']['dbeam_at_sample'] = ((ph1 + ph2) * (
                l1 + l2 + ph3tosample) / l1 - ph1) / 1000
        self.config['geometry']['dbeam_at_bs'] = float(((ph1 + ph2) * (l1 + l2 + ph3tobeamstop) / l1 - ph1) / 1000)
        self.config['geometry']['dparasitic_at_bs'] = float(((ph2 + ph3) * (l2 + ph3tobeamstop) / l2 - ph2) / 1000)
        beamstopshadowradius = ((dbeamsample + beamstopradius) * sd / (sd - beamstoptodetector) - dbeamsample) * 0.5
        try:
            self.config['geometry']['qmin'] = float(4 * np.pi * np.sin(0.5 * np.arctan(beamstopshadowradius / sd)) / \
                                                    self.config['geometry']['wavelength'])
        except ZeroDivisionError:
            self.config['geometry']['qmin'] = math.nan

    def saveGeometry(self, filename: str, configdict: Optional[Dict[str, Any]] = None):
        """Save the current settings under a preset name"""
        if configdict is None:
            configdict = self.config['geometry']
        dic = {key: configdict[key] for key in [
            'l1_elements', 'l2_elements',
            'pinhole_1', 'pinhole_2', 'pinhole_3', 'flightpipes', 'beamstop', 'dist_sample_det', 'dist_sample_det.err',
            'beamposx', 'beamposx.err', 'beamposy', 'beamposy.err', 'mask', 'description', 'l1base', 'l2base',
            'isoKFspacer', 'ph3tosample', 'beamstoptodetector', 'ph3toflightpipes', 'pixelsize', 'pixelsize.err',
            'wavelength', 'wavelength.err', 'sourcetoph1', 'lastflightpipetodetector']}
        for key, value in dic.items():
            if isinstance(value, np.number):
                dic[key] = float(value)
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
        return geometrydict['l1base'] + geometrydict['isoKFspacer'] * len(geometrydict['l1_elements']) + sum(
            geometrydict['l1_elements'])

    def l2(self, geometrydict: Optional[Dict[str, Any]] = None) -> float:
        if geometrydict is None:
            geometrydict = self.config['geometry']
        return geometrydict['l2base'] + geometrydict['isoKFspacer'] * len(geometrydict['l2_elements']) + sum(
            geometrydict['l2_elements'])

    def updateFromOptimizerResult(self, optresult: Dict[str, Any]):
        for key in ['l1_elements', 'l2_elements', 'pinhole_1', 'pinhole_2', 'pinhole_3', 'flightpipes', 'beamstop',
                    'l1', 'l2', 'ph3todetector', 'dbeam_at_ph3', 'dbeam_at_bs', 'dbeam_at_sample', 'dparasitic_at_bs',
                    'qmin', 'intensity']:
            logger.debug(f'Updating geometry from optimizer results: {key} <- {optresult[key]}')
            self.config['geometry'][key] = optresult[key]
        self.config['geometry']['dist_sample_det'] = float(optresult['sd'])
        self.config['geometry']['dist_sample_det.err'] = 0.0
        self.config['geometry']['description'] = ''

    def getHeaderEntry(self) -> Dict[str, Any]:
        dic = {}
        for key in ['dist_sample_det', 'dist_sample_det.err', 'pinhole_1', 'pinhole_2', 'pinhole_3', 'description',
                    'beamstop', 'wavelength', 'wavelength.err', 'beamposx', 'beamposy', 'beamposx.err', 'beamposy.err',
                    'mask', 'pixelsize', 'pixelsize.err']:
            dic[key] = self.config['geometry'][key]
        for key, alias in [('dist_source_ph1', 'sourcetoph1'),
                           ('dist_ph1_ph2', 'l1'),
                           ('dist_ph2_ph3', 'l2'),
                           ('dist_ph3_sample', 'ph3tosample'),
                           ('dist_det_beamstop', 'beamstoptodetector'),
                           ('dist_sample_det.val', 'dist_sample_det'),
                           ('truedistance', 'dist_sample_det'),
                           ('truedistance.err', 'dist_sample_det.err')]:
            dic[key] = self.config['geometry'][alias]
        for key, value in dic.items():
            if isinstance(value, np.number):
                dic[key] = float(value)
        return dic

    def toNeXus(self, instrumentgroup: h5py.Group, sampleshift: float=0.0) -> h5py.Group:
        """Write NeXus information

        :param instrumentgroup: NXinstrument HDF5 group
        :type instrumentgroup: h5py.Group instance
        :param sampleshift: how much the sample is nearer to the detector than the canonical position
        :type sampleshift: float (mm)
        :return: the updated NXinstrument HDF5 group
        :rtype: h5py.Group
        """
        geoconf = self.config['geometry']
        ### Add information on the beamstop
        bsgroup = instrumentgroup.require_group('beam_stop')  # should be created by the beamstop component
        bsgroup.create_dataset('size', data=geoconf['beamstop']).attrs = {'units': 'mm'}
        bsgroup.create_dataset('distance_to_detector', data=geoconf['beamstoptodetector']).attrs = {'units': 'mm'}
        trans = bsgroup.create_group('transformations')
        trans.attrs['NX_class'] = 'NXtransformations'
        trans.create_dataset('z', data=geoconf['dist_sample_det'] - sampleshift - geoconf['beamstoptodetector']).attrs = {
            'transformation_type': 'translation',
            'vector': [0, 0, 1],
            'units': 'mm',
            'depends_on': '.'
        }
        trans.create_dataset('y', data=float(bsgroup.y)).attrs = {
            'transformation_type': 'translation',
            'vector': [0, 1, 0],
            'units': 'mm',
            'depends_on': 'z'
        }
        trans.create_dataset('x', data=float(bsgroup.x)).attrs = {
            'transformation_type': 'translation',
            'vector': [1, 0, 0],
            'units': 'mm',
            'depends_on': 'y'
        }
        # Create a legacy geometry group for the beamstop
        geogrp = bsgroup.create_group('geometry')
        geogrp.attrs['NX_class'] = 'NXgeometry'
        geogrp.create_dataset('description', data=f'Beam-stop')
        geogrp.create_dataset('component_index', 1)
        shapegrp = geogrp.create_group('shape')
        shapegrp.attrs['NX_class'] = 'NXshape'
        shapegrp.create_dataset('shape', data='nxcylinder')
        shapegrp.create_dataset('size', data=[[geoconf['beamstop'], 0, 0, 0, 1]]).attrs = {'units': 'mm'}
        translationgrp = geogrp.create_group('translation')
        translationgrp.attrs['NX_class'] = 'NXtranslation'
        translationgrp.create_dataset(
            'distances', [[0, 0, geoconf['dist_sample_det'] - sampleshift - geoconf['beamstoptodetector']]]).attrs = {'units': 'mm'}

        ### Pinholes
        for ipinhole, (dist, aperture) in enumerate([
            (geoconf['ph3tosample'] + geoconf['l2'] + geoconf['l1'], geoconf['pinhole_1'] + sampleshift),
            (geoconf['ph3tosample'] + geoconf['l2'], geoconf['pinhole_2'] + sampleshift),
            (geoconf['ph3tosample'] + geoconf['pinhole_3'] + sampleshift)], start=1):
            phgrp = instrumentgroup.create_group(f'pinhole_{ipinhole}')
            phgrp.attrs['NX_class'] = 'NXaperture'
            phgrp.create_dataset('material', data='Pt-Ir alloy')
            phgrp.create_dataset('description', data=f'Pinhole #{ipinhole}')
            transgrp = phgrp.create_group('transformations')
            transgrp.create_dataset('x', data=0).attrs = {'transformation_type': 'translation', 'vector': [1, 0, 0],
                                                          'units': 'mm', 'depends_on': '.'}
            transgrp.create_dataset('y', data=0).attrs = {'transformation_type': 'translation', 'vector': [0, 1, 0],
                                                          'units': 'mm', 'depends_on': 'x'}
            transgrp.create_dataset('z', data=-dist).attrs = {'transformation_type': 'translation', 'vector': [0, 0, 1],
                                                              'units': 'mm', 'depends_on': 'y'}
            shapegrp = phgrp.create_group('shape')
            shapegrp.attrs['NX_class'] = 'NXcylindrical_geometry'
            shapegrp.create_dataset('vertices',
                                    data=[[0, 0, -dist], [0, aperture / 1000, -dist], [0, 0, -dist]]).attrs = {
                "units": 'mm'
            }
            shapegrp.create_dataset('cylinders', data=[0, 1, 2])
            # create legacy geometry class
            geogrp = phgrp.create_group('geometry')
            geogrp.attrs['NX_class'] = 'NXgeometry'
            geogrp.create_dataset('description', data=f'Pinhole #{ipinhole}')
            geogrp.create_dataset('component_index', -(3 - ipinhole) - 1)
            shapegrp = geogrp.create_group('shape')
            shapegrp.attrs['NX_class'] = 'NXshape'
            shapegrp.create_dataset('shape', data='nxcylinder')
            shapegrp.create_dataset('size', data=[[aperture / 1000, 0.1, 0, 0, 1]]).attrs = {'units': 'mm'}
            translationgrp = geogrp.create_group('translation')
            translationgrp.attrs['NX_class'] = 'NXtranslation'
            translationgrp.create_dataset('distances', [[0, 0, -dist]]).attrs = {'units': 'mm'}

        ### Crystal and Monochromator: only to set the wavelength
        crystgrp = instrumentgroup.create_group('crystal')
        crystgrp.attrs['NX_class'] = 'NXcrystal'
        crystgrp.create_dataset('wavelength', geoconf['wavelength']).attrs = {'units': 'nm'}
        crystgrp.create_dataset('wavelength_errors', geoconf['wavelength.err']).attrs = {'units': 'nm'}
        mcgrp = instrumentgroup.create_group('monochromator')
        mcgrp.attrs['NX_class'] = 'NXmonochromator'
        mcgrp.create_dataset('wavelength', geoconf['wavelength']).attrs = {'units': 'nm'}
        mcgrp.create_dataset('wavelength_errors', geoconf['wavelength.err']).attrs = {'units': 'nm'}
        hcdive = (299792458 * 6.6260705e-34 / 1.60217663e-19) * 1e9  # eV * nm
        mcgrp.create_dataset('energy', hcdive / geoconf['wavelength']).attrs = {'units': 'eV'}
        mcgrp.create_dataset('energy_errors', hcdive / geoconf['wavelength'] ** 2 * geoconf['wavelength.err']).attrs = {
            'units': 'eV'}
        mcgrp.create_dataset('wavelength_spread', geoconf['wavelength.err'] / geoconf['wavelength'])

        ### update the source
        sourcegrp: h5py.Group = instrumentgroup[[grp for grp in instrumentgroup if
                                                 ('NX_class' in instrumentgroup[grp].attrs) and (
                                                         instrumentgroup[grp].attrs['NX_class'] == 'NXsource')][0]]
        transformgrp = sourcegrp.create_group('transformations')
        transformgrp.attrs['NX_class'] = 'NXtransformations'
        transformgrp.create_dataset('x', data=0).attrs = {'transformation_type': 'translation', 'vector': [1, 0, 0],
                                                          'units': 'mm', 'depends_on': '.'}
        transformgrp.create_dataset('y', data=0).attrs = {'transformation_type': 'translation', 'vector': [1, 0, 0],
                                                          'units': 'mm', 'depends_on': 'x'}
        transformgrp.create_dataset(
            'z', data=-geoconf['ph3tosample'] - geoconf['l2'] - geoconf['l1'] - geoconf['sourcetoph1'] - sampleshift).attrs = {
            'transformation_type': 'translation', 'vector': [1, 0, 0], 'units': 'mm', 'depends_on': 'y'}
        geogrp = sourcegrp.create_group('geometry')
        geogrp.attrs['NX_class'] = 'NXgeometry'
        geogrp.create_dataset('component_index', data=-4)
        translationgrp = geogrp.create_group('translation')
        translationgrp.attrs['NX_class'] = 'NXtranslation'
        translationgrp.create_dataset('distances', [[0, 0, -geoconf['ph3tosample'] - geoconf['l2'] - geoconf['l1'] - geoconf['sourcetoph1'] - sampleshift]]).attrs = {'units': 'mm'}

        ### update the detector
        detgroup: h5py.Group = instrumentgroup[[grp for grp in instrumentgroup if
                                                ('NX_class' in instrumentgroup[grp].attrs) and (
                                                        instrumentgroup[grp].attrs['NX_class'] == 'NXdetector')][0]]
        detgroup.create_dataset('distance', data=geoconf['dist_sample_to_det'] - sampleshift).attrs['units'] = 'mm'
        detgroup.create_dataset('distance_errors', data=geoconf['dist_sample_to_det.err']).attrs['units'] = 'mm'
        detgroup.create_dataset('x_pixel_size', data=geoconf['pixelsize']).attrs['units'] = 'mm'
        detgroup.create_dataset('x_pixel_size_errors', data=geoconf['pixelsize.err']).attrs['units'] = 'mm'
        detgroup.create_dataset('y_pixel_size', data=geoconf['pixelsize']).attrs['units'] = 'mm'
        detgroup.create_dataset('y_pixel_size_errors', data=geoconf['pixelsize.err']).attrs['units'] = 'mm'
        detgroup.create_dataset('beam_center_x', data=geoconf['beamposy'] * geoconf['pixelsize']).attrs['units'] = 'mm'
        detgroup.create_dataset('beam_center_y', data=geoconf['beamposx'] * geoconf['pixelsize']).attrs['units'] = 'mm'
        detgroup.create_dataset(
            'beam_center_x_errors', data=(geoconf['beamposx.err'] ** 2 * geoconf['pixelsize'] ** 2 +
                                          geoconf['pixelsize.err'] ** 2 * geoconf['beamposx'] ** 2) ** 0.5
        ).attrs['units'] = 'mm'
        detgroup.create_dataset(
            'beam_center_y_errors', data=(geoconf['beamposy.err'] ** 2 * geoconf['pixelsize'] ** 2 +
                                          geoconf['pixelsize.err'] ** 2 * geoconf['beamposy'] ** 2) ** 0.5
        ).attrs['units'] = 'mm'
        detgroup.create_dataset('polar_angle', 0.0).attrs['units'] = 'rad'
        detgroup.create_dataset('azimuthal_angle', 0.0).attrs['units'] = 'rad'
        detgroup.create_dataset('rotation_angle', 0.0).attrs['units'] = 'rad'
        detgroup.create_dataset('aequatorial_angle', 0.0).attrs['units'] = 'rad'
        transformgrp = detgroup.create_group('transformations')
        transformgrp.attrs['NX_class'] = 'NXtransformations'
        transformgrp.create_dataset('x', data=0).attrs = {'transformation_type': 'translation', 'vector': [1, 0, 0],
                                                          'units': 'mm', 'depends_on': '.'}
        transformgrp.create_dataset('y', data=0).attrs = {'transformation_type': 'translation', 'vector': [1, 0, 0],
                                                          'units': 'mm', 'depends_on': 'x'}
        transformgrp.create_dataset('z', data=geoconf['dist_sample_to_det'] - sampleshift).attrs = {
            'transformation_type': 'translation', 'vector': [1, 0, 0], 'units': 'mm', 'depends_on': 'y'}
        geogrp = detgroup.create_group('geometry')
        geogrp.attrs['NX_class'] = 'NXgeometry'
        geogrp.create_dataset('component_index', data=2)
        translationgrp = geogrp.create_group('translation')
        translationgrp.attrs['NX_class'] = 'NXtranslation'
        translationgrp.create_dataset('distances', [[0, 0, geoconf['dist_sample_to_det']- sampleshift]]).attrs = {'units': 'mm'}

        return instrumentgroup
