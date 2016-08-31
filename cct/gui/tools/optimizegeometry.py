import collections
import logging
import itertools
import time
import math
from typing import Union, Sequence, SupportsFloat, Optional

from gi.repository import Gtk, Gdk, GLib

from ..core.toolwindow import ToolWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def all_combinations(sequence:Sequence):
    for n in range(len(sequence)+1):
        for c in itertools.combinations(sequence, n):
            yield c
    return

class PinholeConfiguration(object):
    """This class represents the collimation geometry of a conventional SAS instrument."""

    def __init__(self, L1: Union[Sequence, SupportsFloat], L2: Union[Sequence, SupportsFloat], D1: float, D2: float,
                 ls: float, lbs: float, sd: float, mindist_l1: float = 0.0, mindist_l2: float = 0.0,
                 sealringwidth: float = 0.0, wavelength: float = 0.15418):
        if not isinstance(L1, collections.Iterable):
            L1 = [L1]
        self.l1_elements = L1
        if not isinstance(L2, collections.Iterable):
            L2 = [L2]
        self.l2_elements = L2
        self.mindist_l1 = mindist_l1
        self.mindist_l2 = mindist_l2
        self.sealringwidth = sealringwidth
        self.r1 = D1 * 0.5e-3
        self.r2 = D2 * 0.5e-3
        self.ls = ls
        self.lbs = lbs
        self.sd = sd
        self.wavelength = wavelength

    def __copy__(self) -> 'PinholeConfiguration':
        return PinholeConfiguration(
            self.l1_elements, self.l2_elements, self.D1, self.D2, self.ls,
            self.lbs, self.sd, self.mindist_l1, self.mindist_l2,
            self.sealringwidth, self.wavelength)

    copy = __copy__

    @property
    def l1(self) -> float:
        if isinstance(self.l1_elements, collections.Sequence):
            return float(sum(self.l1_elements) +
                         self.sealringwidth * (1 + len(self.l1_elements)) +
                         self.mindist_l1)
        else:
            return self.l1_elements

    @l1.setter
    def l1(self, value):
        self.l1_elements = value

    @property
    def l2(self) -> float:
        if isinstance(self.l2_elements, collections.Sequence):
            return float(sum(self.l2_elements) +
                         self.sealringwidth * (1 + len(self.l2_elements)) +
                         self.mindist_l2)
        else:
            return self.l2_elements

    @l2.setter
    def l2(self, value):
        self.l2_elements = value

    @property
    def D1(self) -> float:
        return 2000 * self.r1

    @D1.setter
    def D1(self, value):
        self.r1 = value * 0.5e-3

    @property
    def D2(self) -> float:
        return 2000 * self.r2

    @D2.setter
    def D2(self, value):
        self.r2 = value * 0.5e-3

    @property
    def D3(self) -> float:
        return 2000 * self.r3

    @property
    def Dsample_direct(self) -> float:
        return 2 * self.rs_direct

    @property
    def Dsample_parasitic(self) -> float:
        return 2 * self.rs_parasitic

    Dsample = Dsample_direct

    @property
    def Dbs_parasitic(self) -> float:
        return 2 * self.rbs_parasitic

    @property
    def Dbs_direct(self) -> float:
        return 2 * self.rbs_direct

    Dbs = Dbs_parasitic

    @property
    def Ddet_parasitic(self) -> float:
        return 2 * self.rdet_parasitic

    @property
    def Ddet_direct(self) -> float:
        return 2 * self.rdet_direct

    Ddet = Ddet_parasitic

    @property
    def l3(self) -> float:
        return self.sd + self.ls

    @property
    def r3(self) -> float:
        return self.r2 + (self.r1 + self.r2) * self.l2 / self.l1

    @property
    def rs_direct(self) -> float:
        return self.r2 + (self.r1 + self.r2) * (self.l2 + self.ls) / self.l1

    @property
    def rs_parasitic(self) -> float:
        return self.r3 + (self.r2 + self.r3) * (self.ls / self.l2)

    rs = rs_direct

    @property
    def rbs_direct(self) -> float:
        return (self.r2 + (self.r1 + self.r2) * (self.l2 + self.l3 -
                                                 self.lbs) / self.l1)

    @property
    def rbs_parasitic(self) -> float:
        return ((self.r2 + self.r3) * (self.l2 + self.l3 - self.lbs) /
                self.l2 - self.r2)

    rbs = rbs_parasitic

    @property
    def rdet_direct(self) -> float:
        return (self.r2 + (self.r1 + self.r2) * (self.l2 + self.l3) /
                self.l1)

    @property
    def rdet_parasitic(self) -> float:
        return ((self.r2 + self.r3) * (self.l2 + self.l3) /
                self.l2 - self.r2)

    rdet = rdet_parasitic

    @property
    def tantthmin(self) -> float:
        return (self.rbs_parasitic / (self.sd - self.lbs))

    @property
    def qmin(self) -> float:
        return (4 * math.pi * math.sin(0.5 * math.atan(self.tantthmin)) /
                self.wavelength)

    @property
    def dmax(self) -> float:
        return 2 * math.pi / self.qmin

    @property
    def intensity(self) -> float:
        return self.D1 ** 2 * self.D2 ** 2 / self.l1 ** 2 / 64 * math.pi

    @property
    def alpha(self) -> float:
        return math.atan2((self.r2 + self.r1), self.l1)

    @property
    def dspheremax(self) -> float:
        return (5 / 3.) ** 0.5 * 2 * self.Rgmax

    @property
    def Rgmax(self) -> float:
        return 1 / self.qmin

    def __str__(self) -> str:
        return 'l1: %.2f mm; l2: %.2f mm; D1: %.0f um; D2: %.0f um;\
D3: %.0f um; I: %.2f; qmin: %.5f 1/nm' % (self.l1, self.l2, self.D1, self.D2,
                                          self.D3, self.intensity, self.qmin)

    @property
    def dominant_constraint(self) -> str:
        lambda1 = (self.ls + self.l2) / self.l1
        lambda0 = (self.l2 / self.l1)
        rho = self.rs / self.rbs
        d_SsBS = (
            (2 * lambda1 * (lambda1 + 1) - rho * (lambda0 + lambda1 +
                                                  2 * lambda0 * lambda1)) /
            (rho * (lambda0 + 2 * lambda1 + 2 * lambda0 * lambda1)) *
            self.l2 + self.lbs - self.ls)
        Discr = 4 * rho ** 2 * lambda0 ** 2 + rho * \
                                              (4 * lambda0 ** 2 - 8 * lambda0 * lambda1) + \
                (lambda0 + 2 * lambda1 + 2 * lambda0 * lambda1) ** 2
        lam2plus = ((2 * lambda1 + lambda0 + 2 * lambda0 * lambda1 -
                     6 * rho * lambda0 - 4 * rho * lambda0 ** 2 + Discr ** 0.5) /
                    (8 * rho * lambda0 + 4 * rho * lambda0 ** 2))
        d_BSsSplus = lam2plus * self.l2 + self.lbs - self.ls
        if self.sd < d_SsBS:
            return 'sample'
        elif self.sd < d_BSsSplus:
            return 'beamstop'
        else:
            return 'neither'

    @classmethod
    def enumerate(cls, spacers:Sequence[float], pinholes:Sequence[float],
                  ls, lbs, sd, mindist_l1, mindist_l2, sealringwidth, wavelength):
        l_seen=[]
        for l1_parts in all_combinations(spacers):
            l1 = mindist_l1+len(l1_parts)*sealringwidth+sum(l1_parts)
            spacers_remaining = list(spacers[:])
            for s in l1_parts:
                spacers_remaining.remove(s)
            for l2_parts in all_combinations(spacers_remaining):
                l2 = mindist_l2 + len(l2_parts)*sealringwidth + sum(l2_parts)
                if (l1, l2) in l_seen:
                    continue
                l_seen.append((l1, l2))
                for d1 in pinholes:
                    for d2 in pinholes:
                        yield PinholeConfiguration(l1_parts, l2_parts, d1, d2, ls, lbs, sd, mindist_l1, mindist_l2, sealringwidth, wavelength)

class OptimizeGeometry(ToolWindow):
    def __init__(self, gladefile, toplevelname, instrument, windowtitle, *args, **kwargs):
        self.pinholegenerator = None
        self.limits_beamstopsize = None
        self.limits_samplesize = None
        self.limit_l1min = None
        self.limit_l2min = None
        self.worksize = None
        self.workdone = None
        self._idle_handler = None
        self.html_being_built=""
        super().__init__(gladefile, toplevelname, instrument, windowtitle, *args, **kwargs)

    def init_gui(self, *args, **kwargs):
        for what in ['spacers', 'pinholes']:
            treeview = self.builder.get_object(what + '_treeview')
            model = treeview.get_model()
            assert isinstance(model, Gtk.ListStore)
            model.clear()
            for e in self.instrument.config['gui']['optimizegeometry'][what]:
                model.append(['{:.2f}'.format(e)])
            self.sort_and_tidy_model(treeview)
        treeview = self.builder.get_object('results_treeview')
        assert isinstance(treeview, Gtk.TreeView)
        for c in treeview.get_columns():
            assert isinstance(c, Gtk.TreeViewColumn)
            c.set_cell_data_func(c.get_cells()[0], self.cell_data_func)
        # sort by descending intensity
        self.builder.get_object('results_store').set_sort_column_id(16, Gtk.SortType.DESCENDING)

    def row_to_html(self, model:Gtk.ListStore, path:Gtk.TreePath, it:Gtk.TreeIter, treeview:Gtk.TreeView):
        self.html_being_built += "  <tr>\n"
        for c in treeview.get_columns():
            self.html_being_built += "    <td>"+ self.cell_data_func(c, None, model, it, None)+"</td>\n"
        self.html_being_built += "  </tr>"

    def on_copy_as_html(self, button: Gtk.Button):
        treeview = self.builder.get_object('results_treeview')
        assert isinstance(treeview, Gtk.TreeView)
        self.html_being_built = "<table>\n  <tr>\n"
        for c in treeview.get_columns():
            assert isinstance(c, Gtk.TreeViewColumn)
            self.html_being_built += "    <th>{}</th>\n".format(c.get_title())
        self.html_being_built += "  </tr>\n"
        treeview.get_selection().selected_foreach(self.row_to_html, treeview)
        self.html_being_built += "</table>"
        clipboard=Gtk.Clipboard.get_default(Gdk.Display.get_default())
        assert isinstance(clipboard, Gtk.Clipboard)
        clipboard.set_text(self.html_being_built, len(self.html_being_built))
        self.html_being_built = ""

    def on_entry_edited(self, treeview: Gtk.TreeView, path: Gtk.TreePath, new_text: str):
        model = treeview.get_model()
        assert isinstance(model, Gtk.ListStore)
        try:
            value = float(new_text)
        except ValueError:
            return
        model[path][0] = '{:.2f}'.format(value)
        self.sort_and_tidy_model(treeview)

    def sort_and_tidy_model(self, treeview: Gtk.TreeView):
        model, selectediter = treeview.get_selection().get_selected()
        assert isinstance(model, Gtk.ListStore)
        if selectediter is not None:
            prev_selected = model[selectediter][0]
        else:
            prev_selected = None
        values = [r[0] for r in model if r[0]]
        model.clear()
        selectediter = None
        for v in sorted(values, key=float):
            it = model.append([v])
            if v == prev_selected:
                selectediter = it
        model.append([''])
        if selectediter is not None:
            treeview.get_selection().select_iter(selectediter)
        return False

    def _idle_func(self):
        if self.pinholegenerator is None:
            return False
        try:
            pc = next(self.pinholegenerator)
            self.workdone +=1
        except StopIteration:
            self.end_work()
            return False
        assert self.limits_beamstopsize is not None
        assert self.limits_samplesize is not None
        assert self.limit_l1min is not None
        assert self.limit_l2min is not None
        assert isinstance(pc, PinholeConfiguration)
        assert isinstance(self.worksize, int)
        assert isinstance(self.workdone, int)
        if ((pc.Dbs>=self.limits_beamstopsize[0]) and (pc.Dbs<=self.limits_beamstopsize[1]) and
                (pc.Dsample>=self.limits_samplesize[0]) and (pc.Dsample<=self.limits_samplesize[1]) and
                (pc.l1 >= self.limit_l1min) and (pc.l2 >=self.limit_l2min)):
            # the pinhole configuration matches our criteria
            model = self.builder.get_object('results_store')
            model.append([pc, pc.l1, pc.l2,
                          ', '.join(['{:.0f}'.format(e) for e in pc.l1_elements]),
                          ', '.join(['{:.0f}'.format(e) for e in pc.l2_elements]),
                          pc.sd, pc.D1, pc.D2, pc.alpha*1000, pc.Dsample, pc.Dbs, pc.qmin, pc.dmax, pc.Rgmax,
                          pc.dspheremax, pc.D3, pc.intensity, pc.dominant_constraint])
        self.builder.get_object('work_progress').set_fraction(self.workdone/self.worksize)
        return True

    def on_resultscolumn_clicked(self, treeviewcolumn:Gtk.TreeViewColumn):
        pass

    def cell_data_func(self, treeviewcolumn:Gtk.TreeViewColumn, cellrenderer:Optional[Gtk.CellRendererText], model:Gtk.ListStore, it:Gtk.TreeIter, data):
        pc = model[it][0]
        colid = treeviewcolumn.get_sort_column_id()
        if colid == 1:
            text = '{:.0f}'.format(pc.l1)
        elif colid == 2:
            text = '{:.0f}'.format(pc.l2)
        elif colid == 3:
            text = ', '.join(['{:.0f}'.format(e) for e in pc.l1_elements])
        elif colid == 4:
            text = ', '.join(['{:.0f}'.format(e) for e in pc.l1_elements])
        elif colid == 5:
            text = '{:.01f}'.format(pc.sd)
        elif colid == 6:
            text = '{:.0f}'.format(pc.D1)
        elif colid == 7:
            text = '{:.0f}'.format(pc.D2)
        elif colid == 8:
            text = '{:.2f}'.format(pc.alpha*1000)
        elif colid == 9:
            text = '{:.2f}'.format(pc.Dsample)
        elif colid == 10:
            text = '{:.2f}'.format(pc.Dbs)
        elif colid == 11:
            text = '{:.4f}'.format(pc.qmin)
        elif colid == 12:
            text = '{:.1f}'.format(pc.dmax)
        elif colid == 13:
            text = '{:.1f}'.format(pc.Rgmax)
        elif colid == 14:
            text = '{:.1f}'.format(pc.dspheremax)
        elif colid == 15:
            text = '{:.0f}'.format(pc.D3)
        elif colid == 16:
            text = '{:.0f}'.format(pc.intensity)
        elif colid == 17:
            text = pc.dominant_constraint
        else:
            raise ValueError(colid)
        if cellrenderer is not None:
            cellrenderer.set_property('text', text)
        else:
            return text

    def estimate_worksize(self, spacers, pinholes, mindist_l1, mindist_l2, sealringwidth):
        progressbar=self.builder.get_object('work_progress')
        progressbar.set_text('Estimating work size...')
        l_seen = []
        count = 0
        lastpulse = 0
        for l1_parts in all_combinations(spacers):
            l1 = mindist_l1+len(l1_parts)*sealringwidth+sum(l1_parts)
            spacers_remaining = list(spacers[:])
            for s in l1_parts:
                spacers_remaining.remove(s)
            for l2_parts in all_combinations(spacers_remaining):
                if time.monotonic()-lastpulse >0.1:
                    progressbar.pulse()
                    lastpulse = time.monotonic()
                    if self.workdone is None:
                        # this happens if we were stopped before finishing
                        return None
                    for i in range(100):
                        if not Gtk.events_pending():
                            break
                        Gtk.main_iteration()
                l2 = mindist_l2+len(l2_parts)*sealringwidth+sum(l2_parts)
                if (l1, l2) in l_seen:
                    continue
                l_seen.append((l1, l2))
                count += 1
        progressbar.set_text('Filtering collimation geometries...')
        return count*len(pinholes)**2


    def on_execute(self, button: Gtk.Button):
        if button.get_label() == 'Execute':
            pinholesizes = [float(x[0]) for x in self.builder.get_object('pinhole_store') if x[0]]
            spacers = [float(x[0]) for x in self.builder.get_object('spacers_store') if x[0]]
            self.instrument.config['gui']['optimizegeometry']['pinholes'] = pinholesizes
            self.instrument.config['gui']['optimizegeometry']['spacers'] = spacers
            mindist_l1 = self.builder.get_object('l1baselength_adjustment').get_value()
            mindist_l2 = self.builder.get_object('l2baselength_adjustment').get_value()
            wavelength = self.builder.get_object('wavelength_adjustment').get_value()
            sealringwidth = self.builder.get_object('sealingringwidth_adjustment').get_value()
            sd = self.builder.get_object('distance_sd_adjustment').get_value()
            lbs = self.builder.get_object('distance_dbs_adjustment').get_value()
            ls = self.builder.get_object('distance_ph3s_adjustment').get_value()
            self.limits_samplesize = (
                self.builder.get_object('diameter_sample_min_adjustment').get_value(),
                self.builder.get_object('diameter_sample_max_adjustment').get_value()
            )
            self.limits_beamstopsize = (
                self.builder.get_object('diameter_beamstop_min_adjustment').get_value(),
                self.builder.get_object('diameter_beamstop_max_adjustment').get_value()
            )
            self.limit_l1min = self.builder.get_object('min_l1_adjustment').get_value()
            self.limit_l2min = self.builder.get_object('min_l2_adjustment').get_value()
            self.pinholegenerator = PinholeConfiguration.enumerate(
                    spacers, pinholesizes, ls, lbs, sd, mindist_l1, mindist_l2, sealringwidth, wavelength)
            self.builder.get_object('results_store').clear()
            button.set_label('Stop')
            button.get_image().set_from_icon_name('gtk-stop', Gtk.IconSize.BUTTON)
            self.set_sensitive(False, 'Filtering possible pinhole configurations',
                               ['inputgrid1', 'spacers_treeview', 'pinholes_treeview', 'inputgrid2', 'inputgrid3'])
            self.builder.get_object('work_progress').show()
            self.builder.get_object('work_progress').set_fraction(0)
            self.workdone = 0
            self.worksize = self.estimate_worksize(spacers, pinholesizes, mindist_l1, mindist_l2, sealringwidth)
            if self.worksize is not None:
                self._idle_handler = GLib.idle_add(self._idle_func)
        else:
            self.end_work()

    def on_treeview_keypress(self, treeview: Gtk.TreeView, event: Gdk.EventKey):
        if event.get_keyval()[1] in [Gdk.KEY_Delete, Gdk.KEY_KP_Delete, Gdk.KEY_BackSpace]:
            model, selectediter = treeview.get_selection().get_selected()
            if (selectediter is not None) and (model[selectediter] != ''):
                model.remove(selectediter)
                self.sort_and_tidy_model(treeview)
        return False

    def end_work(self):
        button= self.builder.get_object('execute_button')
        if self._idle_handler is not None:
            GLib.source_remove(self._idle_handler)
        self._idle_handler = None
        button.set_label('Execute')
        button.get_image().set_from_icon_name('system-run', Gtk.IconSize.BUTTON)
        self.builder.get_object('work_progress').hide()
        self.builder.get_object('work_progress').set_fraction(0)
        self.set_sensitive(True)
        self.limit_l2min = None
        self.limit_l1min = None
        self.worksize = None
        self.workdone = None
        self.limits_samplesize = None
        self.limits_beamstopsize = None
        self.pinholegenerator = None
