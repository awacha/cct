import matplotlib.cm
from h5py import Group
from matplotlib.figure import Figure


def show_cmatrix(fig: Figure, grp: Group):
    fig.clear()
    try:
        cmat = grp['correlmatrix']
        curvesgrp = grp['curves']
    except KeyError:
        return
    ax = fig.add_subplot(1, 1, 1)
    img=ax.imshow(cmat, cmap=matplotlib.cm.coolwarm, interpolation='nearest')
    fig.colorbar(img, ax=ax)
    fsns = sorted([curvesgrp[ds].attrs['fsn'] for ds in curvesgrp.keys()])
    ax.set_xticks(list(range(len(fsns))))
    ax.set_xticklabels([str(f) for f in fsns], rotation='vertical')
    ax.set_yticks(list(range(len(fsns))))
    ax.set_yticklabels([str(f) for f in fsns])
