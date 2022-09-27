# conding: utf-8
"""Manual beam position finding"""

from .centeringmethod import CenteringMethod
import logging
from typing import Union, Optional
from .....core2.dataclasses.exposure import Exposure
import numpy as np
from matplotlib.backend_bases import MouseEvent, PickEvent
from matplotlib.widgets import Cursor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Manual(CenteringMethod):
    name = "Manual"
    description = "Manual centering, by clicking on the pattern or dragging the polar representation"
    polardrag: Optional[MouseEvent] = None
    cid_press: Optional[int] = None
    cid_release: Optional[int] = None
    cid_pick: Optional[int] = None
    cursor: Optional[Cursor] = None
    beamrow: float
    beamcol: float

    def setupUi(self, Form):
        pass

    def prepareUI(self, exposure: Exposure):
        if exposure is None:
            return
        self.cid_press = self.polaraxes.figure.canvas.mpl_connect('button_press_event', self.on_polarcanvas_mpl_button_press)
        self.cid_release = self.polaraxes.figure.canvas.mpl_connect('button_release_event', self.on_polarcanvas_mpl_button_release)
        self.cursor = Cursor(self.patternaxes, horizOn=True, vertOn=True, useblit=True, color='red', ls='--', lw=2)
        self.cursor.active = True
        self.cid_pick = self.patternaxes.figure.canvas.mpl_connect('pick_event', self.on2DPick)
        self.patternaxes.set_picker(True)
        self.beamrow = exposure.header.beamposrow[0]
        self.beamcol = exposure.header.beamposcol[0]

    def cleanupUI(self):
        if self.cid_press is not None:
            self.polaraxes.figure.canvas.mpl_disconnect(self.cid_press)
            self.cid_press = None
        if self.cid_release is not None:
            self.polaraxes.figure.canvas.mpl_disconnect(self.cid_release)
            self.cid_release = None
        if self.cid_pick is not None:
            self.patternaxes.figure.canvas.mpl_disconnect(self.cid_pick)
            self.cid_pick = None
        if self.cursor is not None:
            self.cursor.active=False
            self.cursor = None

    def goodnessfunction(self, beamrow: Union[float, np.ndarray], beamcol: Union[float, np.ndarray],
                         exposure: Exposure):
        return np.nan * np.ones_like(beamrow)

    def on_polarcanvas_mpl_button_press(self, event: MouseEvent):
        if event.inaxes is not self.polaraxes:
            logger.debug('Not inaxes')
            return
        logger.debug('Polardrag start')
        self.polardrag = event

    def on_polarcanvas_mpl_button_release(self, event: MouseEvent):
        if self.polardrag is None:
            logger.debug('polardrag was None')
            return
        if event.inaxes is self.polardrag.inaxes:
            r0, phi0 = self.polardrag.xdata, self.polardrag.ydata / 180.0 * np.pi
            r1, phi1 = event.xdata, event.ydata / 180.0 * np.pi
            phi1 = phi0
            #  the corresponding pixel: row = beamrow0 - r0 * sin(phi0),   col = beamcol0 + r0 * cos(phi0)
            #  It changes to: row = beamrow1 - r1 * sin(phi1),  col = beamcol1 + r1 * cos(phi1)
            #  beamrow1 = beamrow0 - r0 * sin(phi0) + r1 * sin(phi1)
            #  beamcol1 = beamcol0 + r0 * cos(phi0) - r1 * cos(phi1)
            self.positionFound.emit(
                self.beamrow - r0 * np.sin(phi0) + r1 * np.sin(phi1), 0.0,
                self.beamcol + r0 * np.cos(phi0) - r1 * np.cos(phi1), 0.0)
        else:
            logger.debug('Was not inaxes')
        self.polardrag = None

    def on2DPick(self, event: PickEvent):
        if (self.cursor is not None) and self.cursor.active:
            if event.mouseevent.button == 1:
                beamcol, beamrow = event.mouseevent.xdata, event.mouseevent.ydata
                self.positionFound.emit(beamrow, 0.0, beamcol, 0.0)
