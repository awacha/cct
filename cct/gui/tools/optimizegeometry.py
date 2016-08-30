import logging

from gi.repository import Gtk, Gdk

from ..core.toolwindow import ToolWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class OptimizeGeometry(ToolWindow):
    def __init__(self, gladefile, toplevelname, instrument, windowtitle, *args, **kwargs):
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

    def on_copy_as_html(self, button: Gtk.Button):
        pass

    def on_spacers_store_row_changed(self, spacersstore: Gtk.ListStore, path: Gtk.TreePath, it: Gtk.TreeIter):
        pass

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

    def on_execute(self, button: Gtk.Button):
        pinholesizes = [float(x[0]) for x in self.builder.get_object('pinhole_store') if x[0]]
        spacers = [float(x[0]) for x in self.builder.get_object('spacers_store') if x[0]]
        self.instrument.config['gui']['optimizegeometry']['pinholes'] = pinholesizes
        self.instrument.config['gui']['optimizegeometry']['spacers'] = spacers
        pass

    def on_treeview_keypress(self, treeview: Gtk.TreeView, event: Gdk.EventKey):
        if event.get_keyval()[1] in [Gdk.KEY_Delete, Gdk.KEY_KP_Delete, Gdk.KEY_BackSpace]:
            model, selectediter = treeview.get_selection().get_selected()
            if (selectediter is not None) and (model[selectediter] != ''):
                model.remove(selectediter)
                self.sort_and_tidy_model(treeview)
        return False
