import dateutil.parser
import h5py
from matplotlib.axes import Axes
from matplotlib.figure import Figure


def plot_vacuum_and_flux(fig: Figure, group: h5py.Group, gc_name='Glassy_Carbon'):
    fig.clear()

    dates_vacuums = []
    dates_fluxes = []
    for sn in group.keys():
        for dist in group[sn].keys():
            grp = group[sn][dist]
            dates_vacuums.extend(
                [(dateutil.parser.parse(grp['curves'][c].attrs['date']),
                  grp['curves'][c].attrs['vacuum'])
                 for c in sorted(grp['curves'].keys(), key=lambda x: int(x))]
            )
            try:
                # try to use gc_name as a regular expression
                if not gc_name.match(sn) is not None:
                    continue
            except AttributeError:
                # gc_name is a simple string
                if not sn == gc_name:
                    continue
            dates_fluxes.extend(
                [
                    (
                        dateutil.parser.parse(grp['curves'][c].attrs['date']),
                        grp['curves'][c].attrs['flux']
                    )
                    for c in sorted(grp['curves'].keys(), key=lambda x: int(x))
                ]
            )
    dates_vacuums = sorted(dates_vacuums, key=lambda x: x[0])  # sort according to date
    dates_fluxes = sorted(dates_fluxes, key=lambda x: x[0])  # sort according to date

    ax = fig.add_subplot(1, 1, 1)
    assert isinstance(ax, Axes)
    ax.plot([x[0] for x in dates_fluxes], [x[1] for x in dates_fluxes], 'bo')
    ax2 = ax.twinx()
    ax2.plot([x[0] for x in dates_vacuums], [x[1] for x in dates_vacuums], 'r.')
    ax.set_ylabel('Flux (photon/sec)', color='b')
    ax2.set_ylabel('Vacuum (mbar)', color='r')
    ax.set_xlabel('Date of exposure')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=90)
    ax.set_yticklabels(ax.get_yticklabels(), color='b')
    ax2.set_yticklabels(ax2.get_yticklabels(), color='r')
    fig.tight_layout()
