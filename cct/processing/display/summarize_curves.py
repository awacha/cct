import h5py
import numpy as np
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec


def summarize_curves(fig:Figure, group:h5py.Group):
    fig.clear()
    gs = GridSpec(3,1,hspace=0,)
    ax_curves=fig.add_subplot(gs[0, :2])
    ax_std=fig.add_subplot(gs[0, 2])
    I=[]
    for fsn in sorted(group.keys(), key=lambda x:int(x)):
        dset=group[fsn]
        if dset.attrs['correlmat_bad']:
            color = 'r'
        else:
            color = 'g'
        ax_curves.loglog(dset[:,0],dset[:,1],'-', color=color)
        I.append(dset[:,1])
    I=np.hstack(tuple(I))
    ax_curves.loglog(dset[:,0], I.mean(axis=1),'k-',lw=1)
    ax_std.loglog(dset[:,0],I.std(axis=1)*100,'b-')
    ax_std.axis(xmin=ax_curves.axis()[0], xmax=ax_curves.axis()[1])
    ax_curves.grid(True, which='both')
    ax_std.grid(True, which='both')
    ax_std.set_xlabel('q (nm$^{-1}$)')
    ax_curves.set_ylabel('$d\Sigma/d\Omega$ (cm$^{-1}$sr$^{-1}$)')
    ax_std.set_ylabel('STD of intensity (%)')


