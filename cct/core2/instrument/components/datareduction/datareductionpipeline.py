"""Data reduction pipeline for SAXS exposures"""
import logging
import multiprocessing
import re
import traceback
from typing import Optional, Dict, Any
import os

import numpy as np
import scipy.odr

from ....algorithms.geometrycorrections import angledependentabsorption, angledependentairtransmission, solidangle
from ....config import Config
from ....dataclasses import Exposure, Sample

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ProcessingError(Exception):
    pass


class DataReductionPipeLine:
    dark: Optional[Exposure] = None
    emptybeam: Optional[Exposure] = None
    absintref: Optional[Exposure] = None
    commandqueue: Optional[multiprocessing.Queue] = None
    resultqueue: Optional[multiprocessing.Queue] = None
    config: Dict[str, Any]

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @classmethod
    def run_in_background(cls, config: Config, commandqueue: multiprocessing.Queue, resultqueue: multiprocessing.Queue):
        obj = cls(config=config)
        obj.commandqueue = commandqueue
        obj.resultqueue = resultqueue
        while True:
            cmd, arg = commandqueue.get()
            if cmd == 'end':
                obj.debug('Ending')
                break
            elif cmd == 'process':
                try:
                    exposure = obj.process(arg)
                    obj.resultqueue.put_nowait(('result', exposure))
                except ProcessingError as pe:
                    obj.error(pe.args[0])
                except Exception as exc:
                    obj.error(repr(exc) + '\n' + traceback.format_exc())
            elif cmd == 'config':
                obj.config = arg
                obj.debug('Config updated.')
            else:
                obj.error(f'Unknown command: {cmd}')
        obj.debug('Finishing background thread.')
        obj.resultqueue.put_nowait(('finished', None))

    def process(self, exposure: Exposure):
        for operation in [self.sanitize_data, self.normalize_by_monitor, self.subtract_dark_backgrouund,
                          self.normalize_by_transmission, self.subtract_empty_background, self.correct_geometry,
                          self.divide_by_thickness, self.absolute_intensity_scaling]:
            exposure = operation(exposure)
        exposure.save(os.path.join(self.config['path']['directories']['eval2d'], exposure.header.prefix))
        return exposure

    def sanitize_data(self, exposure: Exposure) -> Exposure:
        return exposure

    def normalize_by_monitor(self, exposure: Exposure) -> Exposure:
        exposure.uncertainty = (exposure.header.exposuretime[1] ** 2 * exposure.intensity ** 2 /
                                exposure.header.exposuretime[0] ** 4 + exposure.uncertainty ** 2 /
                                exposure.header.exposuretime[0] ** 2) ** 0.5
        exposure.intensity = exposure.intensity / exposure.header.exposuretime[0]
        self.info(f'FSN #{exposure.header.fsn}: normalized by exposure time.')
        return exposure

    def subtract_dark_background(self, exposure: Exposure) -> Exposure:
        if (exposure.header.sample().category == Sample.Categories.Dark) or (exposure.header.sample().title == 'Dark'):
            # this is a dark current measurement
            self.dark = exposure
            self.dark.header.fsn_dark = self.dark.header.fsn
            self.dark.header.dark_cps = exposure.intensity[exposure.mask].mean(), exposure.uncertainty[exposure.mask]
            self.info(
                f'FSN #{self.dark.header.fsn} is a dark background measurement. '
                f'Level: {self.dark.header.dark_cps[0]:g} \xb1 {self.dark.header.dark_cps[1]:g} cps per pixel '
                f'(overall {self.dark.header.dark_cps[0]:g} cps)'
            )
            raise StopIteration()
        else:
            if self.dark is None:
                raise ProcessingError(
                    'Cannot do dark background subtraction: no dark background measurement encountered yet.')
            exposure.uncertainty = (exposure.uncertainty ** 2 + self.dark.header.dark_cps[1] ** 2) ** 0.5
            exposure.intensity = exposure.intensity - self.dark.header.dark_cps[0]
            exposure.header.fsn_dark = self.dark.header.fsn
            exposure.header.dark_cps = self.dark.header.dark_cps
            self.info(
                f'FSN #{exposure.header.fsn} corrected for dark background signal'
            )
        return exposure

    def normalize_by_transmission(self, exposure: Exposure) -> Exposure:
        if (exposure.header.transmission[0] > 1) or (exposure.header.transmission[0] < 0):
            raise ProcessingError(f'Invalid transmission value: '
                                  f'{exposure.header.transmission[0]:g} \xb1 {exposure.header.transmission[1]:g}.')
        exposure.uncertainty = (exposure.uncertainty ** 2 / exposure.header.transmission[0] ** 2 +
                                exposure.header.transmission[1] ** 2 / exposure.intensity ** 2 /
                                exposure.header.transmission[0] ** 4) ** 0.5
        exposure.intensity = exposure.intensity / exposure.header.transmission[0]
        self.info(
            f'FSN #{exposure.header.fsn} has been normalized by transmission '
            f'{exposure.header.transmission[0]:g} \xb1 {exposure.header.transmission[1]:g}.'
        )

    def subtract_empty_background(self, exposure: Exposure) -> Exposure:
        if (exposure.header.sample().category == Sample.Categories.Empty_beam) or (
                exposure.header.title == 'Empty_Beam'):
            # this is an empty beam measurement.
            self.emptybeam = exposure
            self.info(f'FSN #{exposure.header.fsn} is an empty beam measurement.')
            raise StopIteration()
        elif self.emptybeam is None:
            raise ProcessingError(
                'Empty-beam measurement not encountered yet, cannot correct for instrumental background.')
        else:
            exposure.uncertainty = (exposure.uncertainty ** 2 + self.emptybeam.uncertainty ** 2) ** 0.5
            exposure.intensity = exposure.intensity - self.emptybeam.intensity
            exposure.header.fsn_emptybeam = self.emptybeam.header.fsn
            self.info(f'FSN #{exposure.header.fsn} has been corrected for instrumental background with image '
                     f'#{self.emptybeam.header.fsn}')
        return exposure

    def correct_geometry(self, exposure: Exposure) -> Exposure:
        twotheta = exposure.twotheta()
        sa, dsa = solidangle(twotheta[0], twotheta[1], exposure.header.distance[0], exposure.header.distance[1],
                             exposure.header.pixelsize[0], exposure.header.pixelsize[1])
        asa, dasa = angledependentabsorption(twotheta[0], twotheta[1], exposure.header.transmission[0],
                                             exposure.header.transmission[1])
        aaa, daaa = angledependentairtransmission(twotheta[0], twotheta[1], exposure.header.vacuum,
                                                  exposure.header.distance[0],
                                                  exposure.header.distance[1])  # ToDo: mu_air non-default value
        exposure.uncertainty = (exposure.uncertainty ** 2 * sa ** 2 + exposure.intensity ** 2 * dsa ** 2) ** 0.5
        exposure.intensity = exposure.intensity * sa
        self.info(f'FSN #{exposure.header.fsn} has been corrected for detector flatness (pixel solid angle)')
        exposure.uncertainty = (exposure.uncertainty ** 2 * asa ** 2 + exposure.intensity ** 2 * dasa ** 2) ** 0.5
        exposure.intensity = exposure.intensity * asa
        self.info(f'FSN #{exposure.header.fsn} has been corrected for angle-dependence of sample self-absorption.')
        exposure.uncertainty = (exposure.uncertainty ** 2 * aaa ** 2 + exposure.intensity ** 2 * daaa ** 2) ** 0.5
        exposure.intensity = exposure.intensity * aaa
        self.info(f'FSN #{exposure.header.fsn} has been corrected for angle-dependent absorption of residual air in '
                 f'the vacuum path.')
        return exposure

    def divide_by_thickness(self, exposure: Exposure) -> Exposure:
        exposure.uncertainty = (exposure.uncertainty ** 2 / exposure.header.thickness[0] ** 2 +
                                exposure.header.thickness[1] ** 2 * exposure.intensity ** 4 / exposure.header.thickness[
                                    0] ** 4) ** 0.5
        exposure.intensity = exposure.intensity / exposure.header.thickness[0]
        self.info(f'FSN #{exposure.header.fsn} has been divided by sample thickness of '
                 f'{exposure.header.thickness[0]:g} \xb1 {exposure.header.thickness[1]:g} cm.')
        return exposure

    def absolute_intensity_scaling(self, exposure: Exposure) -> Exposure:
        if exposure.header.sample().category == Sample.Categories.NormalizationSample:
            # find corresponding reference
            if 'calibrants' not in self.config:
                raise ProcessingError('No calibrants found in config.')
            else:
                matching = [cname for cname in self.config['calibrants']
                            if ('datafile' in self.config['calibrants'][cname])
                            and re.match(self.config['calibrants'][cname]['regex'], exposure.header.title)
                            ]
                if not matching:
                    raise ProcessingError('No calibrant information found for sample {}')
                elif len(matching) > 1:
                    raise ProcessingError(
                        f'Sample name {exposure.header.title} is matched by more than one calibrants: '
                        f'{", ".join(matching)}')
                else:
                    datafile = self.config['calibrants'][matching[0]]['datafile']
                    calibdata = np.loadtxt(datafile)
                    rad = exposure.radial_average(calibdata[:, 0]).sanitize()
                    qcalib = rad.q
                    icalib = np.interp(qcalib, calibdata[:, 0], calibdata[:, 1])
                    ecalib = np.interp(qcalib, calibdata[:, 0], calibdata[:, 2])
                    model = scipy.odr.Model(lambda params, x: x * params[0])
                    data = scipy.odr.RealData(rad.intensity, icalib, rad.uncertainty, ecalib)
                    odr = scipy.odr.ODR(data, model, [1.0])
                    result = odr.run()
                    factor = result.beta[0]
                    factor_unc = result.sd_beta[0]
                    chi2_red = result.res_var
                    dof = len(rad) - 1
                    self.absintref = exposure
                    exposure.header.absintchi2 = chi2_red
                    exposure.header.absintdof = dof
                    exposure.header.absintfactor = factor, factor_unc
                    exposure.header.fsn_absintref = exposure.header.fsn
                    exposure.header.absintqmin = qcalib.min()
                    exposure.header.absintqmax = qcalib.max()
                    exposure.header.flux = 1 / factor, abs(factor_unc / factor ** 2)
                    exposure.uncertainty = (exposure.uncertainty ** 2 * exposure.header.absintfactor[
                        0] ** 2 + exposure.intensity ** 2 * exposure.header.absintfactor[1] ** 2) ** 0.5
                    exposure.intensity = exposure.intensity * exposure.header.absintfactor[0]
                    self.info(f'FSN #{exposure.header.fsn} calibrated into absolute units using reference data from '
                             f'{datafile}. Common q-range from {qcalib.min():g} to {qcalib.max():g} 1/nm ({len(qcalib)} '
                             f'points). Reduced chi2: {chi2_red:g} (DoF: {dof}')
                    self.info(f'FSN #{exposure.header.fsn}: estimated beam flux {exposure.header.flux[0]:g} \xb1 '
                             f'{exposure.header.flux[1]} photons*eta/sec')
        elif self.absintref is None:
            raise ProcessingError('No absolute intensity reference measurement encountered up to now, cannot scale into'
                                  'absolute intensity units.')
        else:
            exposure.header.absintdof = self.absintref.header.absintdof
            exposure.header.absintchi2 = self.absintref.header.absintchi2
            exposure.header.absintfactor = self.absintref.header.absintfactor
            exposure.header.fsn_absintref = self.absintref.header.fsn
            exposure.header.absintqmax = self.absintref.header.absintqmax
            exposure.header.absintqmin = self.absintref.header.absintqmin
            exposure.uncertainty = (exposure.uncertainty ** 2 * exposure.header.absintfactor[
                0] ** 2 + exposure.intensity ** 2 * exposure.header.absintfactor[1] ** 2) ** 0.5
            exposure.intensity = exposure.intensity * exposure.header.absintfactor[0]
            self.info(
                f'FSN #{exposure.header.fsn} has been calibrated into absolute units using exposure #{exposure.header.fsn_absintref}. Absolute intensity factor: {exposure.header.absintfactor[0]:g} \xb1 {exposure.header.absintfactor[1]:g}, estimated beam flux {exposure.header.flux[0]:g} \xb1 {exposure.header.flux[1]:g}')

    @staticmethod
    def get_statistics(exposure: Exposure) -> Dict[str, float]:
        return {
            'NaNs': np.isnan(exposure.intensity).sum(),
            'finites': np.isfinite(exposure.intensity).sum(),
            'negatives': (exposure.intensity < 0).sum(),
            'unmaskedNaNs': np.isnan(exposure.intensity[exposure.mask != 0]).sum(),
            'unmaskednegatives': (exposure.intensity[exposure.mask != 0] < 0).sum(),
            'masked': (exposure.mask == 0).sum(),
        }

    def log(self, level:int, message: str):
        if self.resultqueue is not None:
            self.resultqueue.put_nowait(('log', (level, message)))
        logger.log(level, message)

    def error(self, message: str):
        self.log(logging.ERROR, message)

    def debug(self, message: str):
        self.log(logging.DEBUG, message)
        
    def warning(self, message: str):
        self.log(logging.WARNING, message)
        
    def info(self, message: str):
        self.log(logging.INFO, message)
