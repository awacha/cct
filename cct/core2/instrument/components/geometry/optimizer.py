import itertools
import logging
import queue
import time
from multiprocessing import Process, Queue, Event
from typing import Sequence, Optional, Dict, Tuple, Any

import numpy as np
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from ....config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def yieldspacers(spacers: Sequence[float]):
    uniquespacers = sorted(set(spacers))
    spacercounts = [spacers.count(s) for s in uniquespacers]
    # for L1:
    for countsforl1 in itertools.product(*[range(c + 1) for c in spacercounts]):
        assert len(countsforl1) == len(spacercounts)
        for countsforl2 in itertools.product(*[range(c + 1 - cl1) for c, cl1 in zip(spacercounts, countsforl1)]):
            assert all([c1 + c2 <= tot for c1, c2, tot in zip(countsforl1, countsforl2, spacercounts)])
            yield countsforl1, countsforl2, uniquespacers


def yieldflightpipes(flightpipes: Sequence[float]):
    uniquepipes = sorted(set(flightpipes))
    pipecounts = [flightpipes.count(s) for s in uniquepipes]
    # for L1:
    for counts in itertools.product(*[range(0, c + 1) for c in pipecounts]):
        if sum(counts) > 0:  # do not allow 0 flight pipes
            yield counts, uniquepipes


def _worker(stopevent: Event, outqueue: Queue, geoconfig: Dict, maxsamplediameter: Tuple[float, float], qmin: Tuple[float, float], l1min: float = 0.0,
            l2min: float = 0.0,
            lmax: float = 0.0):
    isoKFringwidth = geoconfig['isoKFspacer']
    l1base = geoconfig['l1base']
    l2base = geoconfig['l2base']
    ph3toflightpipes = geoconfig['ph3toflightpipes']
    lastflightpipetodetector = geoconfig['lastflightpipetodetector']
    ph3tosample = geoconfig['ph3tosample']
    beamstoptodetector = geoconfig['beamstoptodetector']
    wavelength = geoconfig['wavelength']
    for ph1, ph2, ph3, bs, (l1_elementcount, l2_elementcount, spacers), (
            flightpipe_elementcount, flightpipes) in itertools.product(
        geoconfig['choices']['pinholes'][1],
        geoconfig['choices']['pinholes'][2],
        geoconfig['choices']['pinholes'][3],
        geoconfig['choices']['beamstops'],
        yieldspacers(geoconfig['choices']['spacers']),
        yieldflightpipes(geoconfig['choices']['flightpipes'])
    ):
        if stopevent.is_set():
            break
        l1 = sum([ec * el for ec, el in zip(l1_elementcount, spacers)]) + l1base + sum(
            l1_elementcount) * isoKFringwidth
        l2 = sum([ec * el for ec, el in zip(l2_elementcount, spacers)]) + l2base + sum(
            l2_elementcount) * isoKFringwidth
        ph3todetector = ph3toflightpipes + sum(
            [ec * el for ec, el in zip(flightpipe_elementcount, flightpipes)]) + lastflightpipetodetector
        sd = ph3todetector - ph3tosample

        if l1 < l1min:
            continue
        if l2 < l2min:
            continue
        if l1 + l2 + ph3todetector > lmax:
            continue

        # 1) check if ph3 cuts into the main beam
        if (dbeam_at_ph3:=(ph1 + ph2) * (l1 + l2) / l1 - ph1) >= ph3:
            # yes, it does
            continue
        # 2) check if the direct beam is larger than the beamstop
        if (dbeam_at_bs:=(ph1 + ph2) * (l1 + l2 + ph3todetector - beamstoptodetector) / l1 - ph1) >= bs * 1000:
            # yes, it is
            continue
        # 3) check if there is parasitic scattering around the beamstop
        if (dparasitic_at_bs:=(ph2 + ph3) * (l2 + ph3todetector - beamstoptodetector) / l2 - ph2) >= bs * 1000:
            # yes, there is
            continue
        # 4) check if the beam is not too large at the sample
        dbeamatsample = ((ph1 + ph2) * (l1 + l2 + ph3tosample) / l1 - ph1) * 1e-3
        #            logger.debug(f'{dbeamatsample=}')
        if (dbeamatsample >= maxsamplediameter[1]) or (dbeamatsample <= maxsamplediameter[0]):
            # yes, it is too large (or too small)
            continue
        # 5) check if qmin is reached
        # at this point we do not have parasitic scattering, nor direct beam hitting the detector. Therefore qmin
        # is only limited by the shadow of the beamstop on the detector.
        rmin = ((dbeamatsample + bs) * sd / (sd - beamstoptodetector) - dbeamatsample) * 0.5
        # logger.debug(f'{rmin=}, {sd=}, {wavelength=}')
        thisqmin = 4 * np.pi * np.sin(0.5 * np.arctan(rmin / sd)) / wavelength
        if (thisqmin <= qmin[0]) or (thisqmin >= qmin[1]):
            # not reached or too fine
            continue
        # otherwise we have found a good solution. Maybe not the best one though
        outqueue.put({
            'l1_elements': list(itertools.chain(*[itertools.repeat(el, ec) for el, ec in zip(spacers, l1_elementcount)])),
            'l2_elements': list(itertools.chain(*[itertools.repeat(el, ec) for el, ec in zip(spacers, l2_elementcount)])),
            'pinhole_1': ph1,
            'pinhole_2': ph2,
            'pinhole_3': ph3,
            'flightpipes': list(itertools.chain(
                *[itertools.repeat(fp, fpc) for fp, fpc in zip(flightpipes, flightpipe_elementcount)])),
            'beamstop': bs,
            'l1': l1,
            'l2': l2,
            'ph3todetector': ph3todetector,
            'sd': sd,
            'dbeam_at_ph3': dbeam_at_ph3/1000.,  # um -> mm
            'dbeam_at_bs': dbeam_at_bs/1000.,  # um -> mm
            'dparasitic_at_bs': dparasitic_at_bs/1000.,  # um -> mm
            'dbeam_at_sample': dbeamatsample,  # already in mm
            'qmin': thisqmin,  # 1/[wavelength unit]
            'intensity': ph1**2*ph2**2/l1**2,  # um^4/mm^2
        })


class GeometryOptimizer(QtCore.QObject):
    geoconfig: Dict[str, Any] 
    process: Optional[Process] = None
    queue: Optional[Queue] = None
    timerid: Optional[int] = None
    starttime: Optional[float] = None
    geometryFound = Signal(object)
    finished = Signal(float,  # elapsed time

                                 )

    def __init__(self, config: Config):
        super().__init__()
        self.geoconfig = config['geometry'].asdict()
        self.queue = None
        self.process = None
        self.timerid = None
        self.stopevent = Event()

    def start(self, maxsamplediameter: Tuple[float, float], qmin: Tuple[float, float], l1min: float, l2min: float, lmax: float):
        if self.process is not None or self.queue is not None:
            raise RuntimeError('Cannot start processing: already running')
        self.queue = Queue()
        self.process = Process(target=_worker, name='optimization worker',
                               args=(
                               self.stopevent, self.queue, self.geoconfig, maxsamplediameter, qmin, l1min, l2min,
                               lmax))
        self.stopevent.clear()
        self.process.start()
        self.timerid = self.startTimer(10, QtCore.Qt.PreciseTimer)
        self.starttime = time.monotonic()

    def timerEvent(self, timerevent: QtCore.QTimerEvent) -> None:
        while True:
            try:
                optresult = self.queue.get_nowait()
            except queue.Empty:
                break
            self.geometryFound.emit(optresult)
        if (not self.process.is_alive()) and (self.queue.empty()):
            self.process.join()
            self.killTimer(self.timerid)
            self.timerid = None
            self.process = None
            self.queue = None
            self.finished.emit(time.monotonic() - self.starttime)
            self.starttime = None
            self.stopevent.clear()
