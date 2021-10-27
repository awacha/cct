import multiprocessing
from typing import List, Tuple

import h5py
import numpy as np
import scipy.odr

from .backgroundprocess import BackgroundProcess, BackgroundProcessError, Results
from ...dataclasses import Exposure, Curve, Header, Sample

class MergingResult(Results):
    pass


class MergingJob(BackgroundProcess):
    samplename: str
    distancekeys: List[str]
    intervals: List[Tuple[float, float]]

    def __init__(self, jobid: int, h5file: str, h5lock: multiprocessing.Lock, stopEvent: multiprocessing.Event,
                 messagequeue: multiprocessing.Queue, samplename: str, distancekeys: List[str],
                 intervals: List[Tuple[float, float]]):
        super().__init__(jobid, h5file, h5lock, stopEvent, messagequeue)
        self.samplename = samplename
        assert len(distancekeys) == len(intervals)
        # sort distance keys in increasing order
        dkiv = [(d, i) for d, i in zip(distancekeys, intervals)]
        self.distancekeys = [d for d, i in sorted(dkiv, key=lambda di: float(di[0]))]
        self.intervals = [i for d, i in sorted(dkiv, key=lambda di: float(di[0]))]

    def main(self):
        self.sendProgress('Loading exposures', len(self.distancekeys), 0)
        exposures: List[Exposure] = []
        for i, distkey in enumerate(self.distancekeys):
            exposures.append(self.h5io.readExposure(f'Samples/{self.samplename}/{distkey}'))
            self.sendProgress('Loading exposures', len(self.distancekeys), i + 1)

        self.sendProgress('Loading curves', len(self.distancekeys), 0)
        curves_reint: List[Curve] = []
        curves_avg: List[Curve] = []
        for i, distkey in enumerate(self.distancekeys):
            curves_reint.append(self.h5io.readCurve(f'Samples/{self.samplename}/{distkey}/curve_reintegrated'))
            curves_avg.append(self.h5io.readCurve(f'Samples/{self.samplename}/{distkey}/curve_averaged'))
            self.sendProgress('Loading curves', len(self.distancekeys), i + 1)

        self.sendProgress('Determining scaling factors', len(self.distancekeys) - 1, 0)
        factors = []
        separators = []
        for i in range(len(self.distancekeys) - 1):
            commonqrange = max(self.intervals[i][0], self.intervals[i + 1][0]), \
                           min(self.intervals[i][1], self.intervals[i + 1][1])
            if commonqrange[0] >= commonqrange[1]:
                raise BackgroundProcessError('Common q range is null')
            q = np.linspace(*commonqrange, 10)
            radshort = exposures[i].radial_average(q)
            radlong = exposures[i + 1].radial_average(q)
            idx = np.logical_and(radshort.isvalid(), radlong.isvalid())
            radshort = radshort[idx]
            radlong = radlong[idx]
            if (len(radshort) < 2) or (len(radlong) < 2):
                raise BackgroundProcessError('Not enough valid points for merging')
            odrresults = scipy.odr.ODR(
                scipy.odr.RealData(radlong.intensity, radshort.intensity, radlong.uncertainty, radshort.uncertainty),
                scipy.odr.Model(lambda beta, x: beta[0] * x),
                [1.0]).run()
            if odrresults.info > 4:
                raise BackgroundProcessError(f'ODR fitting error: {odrresults.stopreason}')
            factors.append((odrresults.beta[0], odrresults.sd_beta[0]))
            separators.append(radlong.q[np.argmin(np.abs(radlong.intensity * odrresults.beta[0] - radshort.intensity))])
            self.sendProgress('Determining scaling factors', len(self.distancekeys) - 1, i + 1)

        self.sendProgress('Scaling curves', len(self.distancekeys), 1)
        for icurve in range(1, len(self.distancekeys)):
            for ifactor in range(icurve):
                curves_reint[icurve] = curves_reint[icurve] * factors[ifactor]
                curves_avg[icurve] = curves_avg[icurve] * factors[ifactor]
            self.sendProgress('Scaling curves', len(self.distancekeys), icurve + 1)

        self.sendProgress('Merging')
        merged_reint = curves_reint[0]
        merged_avg = curves_avg[0]
        for icurve in range(1, len(self.distancekeys)):
            merged_reint = merged_reint.sanitize().trim(separators[icurve - 1], np.inf)
            merged_avg = merged_avg.sanitize().trim(separators[icurve - 1], np.inf)
            c_reint = curves_reint[icurve].sanitize().trim(0, separators[icurve - 1])
            c_avg = curves_avg[icurve].sanitize().trim(0, separators[icurve - 1])
            merged_reint = Curve.fromArray(
                np.vstack((c_reint, merged_reint))
            )
            merged_avg = Curve.fromArray(
                np.vstack((c_avg, merged_avg))
            )
        header = Header(datadict={})
        header.title = exposures[0].header.title
        header.sample_category = Sample.Categories.Merged.value
        header.exposuretime = sum([e.header.exposuretime[0] for e in exposures]), sum(
            [e.header.exposuretime[1] ** 2 for e in exposures]) ** 0.5
        header.exposurecount = sum([e.header.exposurecount for e in exposures])
        header.enddate = max([e.header.enddate for e in exposures])
        header.startdate = min([e.header.startdate for e in exposures])
        header.date = max([e.header.date for e in exposures])

        self.sendProgress('Writing HDF5 file')
        with self.h5io.writer(f'Samples/{self.samplename}/merged') as grp:
            self.h5io.writeCurve(merged_reint, grp, 'curve_reintegrated')
            self.h5io.writeCurve(merged_avg, grp, 'curve_averaged')
            try:
                del grp['curve']
            except KeyError:
                pass
            grp['curve'] = h5py.SoftLink('curve_averaged')
            self.h5io.writeHeader(header, grp)
            try:
                del grp['scaled_curves']
            except KeyError:
                pass
            scgrp = grp.require_group('scaled_curves')
            for distkey, curveavg, curvereint, interval, factor, sephighq, seplowq in zip(
                    self.distancekeys, curves_avg, curves_reint, self.intervals, [(1.0, 0.0)] + factors,
                    [np.nan] + separators, separators + [np.nan]):
                g = scgrp.create_group(distkey)
                g.create_dataset('averaged', data=curveavg)
                g.create_dataset('reintegrated', data=curvereint)
                g['curve'] = h5py.SoftLink('averaged')
                g.attrs['qmin'] = interval[0]
                g.attrs['qmax'] = interval[1]
                g.attrs['factor'] = factor[0]
                g.attrs['factor.unc'] = factor[1]
                g.attrs['separator_lowq'] = seplowq
                g.attrs['separator_highq'] = sephighq
        return MergingResult(jobid=self.jobid)