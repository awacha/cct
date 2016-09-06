import logging
import time
from concurrent.futures import ProcessPoolExecutor, Future
from typing import Optional

from gi.repository import Gtk, Gdk, GLib

from .estimateworksize import estimate_worksize_C
from .pinholeconfiguration import PinholeConfiguration
from ...core.toolwindow import ToolWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
        self.html_being_built = ""
        super().__init__(gladefile, toplevelname, instrument, windowtitle, *args, **kwargs)
        self._executor = ProcessPoolExecutor()
        self.lastpulse = 0

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

    def row_to_html(self, model: Gtk.ListStore, path: Gtk.TreePath, it: Gtk.TreeIter, treeview: Gtk.TreeView):
        self.html_being_built += "  <tr>\n"
        for c in treeview.get_columns():
            self.html_being_built += "    <td>" + self.cell_data_func(c, None, model, it, None) + "</td>\n"
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
        clipboard = Gtk.Clipboard.get_default(Gdk.Display.get_default())
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

    # noinspection PyMethodMayBeStatic
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
        if isinstance(self.worksize, Future):
            if self.worksize.done():
                self.worksize = self.worksize.result()
                return True
            if time.monotonic() - self.lastpulse > 0.3:
                self.builder.get_object('work_progress').set_text('Estimating work size...')
                self.builder.get_object('work_progress').pulse()
                self.lastpulse = time.monotonic()
            return True

        if self.pinholegenerator is None:
            return False
        try:
            pc = next(self.pinholegenerator)
            self.workdone += 1
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
        if ((pc.Dbs >= self.limits_beamstopsize[0]) and (pc.Dbs <= self.limits_beamstopsize[1]) and
                (pc.Dsample >= self.limits_samplesize[0]) and (pc.Dsample <= self.limits_samplesize[1]) and
                (pc.l1 >= self.limit_l1min) and (pc.l2 >= self.limit_l2min)):
            # the pinhole configuration matches our criteria
            model = self.builder.get_object('results_store')
            logger.debug(
                'New pinhole configuration: ' + str(pc) + ' L1: {}, L2: {}'.format(pc.l1_elements, pc.l2_elements))
            model.append([pc, pc.l1, pc.l2,
                          ', '.join(['{:.0f}'.format(e) for e in pc.l1_elements]),
                          ', '.join(['{:.0f}'.format(e) for e in pc.l2_elements]),
                          pc.sd, pc.D1, pc.D2, pc.alpha * 1000, pc.Dsample, pc.Dbs, pc.qmin, pc.dmax, pc.Rgmax,
                          pc.dspheremax, pc.D3, pc.intensity, pc.dominant_constraint])
        self.builder.get_object('work_progress').set_text(
            'Filtering possible geometries: {:d}/{:d} done'.format(self.workdone, self.worksize))
        self.builder.get_object('work_progress').set_fraction(self.workdone / self.worksize)
        return True

    # noinspection PyMethodMayBeStatic
    def cell_data_func(self, treeviewcolumn: Gtk.TreeViewColumn, cellrenderer: Optional[Gtk.CellRendererText],
                       model: Gtk.ListStore, it: Gtk.TreeIter, data):
        pc = model[it][0]
        colid = treeviewcolumn.get_sort_column_id()
        if colid == 1:
            text = '{:.0f}'.format(pc.l1)
        elif colid == 2:
            text = '{:.0f}'.format(pc.l2)
        elif colid == 3:
            text = ', '.join(['{:.0f}'.format(e) for e in pc.l1_elements])
        elif colid == 4:
            text = ', '.join(['{:.0f}'.format(e) for e in pc.l2_elements])
        elif colid == 5:
            text = '{:.01f}'.format(pc.sd)
        elif colid == 6:
            text = '{:.0f}'.format(pc.D1)
        elif colid == 7:
            text = '{:.0f}'.format(pc.D2)
        elif colid == 8:
            text = '{:.2f}'.format(pc.alpha * 1000)
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
                               ['inputframe'])
            self.builder.get_object('work_progress').show()
            self.builder.get_object('work_progress').set_fraction(0)
            self.workdone = 0
            self.worksize = self._executor.submit(estimate_worksize_C, spacers, pinholesizes, sealringwidth)
            state = {'pinholesizes': pinholesizes,
                     'spacers': spacers,
                     'mindist_l1': mindist_l1,
                     'mindist_l2': mindist_l2,
                     'wavelength': wavelength,
                     'sealringwidth': sealringwidth,
                     'sd': sd,
                     'lbs': lbs,
                     'ls': ls,
                     'limits_samplesize': self.limits_samplesize,
                     'limits_beamstopsize': self.limits_beamstopsize,
                     'limit_l1min': self.limit_l1min,
                     'limit_l2min': self.limit_l2min
                     }
            self.instrument.config['gui']['optimizegeometry'].update(state)
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
        button = self.builder.get_object('execute_button')
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
