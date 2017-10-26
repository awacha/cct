from typing import Tuple

import matplotlib.cm
import numpy as np
from h5py import Group
from matplotlib.axes import Axes
from matplotlib.colors import LogNorm, Normalize
from matplotlib.figure import Figure


def pixel_to_q(row:float, column:float, bcrow:float, bccol:float, pixelsizerow:float, pixelsizecol:float, distance:float, wavelength:float) -> Tuple[float, float]:
    qrow = 4 * np.pi * np.sin(0.5 * np.arctan(float(
            (row - float(bcrow)) *
            float(pixelsizerow) /
            float(distance)))) / float(wavelength)
    qcol = 4 * np.pi * np.sin(0.5 * np.arctan(
            (column - float(bccol)) *
            float(pixelsizecol) /
            float(distance))) / float(wavelength)
    return qrow, qcol

def show_scattering_image(fig:Figure, group:Group, showmask:bool=True, showcenter:bool=True):
    fig.clear()
    img = np.array(group['image'])
    mask = np.array(group['mask'])
    ax=fig.add_subplot(1,1,1)
    assert isinstance(ax, Axes)

    ymin, xmin = pixel_to_q(0, 0, group.attrs['beamcentery'], group.attrs['beamcenterx'], group.attrs['pixelsizey'], group.attrs['pixelsizex'], group.attrs['distance'], group.attrs['wavelength'])
    ymax, xmax = pixel_to_q(img.shape[0], img.shape[1], group.attrs['beamcentery'], group.attrs['beamcenterx'], group.attrs['pixelsizey'], group.attrs['pixelsizex'], group.attrs['distance'], group.attrs['wavelength'])

    ret = ax.imshow(img, extent=[xmin, xmax, -ymax, -ymin], aspect='equal', origin='upper', interpolation='nearest', norm=LogNorm())
    if showmask:
        # workaround: because of the colour-scaling we do here, full one and
        #   full zero masks look the SAME, i.e. all the image is shaded.
        #   Thus if we have a fully unmasked matrix, skip this section.
        #   This also conserves memory.
        if (mask == 0).sum():  # there are some masked pixels
            # we construct another representation of the mask, where the masked pixels are 1.0, and the
            # unmasked ones will be np.nan. They will thus be not rendered.
            mf = np.ones(mask.shape, np.float)
            mf[mask != 0] = np.nan
            ax.imshow(mf, extent = [xmin, xmax, -ymax, -ymin], aspect='equal', origin='upper', interpolation='nearest', alpha=0.8, norm=Normalize(), cmap=matplotlib.cm.gray_r)
    if showcenter:
        lims = ax.axis()  # save zoom state
        ax.plot([xmin, xmax], [0,0], 'w-')
        ax.plot([0,0], [ymin, ymax], 'w-')
        ax.axis(lims)  # restore zoom state
    ax.set_facecolor('black')
    # try to find a suitable colorbar axes: check if the plot target axes already
    # contains some images, then check if their colorbars exist as
    # axes.
    cax = [i.colorbar[1]
           for i in ax.images if i.colorbar is not None]
    cax = [c for c in cax if c in c.figure.axes]
    if cax:
        cax = cax[0]
    else:
        cax = None
    ax.set_xlabel('$q_x$ (nm$^{-1}$)')
    ax.set_ylabel('$q_x$ (nm$^{-1}$)')
    ax.figure.colorbar(ret, cax=cax, ax=ax)
