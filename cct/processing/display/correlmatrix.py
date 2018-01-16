import matplotlib.cm
from h5py import Group
from matplotlib.figure import Figure


def show_cmatrix(fig: Figure, grp: Group):
    fig.clear()
    try:
        cmat = grp['correlmatrix']
    except KeyError:
        return
    ax = fig.add_subplot(1, 1, 1)
    ax.imshow(cmat, cmap=matplotlib.cm.coolwarm, interpolation='nearest')
    fsns = sorted([grp['curves'][ds].attrs['fsn'] for ds in grp['curves'].keys()])
    ax.set_xticks(list(range(len(fsns))))
    ax.set_xticklabels([str(f) for f in fsns], rotation='vertical')
    ax.set_yticks(list(range(len(fsns))))
    ax.set_yticklabels([str(f) for f in fsns])
