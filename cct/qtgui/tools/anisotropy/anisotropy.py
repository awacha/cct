import numpy as np
from PyQt5 import QtWidgets
from matplotlib.patches import Circle
from matplotlib.widgets import SpanSelector
from sastool.classes2 import Exposure, Curve
from sastool.utils2d.integrate import azimint, radint_errorprop

from .anisotropy_ui import Ui_MainWindow
from ...core.fsnselector import FSNSelector
from ...core.h5selector import H5Selector
from ...core.mixins import ToolWindow
from ...core.plotimage import PlotImage


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
        self.plotimage.figure.clf()
        self.plotimage.axes = self.plotimage.figure.add_subplot(2,2,1)
        self.plotimage.axes.set_facecolor('black')
        self.axes_full = self.plotimage.figure.add_subplot(2,2,2)
        self.axes_azim = self.plotimage.figure.add_subplot(2,2,3)
        self.axes_slice = self.plotimage.figure.add_subplot(2,2,4)
        self.vboxLayout = QtWidgets.QVBoxLayout(self.centralWidget())
        self.centralWidget().setLayout(self.vboxLayout)
        if self.credo is not None:
            self.fsnSelector = FSNSelector(self, credo=self.credo, horizontal=True)
            self.vboxlayout().addWidget(self.fsnSelector)
            self.fsnSelector.FSNSelected.connect(self.onFSNSelected)
        self.h5Selector = H5Selector(self, horizontal=True)
        self.vboxLayout.addWidget(self.h5Selector)
        self.h5Selector.H5Selected.connect(self.onH5Selected)
        self.vboxLayout.addWidget(self.plotimage, stretch=1)
        self.plotimage.figure.tight_layout()
        self.plotimage.canvas.draw()

    def onFSNSelected(self, prefix:str, fsn:int, exposure:Exposure):
        self.setExposure(exposure)

    def onH5Selected(self, filename:str, sample:str, distance:float, exposure:Exposure):
        self.setExposure(exposure)

    def setExposure(self, exposure:Exposure):
        self.removeCircles()
        self.axes_azim.clear()
        self.axes_slice.clear()
        self.plotimage.setExposure(exposure)
        self.axes_full.clear()
        exposure.radial_average().loglog(axes=self.axes_full, label='Full radial average')
        self.axes_full.set_xlabel('q (nm$^{-1}$)')
        self.axes_full.set_ylabel('$d\sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
        self.axes_full.set_title('Circular average')
        self.fullSpanSelector = SpanSelector(self.axes_full, self.onQRangeSelected, 'horizontal', span_stays=True)
        self.plotimage.canvas.draw()

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
        self.plotimage.axes.add_patch(self._circles[0])
        self.plotimage.axes.add_patch(self._circles[1])
        self.plotimage.canvas.draw()
        ex=self.exposure()
        ex.mask_nonfinite()
        phi, intensity, error, area, mask = azimint(ex.intensity, ex.error, ex.header.wavelength.val, ex.header.distance.val,
                                                    ex.header.pixelsizex.val, ex.header.beamcentery.val, ex.header.beamcenterx.val,
                                                    (ex.mask==0).astype(np.uint8), qmin=min(qmin,qmax), qmax=max(qmin,qmax),
                                                    returnmask=True
                                                    )
        self.axes_azim.clear()
        self.axes_azim.plot(phi*180.0/np.pi, intensity, label='Azimuthal curve')
        self.plotimage.canvas.draw()
        self.azimSpanSelector = SpanSelector(self.axes_azim, self.onPhiRangeSelected, 'horizontal', span_stays=True)
        self.axes_azim.set_xlabel('$\phi$ (°)')
        self.axes_azim.set_ylabel('$d\sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
        self.axes_azim.set_title('Azimuthal scattering curve')

    def onPhiRangeSelected(self, phimin:float, phimax:float):
        ex = self.exposure()
        phi0=(phimin+phimax)*0.5
        dphi=(phimax-phimin)
        ex.mask_nonfinite()
        q, dq, intensity, dintensity, area, mask = radint_errorprop(
            ex.intensity, ex.error, ex.header.wavelength.val, ex.header.wavelength.err, ex.header.distance.val,
            ex.header.distance.err, ex.header.pixelsizey.val, ex.header.pixelsizex.val, ex.header.beamcentery.val,
            ex.header.beamcentery.err, ex.header.beamcenterx.val, ex.header.beamcenterx.err,
            (ex.mask==0).astype(np.uint8), phi0=phi0*np.pi/180.0, dphi=dphi*np.pi/180.0, returnmask=True,
            symmetric_sector=True,
        )
        print('q:',q)
        print('intensity:',intensity)
        print('error:',dintensity)
        print('qerror:',dq)
        Curve(q, intensity, dintensity, dq).loglog(
            axes=self.axes_slice,
            label='$\phi_0={:.2f}^\circ$, $\Delta\phi = {:.2f}^\circ$'.format(phi0,dphi))
        self.axes_slice.legend(loc='best')
        self.axes_slice.set_title('Slices')

    def exposure(self) -> Exposure:
        return self.plotimage.exposure()
