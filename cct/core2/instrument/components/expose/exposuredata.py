# coding: utf-8
"""ExposureTask: a class representing an ongoing exposure with the detector"""
import datetime
import enum
import logging
import os
import pickle
import time
from typing import Optional

import h5py
import numpy as np
from PySide6 import QtCore
from PySide6.QtCore import Signal

from ....dataclasses.exposure import Exposure
from ....dataclasses.header import Header
from ....dataclasses.sample import Sample
from ....devices.detector.pilatus.frontend import PilatusDetector
from ....devices.device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ExposureState(enum.Enum):
    Initializing = enum.auto()  # the detector is being initialized by the Exposer
    Pending = enum.auto()  # another image is being collected, wait for our turn
    Running = enum.auto()  # this image is being collected
    WaitingForImage = enum.auto()  # collection done, trying to load the image file from disk
    Finished = enum.auto()  # finished successfully, image have been loaded
    TimedOut = enum.auto()  # finished unsuccessfully, image file could not be found
    Stopped = enum.auto()  # finished, stopped on external request


class ExposureTask(QtCore.QObject):
    """Representation of a scheduled/running exposure

    The life of an exposure is the following, reflected by the `status` variable:
        - the exposure task is created in the "Initializing" state. This precedes the issuing of the start exposure
          command to the detector.
        - After the detector has acknowledged the exposure command, the exposure task goes into the "Running" state. If
          multiple exposures are requested, the first one will be "Running", the subsequent ones are "Pending".
        - "Pending" tasks become "Running" when all previous exposures have been done and the waiting times inbetween
          them are also elapsed. In this sense, the i-th exposure (i=1..) spends `exptime`*(i-1) + `expdelay`*(i-1) in
          the "Pending" state and finishes after i*`exptime` + (i-1)*`expdelay`.
        - When the exposure time has elapsed (on the clock of the computer, i.e. no interaction is needed with the
          detector hardware), the state turns to "WaitingForImage". In this state the program tries periodically to load
          the image file from the disk.
        - If the image file is found in the preferred timeout interval, the status gets to "Finished". This is success.
        - If the image file is not found even after the timeout has been elapsed, the status will be "TimedOut".

    The following signals are defined:

        - `exposurestarted`: emitted at the actual start of the exposure (estimated using the clock)
        - `exposureended`: emitted at the actual end of the exposure
        - `finished`: emitted when the image has been loaded / the image loading timeout has been spent

    :ivar prefix: file name prefix, e.g. 'crd', 'tst', 'scn', 'tra' etc.
    :type prefix: str
    :ivar fsn: file sequence number of this exposure
    :type fsn: int
    :ivar command_ack_time: the timestamp (a la time.monotonic()) when the detector acknowledged the start command
    :type command_ack_time: float
    :ivar exptime: time of a single exposure (sec)
    :type exptime: float
    :ivar expdelay: delay between two subsequent exposures in a multi-exposure series (sec)
    :type expdelay: float
    :ivar imagetimeout: time before giving up on reading a finished image (sec)
    :type imagetimeout: float
    :ivar index: the 0-based index of this image in a multi-frame exposure
    :type index: int
    :ivar maskoverride: use a different mask
    :type maskoverride: str or None
    """
    # all times are from time.monotonic()
    prefix: str
    fsn: int
    firstfsn: int
    command_ack_time: Optional[float] = None  # when the detector backend process replied to the expose command
    exptime: float  # exposure time
    expdelay: float  # delay between exposures
    imagetimeout: float = 2.0  # timeout for waiting for the image.
    index: int  # 0-based index of this image in a multiple exposure sequence
    maskoverride: Optional[str] = None
    status: ExposureState = ExposureState.Initializing
    finished = Signal(bool, object)
    exposurestarted = Signal()
    exposureended = Signal()
    pendingtimer: Optional[int] = None
    runningtimer: Optional[int] = None
    waitforimagetimer: Optional[int] = None
    imageloadtimer: Optional[int] = None
    imageloadperiod: float = 0.1
    instrument: "Instrument"
    detector: PilatusDetector
    h5filename: Optional[str] = None

    def __init__(self, instrument: "Instrument", detector: PilatusDetector, prefix: str, fsn: int, index: int,
                 exptime: float, expdelay: float, maskoverride: Optional[str] = None, writenexus: bool = False):
        super().__init__()
        logger.debug(f'Initializing an exposure task for {prefix}/{fsn}')
        self.prefix = prefix
        self.fsn = fsn
        self.index = index
        self.exptime = exptime
        self.expdelay = expdelay
        self.exptime = exptime
        if isinstance(maskoverride, str) and not maskoverride.strip():
            maskoverride = None
        self.maskoverride = maskoverride
        self.status = ExposureState.Initializing
        self.instrument = instrument
        self.detector = detector
        self.writenexus = writenexus
        if writenexus:
            targetdir = os.path.join(self.instrument.io.getSubDir('nexus'), prefix)
            os.makedirs(targetdir, exist_ok=True)
            self.h5filename = os.path.join(targetdir, self.instrument.io.formatFileName(prefix, fsn, '.nxs'))
            with h5py.File(self.h5filename, 'w', libver='latest') as h5:
                logger.debug(f'Initializing NeXus file {h5.filename}')
                h5.attrs['NX_class'] = 'NXroot'
                grp = h5.require_group(f'{prefix}_{fsn:05d}')
                h5.attrs['default'] = f'{prefix}_{fsn:05d}'
                grp.attrs['NX_class'] = 'NXentry'
                self.instrument.toNeXus(grp)
        else:
            logger.debug('Won\'t write a NeXus file')

    @property
    def starttime(self):
        """expected start time of this image"""
        return self.command_ack_time + self.index * (self.exptime + self.expdelay)

    @property
    def endtime(self):
        """expected end time of this image"""
        return self.starttime + self.exptime

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        if (event.timerId() == self.pendingtimer) and (self.status == ExposureState.Pending):
            # the exposure is supposedly started
            self.onExposureStarted()
            self.killTimer(self.pendingtimer)
            self.pendingtimer = None
        elif (event.timerId() == self.runningtimer) and (self.status == ExposureState.Running):
            # the exposure is supposedly ended
            self.onExposureFinished()
            self.killTimer(self.runningtimer)
            self.runningtimer = None
        elif (event.timerId() == self.waitforimagetimer) and (self.status == ExposureState.WaitingForImage):
            # image waiting timeout spent
            self.killTimer(self.waitforimagetimer)
            self.waitforimagetimer = None
            self.status = ExposureState.TimedOut
            self.finished.emit(False, None)
        elif (event.timerId() == self.imageloadtimer) and (self.status == ExposureState.WaitingForImage):
            # try to load the image
            try:
                image = self.instrument.io.loadCBF(self.prefix, self.fsn, check_local=False)
            except FileNotFoundError:
                # the file is not there (yet?). Wait until timeout
                pass
            else:
                # the file has been found. Kill the timers
                logger.debug(f'CBF file {self.prefix}/{self.fsn} has been found.')
                self.killTimer(self.waitforimagetimer)
                self.killTimer(self.imageloadtimer)
                self.waitforimagetimer = None
                self.imageloadtimer = None
                self.status = ExposureState.Finished
                # construct the metadata
                logger.debug(f'Writing header for {self.prefix}/{self.fsn}')
                header = self.createHeader()
                self.instrument.io.imageReceived(self.prefix, self.fsn)
                try:
                    mask = self.instrument.io.loadMask(header.maskname)
                except FileNotFoundError:
                    logger.warning(f'Invalid mask file "{header.maskname}". You might have to create a mask yourself.')
                    mask = np.ones_like(image, dtype=np.uint8)
                uncertainty = np.empty_like(image)
                uncertainty[image > 0] = image[image > 0] ** 0.5
                uncertainty[image <= 0] = 1
                logger.debug(f'Finalizing NeXus file for {self.prefix}/{self.fsn}')
                self.writeNeXus(image, uncertainty, mask)
                # emit the raw image.
                exposure = Exposure(image, header, uncertainty, mask)
                if self.prefix == self.instrument.cfg['path',  'prefixes',  'crd']:
                    self.instrument.datareduction.submit(exposure)
                self.finished.emit(True, exposure)

    def onDetectorExposureStarted(self, starttime):
        """This method should be called when the detector has acknowledged the exposure command.
        In this method we initialize the timers.
        """
        self.command_ack_time = starttime
        assert self.status == ExposureState.Initializing
        if not self.index:
            # this is the first exposure
            self.status = ExposureState.Pending
            self.onExposureStarted()
        else:
            # pending time: exptime * index + expdelay * index
            self.status = ExposureState.Pending
            self.pendingtimer = self.startTimer(
                int(1000 * (self.exptime + self.expdelay) * self.index),
                QtCore.Qt.TimerType.PreciseTimer)
        self.runningtimer = self.startTimer(
            int(1000 * ((self.exptime + self.expdelay) * self.index + self.exptime)),
            QtCore.Qt.TimerType.PreciseTimer)
        self.waitforimagetimer = self.startTimer(
            int(1000 * ((self.exptime + self.expdelay) * self.index + self.exptime + self.imagetimeout)),
            QtCore.Qt.TimerType.PreciseTimer)

    def onExposureStarted(self):
        logger.debug(f'Exposure of {self.prefix}/{self.fsn} started')
        assert self.status == ExposureState.Pending
        self.status = ExposureState.Running
        self.exposurestarted.emit()

    def onExposureFinished(self):
        logger.debug(f'Exposure of {self.prefix}/{self.fsn} finished')
        assert self.status == ExposureState.Running
        self.imageloadtimer = self.startTimer(int(1000 * self.imageloadperiod), QtCore.Qt.TimerType.PreciseTimer)
        self.status = ExposureState.WaitingForImage
        self.exposureended.emit()

    def stopExposure(self):
        """Stop the ongoing exposure

        This method does not talk to the detector: its job is to stop all the timers, to avoid waiting
        """
        if self.pendingtimer:
            self.killTimer(self.pendingtimer)
            self.pendingtimer = None
        if self.runningtimer:
            self.killTimer(self.runningtimer)
            self.runningtimer = None
        if self.waitforimagetimer:
            self.killTimer(self.waitforimagetimer)
            self.waitforimagetimer = None
        if self.imageloadtimer:
            self.killTimer(self.imageloadtimer)
            self.imageloadtimer = None
        self.status = ExposureState.Stopped
        self.finished.emit(False, None)

    def createHeader(self) -> Header:
        sample: Optional[Sample] = self.instrument.samplestore.currentSample()
        data = {
            'fsn': self.fsn,
            'filename': os.path.abspath(
                os.path.join(
                    self.instrument.cfg['path',  'directories',  'param'], self.prefix,
                    self.instrument.io.formatFileName(self.prefix, self.fsn, '.pickle'))),
            'exposure': {
                'fsn': self.fsn,
                'prefix': self.prefix,
                'exptime': self.exptime,
                'monitor': self.exptime,
                'startdate': datetime.datetime.fromtimestamp(time.time() - time.monotonic() + self.starttime),
                'date': datetime.datetime.now(),
                'enddate': datetime.datetime.now(),
            },
            'geometry': self.instrument.geometry.getHeaderEntry(),
            'sample': sample.todict() if sample is not None else {},
            'motors': self.instrument.motors.getHeaderEntry(),
            'devices': {dev.name: dev.toDict() for dev in self.instrument.devicemanager.iterDevices() if dev.isOnline()},
            'environment': {},
            'accounting': {'projectid': self.instrument.projects.project().projectid,
                           'operator': self.instrument.auth.username(),
                           'projectname': self.instrument.projects.project().title,
                           'proposer': self.instrument.projects.project().proposer},
        }
        # devices
        for dev in self.instrument.devicemanager.iterDevices():
            if not dev.isOnline():
                continue
            data['devices'][dev.name]['devicetype'] = dev.devicetype.value
            data['devices'][dev.name]['deviceclass'] = dev.devicename
        # environment
        try:
            vac = self.instrument.devicemanager.vacuum()
            data['environment']['vacuum_pressure'] = vac.pressure()
        except (KeyError, IndexError, DeviceFrontend.DeviceError):
            data['environment']['vacuum_pressure'] = 0.0001
        try:
            temp = self.instrument.devicemanager.temperature()
            data['environment']['temperature'] = temp.temperature()
        except (KeyError, IndexError, DeviceFrontend.DeviceError):
            data['environment']['temperature'] = np.nan
        # sensors
        data['sensors'] = {s.name: s.__getstate__() for s in self.instrument.sensors}
        # adjust truedistance
        if sample is not None:
            data['geometry']['truedistance'] = data['geometry']['dist_sample_det'] - data['sample']['distminus.val']
            data['geometry']['truedistance.err'] = (data['geometry']['dist_sample_det.err'] ** 2 + data['sample'][
                'distminus.err'] ** 2) ** 0.5
        if (sample is not None) and (sample.maskoverride is not None) and sample.maskoverride.strip():
            data['geometry']['mask'] = sample.maskoverride
        if (self.maskoverride is not None) and self.maskoverride.strip():
            # global mask override takes precedence
            data['geometry']['mask'] = self.maskoverride
        # Save the pickle file
        folder, filename = os.path.split(data['filename'])
        os.makedirs(folder, exist_ok=True)
        with open(data['filename'], 'wb') as f:
            pickle.dump(data, f)
        return Header(datadict=data)

    def writeNeXus(self, img: np.ndarray, unc: np.ndarray, mask: np.ndarray):
        if self.h5filename is None:
            return
        with h5py.File(self.h5filename, 'a', libver='latest') as h5:
            logger.debug(f'Finalizing NeXus file {h5.filename}')
            grp = h5.require_group(f'{self.prefix}_{self.fsn:05d}')
            grp.attrs['NX_class'] = 'NXentry'
            # the instrument state has already been written, no need to call self.instrument.toNeXus() again.
            instgroup = grp[[g for g in grp if ('NX_class' in grp[g].attrs) and (grp[g].attrs['NX_class'] == 'NXinstrument')][0]]
            detectorgroup: h5py.Group = instgroup[[g for g in instgroup if ('NX_class' in instgroup[g].attrs) and (instgroup[g].attrs['NX_class'] == 'NXdetector')][0]]
            ds = detectorgroup.create_dataset('data', data=img)
            ds.attrs['target'] = ds.name  # we will link to this from NXentry/NXdata
            ds = detectorgroup.create_dataset('data_errors', data=unc)
            ds.attrs['target'] = ds.name  # we will link to this from NXentry/NXdata
            ds = detectorgroup.create_dataset('pixel_mask', data=mask.astype(np.uint32))
            ds.attrs['target'] = ds.name

            datagrp = grp.create_group('data')
            datagrp.attrs['NX_class'] = 'NXdata'
            datagrp.attrs['signal'] = 'data'
            datagrp['data'] = detectorgroup['data']
            grp.attrs['default'] = 'data'
            datagrp['errors'] = detectorgroup['data_errors']

            try:
                samplegroup = grp[[g for g in grp if ('NX_class' in grp[g].attrs) and (grp[g].attrs['NX_class'] == 'NXsample')][0]]
            except IndexError:
                # no sample group, probably an exposure without specifying the sample
                pass
            else:
                datagrp['title'] = f"{samplegroup['name'][()].decode('utf-8')}"
        self.h5filename = None

