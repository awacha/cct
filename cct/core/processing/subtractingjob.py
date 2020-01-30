import multiprocessing
import time
import traceback
from typing import Any, Union, Tuple, Optional

import h5py
import numpy as np
import scipy.odr
import scipy.optimize
from sastool.classes2 import Curve
from sastool.io.credo_cpth5 import Exposure
from sastool.misc.errorvalue import ErrorValue

from .backgroundprocedure import BackgroundProcedure, Results, ProcessingError


class SubtractionResults(Results):
    pass


class SubtractingJob(BackgroundProcedure):
    samplename: str
    backgroundname: str
    subtractmode: str
    subtractparameters: Union[None, float, Tuple[float, float, int], Tuple[float, float, int, Optional[float]]]

    def __init__(
            self, jobid: Any, h5writerLock: multiprocessing.Lock, killswitch: multiprocessing.Event,
            resultsqueue: multiprocessing.Queue, h5file: str, samplename: str, backgroundname: str,
            subtractmode: str,
            subtractparameters: Union[None, float, Tuple[float, float, int], Tuple[float, float, int, Optional[float]]]
    ):
        super().__init__(jobid, h5writerLock, killswitch, resultsqueue, h5file)
        self.samplename = samplename
        self.backgroundname = backgroundname
        self.subtractmode = subtractmode
        self.subtractparameters = subtractparameters
        self.result = Results()

    def _execute(self) -> None:
        t0 = time.monotonic()
        subname = self.samplename + '-' + self.backgroundname
        try:
            self.sendProgress('Waiting for HDF5 lock')
            with self.h5WriterLock:
                self.sendProgress('Loading exposures')
                with h5py.File(self.h5file, 'r+') as f:
                    #                    f.swmr_mode = True
                    sampledistancekeys = list(f['Samples'][self.samplename].keys())
                    backgrounddistancekeys = list(f['Samples'][self.backgroundname].keys())
                    for dist in sorted(sampledistancekeys):
                        if dist not in backgrounddistancekeys:
                            # ToDo: warning
                            continue
                        # load the exposures from the h5 file
                        exsample = Exposure.new_from_group(f['Samples'][self.samplename][dist])
                        exbg = Exposure.new_from_group(f['Samples'][self.backgroundname][dist])
                        # subtract
                        if self.subtractmode == 'None':
                            factor = 1.0
                        elif self.subtractmode == 'Constant':
                            factor = float(self.subtractparameters)
                        elif self.subtractmode == 'Interval':
                            # scale the background to match the sample over the selected interval
                            q = np.linspace(min(self.subtractparameters[0]), max(self.subtractparameters[1]),
                                            self.subtractparameters[2])
                            csample = exsample.radial_average(qrange=q)
                            cbg = exbg.radial_average(qrange=q)
                            valid = np.logical_and(
                                np.logical_and(
                                    np.logical_and(np.isfinite(csample.Intensity), np.isfinite(csample.Error)),
                                    np.logical_and(np.isfinite(csample.q), np.isfinite(csample.qError))),
                                np.logical_and(
                                    np.logical_and(np.isfinite(cbg.Intensity), np.isfinite(cbg.Error)),
                                    np.logical_and(np.isfinite(cbg.q), np.isfinite(cbg.qError)))
                            )
                            if valid.sum() < 3:
                                raise ProcessingError(
                                    'Not enough valid points in radial averages at distance {}'.format(
                                        dist))

                            linmodel = scipy.odr.Model(lambda params, x: params[0] * x)
                            data = scipy.odr.RealData(x=cbg.Intensity[valid], y=csample.Intensity[valid],
                                                      sx=cbg.Error[valid], sy=csample.Error[valid])
                            odr = scipy.odr.ODR(data, linmodel, beta0=[1.0])
                            odroutput = odr.run()
                            if odroutput.info >= 4:
                                raise ProcessingError(
                                    'Cannot scale background to sample (distance {}).'.format(dist))
                            factor = ErrorValue(odroutput.beta[0], odroutput.sd_beta[0])
                        elif self.subtractmode == 'Power-law':
                            # fit a power-law curve to the subtracted data on the selected interval: the factor
                            # producing the best fit wins.
                            q = np.linspace(min(self.subtractparameters[0]), max(self.subtractparameters[1]),
                                            self.subtractparameters[2])
                            csample = exsample.radial_average(qrange=q)
                            cbg = exbg.radial_average(qrange=q)
                            valid = np.logical_and(
                                np.logical_and(
                                    np.logical_and(np.isfinite(csample.Intensity), np.isfinite(csample.Error)),
                                    np.logical_and(np.isfinite(csample.q), np.isfinite(csample.qError))),
                                np.logical_and(
                                    np.logical_and(np.isfinite(cbg.Intensity), np.isfinite(cbg.Error)),
                                    np.logical_and(np.isfinite(cbg.q), np.isfinite(cbg.qError)))
                            )
                            if valid.sum() < 3:
                                raise ProcessingError(
                                    'Not enough valid points in radial averages at distance {}'.format(dist))

                            def minimizeTargetFunction(factor: float, csample: Curve, cbg: Curve, fixalpha=None):
                                subcurve = csample - factor * cbg
                                model = scipy.odr.Model(lambda parameters, x: parameters[0] * x ** parameters[1])
                                data = scipy.odr.RealData(x=subcurve.q, y=subcurve.Intensity, sx=subcurve.qError,
                                                          sy=subcurve.Error)
                                alpha0 = fixalpha if fixalpha is not None else -4
                                odr = scipy.odr.ODR(data=data, model=model, beta0=[1, alpha0], ifixb=[1, 0])
                                result1 = odr.run()
                                if result1.info >= 4:
                                    raise ProcessingError(
                                        'Error while power-law fitting (stage 1): {}'.format(result1.stopreason))
                                if fixalpha is None:
                                    # fit the exponent as well
                                    odr = scipy.odr.ODR(data=data, model=model, beta0=[result1.beta[0], alpha0],
                                                        ifixb=[1, 1])
                                    result2 = odr.run()
                                    if result2.info >= 4:
                                        raise ProcessingError(
                                            'Error while power-law fitting (stage 2): {}'.format(result1.stopreason))
                                    return result2.sum_square
                                else:
                                    return result1.sum_square

                            optres = scipy.optimize.minimize_scalar(minimizeTargetFunction,
                                                                    args=(csample, cbg, self.subtractparameters[3]))
                            if not optres.success:
                                raise ProcessingError('Could not optimize factor with power-law fitting')
                            factor = optres.x
                        else:
                            raise ProcessingError('Invalid background subtraction method: {}'.format(self.subtractmode))
                        sub = exsample - factor * exbg
                        # the mask is a logical AND of the two masks, since 1 is valid, 0 is invalid
                        mask = np.logical_and(exsample.mask, exbg.mask)
                        f['Samples'].require_group(subname)
                        try:
                            # remove the target group if it already exists: start with a clean slate
                            del f['Samples'][subname][dist]
                        except KeyError:
                            pass
                        g = f['Samples'][subname].require_group(dist)
                        assert isinstance(g, h5py.Group)
                        for attr in f['Samples'][self.samplename][dist].attrs:
                            f['Samples'][subname][dist].attrs[attr] = f['Samples'][self.samplename][dist].attrs[attr]
                        f['Samples'][subname][dist].attrs['title'] = subname
                        f['Samples'][subname][dist].attrs['sample_category'] = 'subtracted'
                        # write the image and the mask
                        g.create_dataset('image', sub.shape, data=sub.intensity, compression=self.h5compression)
                        g.create_dataset('image_uncertainty', sub.shape, data=sub.error, compression=self.h5compression)
                        g.create_dataset('mask', mask.shape, data=mask, compression=self.h5compression)
                        # subtract the curves
                        curvesample = np.array(f['Samples'][self.samplename][dist]['curve_averaged'])
                        curvebg = np.array(f['Samples'][self.backgroundname][dist]['curve_averaged'])
                        if curvesample.shape != curvebg.shape:
                            raise ProcessingError(
                                'Shape mismatch between {} and {} (distance {})'.format(self.samplename,
                                                                                        self.backgroundname, dist))
                        qmaxmismatch = np.nanmax(np.abs(curvesample[:, 0] - curvebg[:, 0]))
                        if qmaxmismatch > 0.001:
                            raise ProcessingError(
                                'Q-range mismatch between {} and {} (distance {}; max. mismatch: {})'.format(
                                    self.samplename, self.backgroundname, dist, qmaxmismatch))
                        g.create_dataset('curve_averaged', curvesample.shape, compression=self.h5compression,
                                         dtype=curvesample.dtype)
                        g['curve_averaged'][:, 0] = 0.5 * (curvesample[:, 0] + curvebg[:, 0])
                        g['curve_averaged'][:, 1] = curvesample[:, 1] - curvebg[:, 1]
                        g['curve_averaged'][:, 2] = (curvesample[:, 2] ** 2 + curvebg[:, 2] ** 2) ** 0.5
                        g['curve_averaged'][:, 3] = 0.5 * (curvesample[:, 3] ** 2 + curvebg[:, 3] ** 2) ** 0.5
                        # make a radial average as well.
                        radavg = sub.radial_average(qrange=0.5 * (curvesample[:, 0] + curvebg[:, 0]))
                        g.create_dataset('curve_reintegrated', curvesample.shape, dtype=curvesample.dtype)
                        g['curve_reintegrated'][:, 0] = radavg.q
                        g['curve_reintegrated'][:, 1] = radavg.Intensity
                        g['curve_reintegrated'][:, 2] = radavg.Error
                        g['curve_reintegrated'][:, 3] = radavg.qError
                        g['curve'] = h5py.SoftLink('curve_averaged')
            self.result.success = True
            self.result.time_total = time.monotonic() - t0
        except Exception as exc:
            self.sendError(str(exc), traceback=traceback.format_exc())
            self.result.success = False
            self.result.time_total = time.monotonic() - t0
