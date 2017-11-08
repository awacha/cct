import h5py
import numpy as np
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec


def summarize_curves(fig: Figure, group: h5py.Group, showgoods: bool = True, showbads: bool = True,
                     showmean: bool = True, logx: bool = True, logy: bool = True):
    fig.clear()
    gs = GridSpec(3, 1, hspace=0, )
    ax_curves = fig.add_subplot(gs[:2, 0])
    ax_std = fig.add_subplot(gs[2, 0], sharex=ax_curves)
    I = []
    for fsn in sorted(group.keys(), key=lambda x: int(x)):
        dset = group[fsn]
        if dset.attrs['correlmat_bad']:
            if not showbads:
                continue
            color = 'r'
        else:
            if not showgoods:
                continue
            color = 'g'
        ax_curves.plot(dset[:, 0], dset[:, 1], '-', color=color)
        I.append(dset[:, 1])
    if len(I) and showmean:
        I = np.vstack(tuple(I))
        ax_curves.plot(dset[:, 0], I.mean(axis=0), 'k-', lw=1)
        ax_std.plot(dset[:, 0], I.std(axis=0) * 100, 'b-')
    if logx:
        ax_curves.set_xscale('log')
        ax_std.set_xscale('log')
    if logy:
        ax_curves.set_yscale('log')
        ax_std.set_yscale('log')
    ax_std.axis(xmin=ax_curves.axis()[0], xmax=ax_curves.axis()[1])
    ax_curves.grid(True, which='both')
    ax_std.grid(True, which='both')
    ax_std.set_xlabel('q (nm$^{-1}$)')
    ax_curves.set_ylabel('$d\Sigma/d\Omega$ (cm$^{-1}$sr$^{-1}$)')
    ax_std.set_ylabel('STD of intensity (%)')
