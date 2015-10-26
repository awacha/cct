from ..core.toolwindow import ToolWindow
from gi.repository import Gtk

class EditConfig(ToolWindow):
    def _init_gui(self, *args):
        tv=self._builder.get_object('configtreeview')
        tc=Gtk.TreeViewColumn('Label', Gtk.CellRendererText(), text=0)
        tv.append_column(tc)
        tv.get_selection().connect('changed', on_select)

    def on_map(self, window):
        model=self._builder.get_object('configtreestore')
        model.clear()
        parents=[None]
        def _add_children(config):
            for c in sorted(config.keys()):
                it=model.append(parents[-1], (c,))
                if isinstance(config[c],dict):
                    parents.append(it)
                    _add_children(config[c])
            del parents[-1]
        _add_children(self._instrument.config)

    def on_apply(self, button):
        pass

    def on_select(self, treeviewselection):
        model, it=treeviewselection.get_selected()


