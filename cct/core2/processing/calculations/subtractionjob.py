import enum
import logging
import multiprocessing
import os
from typing import Optional, Tuple, List

import h5py
import numpy as np
import scipy.odr
import scipy.optimize

from .backgroundprocess import BackgroundProcess, Results, BackgroundProcessError
from ...dataclasses import Exposure, Curve
from ...dataclasses.exposure import QRangeMethod
from ...dataclasses.sample import Sample
from ...algorithms.matrixaverager import ErrorPropagationMethod

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SubtractionError(BackgroundProcessError):
    pass


class SubtractionResult(Results):
    distancekeys: List[str]
    subtractedname: str

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.distancekeys = []
        self.subtractedname = ""


class SubtractionScalingMode(enum.Enum):
    Unscaled = 'None'  # no scaling, no parameter
    Constant = 'Constant'  # multiply the background with a fixed constant. One parameter: the constant
    Interval = 'Interval'  # Scale the sample and the background together on the given q-range (qmin, qmax, Nq)
    PowerLaw = 'Power-law'  # Scale the sample and the background for best power-law fit on the q-range (qmin, qmax, Nq)


class SubtractionJob(BackgroundProcess):
    samplename: Optional[str]
    backgroundname: Optional[str]
    subtractedname: str
    scalingmode: SubtractionScalingMode
    factor: Tuple[float, float]
    interval: Tuple[float, float, int]
    result: SubtractionResult
    qrangemethod: QRangeMethod
    qcount: int
    errorprop: ErrorPropagationMethod
    qerrorprop: ErrorPropagationMethod

    def __init__(self, jobid: int, h5file: str, h5lock: multiprocessing.Lock, stopEvent: multiprocessing.Event,
                 messagequeue: multiprocessing.Queue, samplename: Optional[str], backgroundname: Optional[str],
                 scalingmode: SubtractionScalingMode, factor: Tuple[float, float], interval: Tuple[float, float, int],
                 subtractedname: Optional[str], qrangemethod: QRangeMethod, qcount: int,
                 errorprop: ErrorPropagationMethod, qerrorprop: ErrorPropagationMethod):
        super().__init__(jobid, h5file, h5lock, stopEvent, messagequeue)
        self.samplename = samplename
        self.backgroundname = backgroundname
        self.scalingmode = scalingmode
        self.factor = factor
        self.interval = interval
        self.qrangemethod = qrangemethod
        self.qcount = qcount
        self.errorprop = errorprop
        self.qerrorprop = qerrorprop
        self.result = SubtractionResult(jobid=self.jobid)
        if subtractedname is None:
            self.result.subtractedname = f'{samplename}-{backgroundname if backgroundname is not None else "constant"}'
        else:
            self.result.subtractedname = subtractedname

    def subtractconstant(self, distkey: str) -> Tuple[Exposure, Curve, Curve]:
        exposure = self.h5io.readExposure(f'Samples/{self.samplename}/{distkey}')
        if self.scalingmode == SubtractionScalingMode.PowerLaw:
            # fit a power-law
            curve = exposure.radial_average(
                np.linspace(self.interval[0], self.interval[1], self.interval[2])).sanitize()
            odrdata = scipy.odr.RealData(curve.q, curve.intensity, curve.quncertainty, curve.uncertainty)
            odrmodel = scipy.odr.Model(lambda params, x: params[0] * x ** params[1] + params[2])
            odrresult = scipy.odr.ODR(odrdata, odrmodel, [1, -4, curve.intensity[-10:].mean()])
            bglevel = odrresult.beta[2], odrresult.sd_beta[2]
        elif self.scalingmode == SubtractionScalingMode.Constant:
            bglevel = self.factor
        elif self.scalingmode == SubtractionScalingMode.Interval:
            # fit a constant
            curve = exposure.radial_average(
                np.linspace(self.interval[0], self.interval[1], self.interval[2])).sanitize()
            odrdata = scipy.odr.RealData(curve.q, curve.intensity, curve.quncertainty, curve.uncertainty)
            odrmodel = scipy.odr.Model(lambda params, x: params[0])
            odrresult = scipy.odr.ODR(odrdata, odrmodel, [curve.intensity.mean()])
            bglevel = odrresult.beta[0], odrresult.sd_beta[0]
        elif self.scalingmode == SubtractionScalingMode.Unscaled:
            bglevel = (0.0, 0.0)
        ex = Exposure(exposure.intensity - bglevel[0], exposure.header,
                      (exposure.uncertainty ** 2 + bglevel[1] ** 2) ** 0.5, exposure.mask)
        curve_avg = self.h5io.readCurve(f'Samples/{self.samplename}/{distkey}/curve_averaged')
        return ex, ex.radial_average(
            qbincenters=(self.qrangemethod, self.qcount), errorprop=self.errorprop, qerrorprop=self.qerrorprop), \
               curve_avg - bglevel

    def subtractbackground(self, distkey: str) -> Tuple[Exposure, Curve, Curve]:
        exposure = self.h5io.readExposure(f'Samples/{self.samplename}/{distkey}')
        bg = self.h5io.readExposure(f'Samples/{self.backgroundname}/{distkey}')
        if self.scalingmode == SubtractionScalingMode.Unscaled:
            factor = (1.0, 0.0)
        elif self.scalingmode == SubtractionScalingMode.Constant:
            factor = self.factor
        elif self.scalingmode in [SubtractionScalingMode.Interval, SubtractionScalingMode.PowerLaw]:
            q = np.linspace(self.interval[0], self.interval[1], self.interval[2])
            rad = exposure.radial_average(q)
            bgrad = bg.radial_average(q)
            idx = np.logical_and(rad.isvalid(), bgrad.isvalid())
            if idx.sum() < 2:
                raise SubtractionError('Not enough valid points between sample and background')
            rad = rad[idx]
            bgrad = bgrad[idx]
            if self.scalingmode == SubtractionScalingMode.Interval:
                odrdata = scipy.odr.RealData(bgrad.intensity, rad.intensity, bgrad.uncertainty, rad.uncertainty)
                odrmodel = scipy.odr.Model(lambda params, x: x * params[0])
                odrresult = scipy.odr.ODR(odrdata, odrmodel, [1.0]).run()
                factor = odrresult.beta[0], odrresult.sd_beta[0]
            else:
                odrmodel = scipy.odr.Model(lambda params, x: params[0] * x ** params[1])

                def powerlaw_goodnessoffit(paramarray):
                    odrdata = scipy.odr.RealData(rad.q, rad.intensity - bgrad.intensity * paramarray[0],
                                                 rad.quncertainty, (rad.uncertainty ** 2 + paramarray[
                            0] ** 2 * bgrad.uncertainty ** 2) ** 0.5)
                    return scipy.odr.ODR(odrdata, odrmodel, [1.0, -4.0]).run().res_var

                result = scipy.optimize.minimize(
                    powerlaw_goodnessoffit,
                    np.array([1.0]),
                    method='L-BFGS-B',
                    options={'ftol': 1e7 * np.finfo(float).eps,
                             'eps': 0.0001,  # finite step size for approximating the jacobian
                             },
                )
                ftol = 1e7 * np.finfo(float).eps  # L-BFGS-B default factr value is 1e7
                covar = max(1, np.abs(result.fun)) * ftol * result.hess_inv.todense()
                factor = result.x[0], covar[0, 0] ** 0.5
        else:
            assert False
        ex = Exposure(exposure.intensity - factor[0] * bg.intensity, exposure.header, (
                exposure.uncertainty ** 2 + factor[0] ** 2 * bg.uncertainty ** 2 + bg.intensity ** 2 * factor[
            1] ** 2) ** 0.5)
        if exposure.header.maskname != bg.header.maskname:
            ex.header.maskname = f'{os.path.split(exposure.header.maskname)[-1]}-{os.path.split(bg.header.maskname)[-1]}'
            ex.mask = np.logical_and(exposure.mask, bg.mask)
        samplecurve_avg = self.h5io.readCurve(f'Samples/{self.samplename}/{distkey}/curve_averaged')
        bgcurve_avg = self.h5io.readCurve(f'Samples/{self.backgroundname}/{distkey}/curve_averaged')
        return ex, ex.radial_average(
            qbincenters=(self.qrangemethod, self.qcount), errorprop=self.errorprop, qerrorprop=self.qerrorprop), \
               samplecurve_avg - factor * bgcurve_avg

    def main(self):
        if self.samplename is None:
            # do nothing
            return
        items = self.h5io.items()
        distkeys_sample = [d for s, d in items if s == self.samplename]
        distkeys_background = [d for s, d in items if s == self.backgroundname]
        if not distkeys_sample:
            self.sendError(f'Sample {self.samplename} does not exist.')
            return
        for dk in distkeys_sample:
            if (dk not in distkeys_background) and (self.backgroundname is not None):
                self.sendWarning(f'No measurement exists for background {self.backgroundname} at {dk} mm.')
                continue
            elif self.backgroundname is None:
                # subtract a constant
                sub, curve_reint, curve_avg = self.subtractconstant(dk)
            else:
                # subtract the background
                sub, curve_reint, curve_avg = self.subtractbackground(dk)
            with self.h5io.writer('Samples') as grp:
                sub.header.title = self.result.subtractedname
                subgrp = grp.require_group(sub.header.title)
                sub.header.sample_category = Sample.Categories.Subtracted.value
                dkgroup = subgrp.require_group(dk)
                self.h5io.writeExposure(sub, dkgroup)

                self.h5io.writeCurve(curve_reint, dkgroup, 'curve_reintegrated')
                self.h5io.writeCurve(curve_avg, dkgroup, 'curve_averaged')
                try:
                    del dkgroup['curve']
                except KeyError:
                    pass
                dkgroup['curve'] = h5py.SoftLink('curve_averaged')
            self.result.distancekeys.append(dk)
