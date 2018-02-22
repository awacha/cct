from PyQt5 import QtWidgets, QtCore
from ...core.mixins import ToolWindow
from ...core.plotcurve import PlotCurve
from ...core.plotimage import PlotImage
from ...core.fsnselector import FSNSelector
from ...core.h5selector import H5Selector
from .anisotropy_ui import Ui_MainWindow
from sastool.classes2 import Exposure, Curve
from matplotlib.widgets import SpanSelector
from matplotlib.patches import Circle
from sastool.utils2d.integrate import azimint, radint_errorprop
import numpy as np

class AnisotropyEvaluator(QtWidgets.QMainWindow, Ui_MainWindow, ToolWindow):
    def __init__(self, *args, **kwargs):
        try:
            credo = kwargs.pop('credo')
        except KeyError:
            credo = None
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        self._circles = []
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.setWindowTitle('Anisotropy Evaluator [*]')
        self.plotimage = PlotImage(self, False)
        self.plotimage.setPixelMode(True)
        self.plotcurve_full = PlotCurve(self.centralWidget)
        self.plotcurve_azim = PlotCurve(self.centralWidget)
        self.plotcurve_slice = PlotCurve(self.centralWidget)
        self.gridLayout=QtWidgets.QGridLayout(self.centralWidget)
        self.centralwidget.setLayout(QtWidgets.QGridLayout(self))
        if self.credo is not None:
            self.fsnSelector = FSNSelector(self, credo=self.credo, horizontal=True)
            self.centralwidget.layout().addWidget(self.fsnSelector)
            self.fsnSelector.FSNSelected.connect(self.onFSNSelected)
        self.h5Selector = H5Selector(self, horizontal=True)
        self.centralwidget.layout().addWidget(self.h5Selector)
        self.h5Selector.H5Selected.connect(self.onH5Selected)
        self.gridLayout.addWidget(self.plotimage, 0, 0, 1,1)
        self.gridLayout.addWidget(self.plotcurve_full, 0, 1, 1,1)
        self.gridLayout.addWidget(self.plotcurve_azim, 1, 0, 1,1)
        self.gridLayout.addWidget(self.plotcurve_slice, 1,1,1,1)

    def onFSNSelected(self, prefix:str, fsn:int, exposure:Exposure):
        self.setExposure(exposure)

    def onH5Selected(self, filename:str, sample:str, distance:float, exposure:Exposure):
        self.setExposure(exposure)

    def setExposure(self, exposure:Exposure):
        self.removeCircles()
        self.plotimage.setExposure(exposure)
        self.plotcurve_full.clear()
        self.plotcurve_full.addCurve(exposure.radial_average(), label='Full radial average', hold_mode=False)
        self.fullSpanSelector = SpanSelector(self.plotcurve_full.axes, self.onQRangeSelected, 'horizontal', span_stays=True)

    def removeCircles(self):
        for c in self._circles:
            c.remove()
        self._circles = []

    def onQRangeSelected(self, qmin:float, qmax:float):
        self.removeCircles()
        self._circles = [
            Circle([0,0], radius = qmin, color='white', fill=False, linestyle='--', zorder=100),
            Circle([0,0], radius = qmax, color='white', fill=False, linestyle='--', zorder=100)
        ]
        ex=self.exposure()
        phi, intensity, error, area, mask = azimint(ex.intensity, ex.error, ex.header.wavelength.val, ex.header.distance.val,
                                                    ex.header.pixelsizex.val, ex.header.beamcentery.val, ex.header.beamcenterx.val,
                                                    (ex.mask==0).astype(np.uint8), qmin=qmin, qmax=qmax, returnmask=True
                                                    )
        self.plotcurve_azim.clear()
        self.plotcurve_azim.addCurve(Curve(phi, intensity, error), label='Azimuthal curve', hold_mode=False)
        self.plotcurve_azim.axes.set_xscale('linear')
        self.plotcurve_azim.axes.set_yscale('linear')
        self.plotcurve_azim.canvas.draw()
        self.azimSpanSelector = SpanSelector(self.plotcurve_azim.axes, self.onPhiRangeSelected, 'horizontal', span_stays=True)

    def onPhiRangeSelected(self, phimin:float, phimax:float):
        ex = self.exposure()
        q, dq, intensity, dintensity, area, mask = radint_errorprop(
            ex.intensity, ex.error, ex.header.wavelength.val, ex.header.wavelength.err, ex.header.distance.val,
            ex.header.distance.err, ex.header.pixelsizey.val, ex.header.pixelsizex.val, ex.header.beamcentery.val,
            ex.header.beamcentery.err, ex.header.beamcenterx.val, ex.header.beamcenterx.err,
            (ex.mask==0).astype(np.uint8), phi0=(phimin+phimax)*0.5, dphi=phimax-phimin, returnmask=True,
            symmetric_sector=True,
        )
        self.plotcurve_slice.addCurve(Curve(q, intensity, dintensity, dq), 'Slice average')

    def exposure(self) -> Exposure:
        return self.plotimage.exposure()
