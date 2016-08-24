import logging
from operator import setitem

from gi.repository import Gtk

from ..core.dialogs import info_message
from ..core.toolwindow import ToolWindow
from ...core.instrument.privileges import PRIV_SUPERUSER

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class EditConfig(ToolWindow):
    privlevel = PRIV_SUPERUSER

    def __init__(self, *args, **kwargs):
        self._changedpaths = []
        self._selectioniter = None
        self._selectionpath = None
        self._updating_edit_field = False
        super().__init__(*args, **kwargs)

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self.update_gui()

    def update_gui(self):
        model = self.builder.get_object('configtreestore')
        model.clear()
        parents = [None]

        def _add_children(config, parents):
            for c in sorted(config.keys()):
                it = model.append(parents[-1], (c, ''))
                if isinstance(config[c], dict):
                    parents.append(it)
                    _add_children(config[c], parents)
            del parents[-1]

        _add_children(self.instrument.config, parents)
        self._selectioniter = None  # on_select() will update this promptly
        self.builder.get_object('configtreeview').get_selection().select_iter(model.get_iter_first())

    def on_apply(self, button):
        self.mark_change()
        for path, value in self._changedpaths:
            dic = self.instrument.config
            for p in path[:-1]:
                dic = dic[p]
            dic[path[-1]] = value
            logger.debug('Updated config element %s. New value: %s.' % ('::'.join(['ROOT'] + path), str(value)))
        self._changedpaths = []
        model = self.builder.get_object('configtreestore')
        # reset the "changed" flag.
        model.foreach(lambda model, path, it: setitem(model[it], 1, ''))
        self.on_save(button)

    def mark_change(self):
        model, it = self.builder.get_object('configtreeview').get_selection().get_selected()
        if it is None:
            return
        if self._selectioniter is not None:
            if model[self._selectioniter][1] == 'dialog-information':
                # save the updated value of the previously selected config item.
                entry = self.builder.get_object('entry_stack').get_visible_child()
                if isinstance(entry, Gtk.SpinButton) and entry.get_digits() == 0:
                    newvalue = entry.get_value_as_int()
                elif isinstance(entry, Gtk.SpinButton):
                    newvalue = entry.get_value()
                elif isinstance(entry, Gtk.Entry):
                    newvalue = entry.get_text()
                elif isinstance(entry, Gtk.Switch):
                    newvalue = entry.get_active()
                elif isinstance(entry, Gtk.Label):
                    newvalue = None
                else:
                    raise TypeError(entry)
                if newvalue is not None:
                    self._changedpaths.append((self._selectionpath, newvalue))

    def on_select(self, treeviewselection: Gtk.TreeSelection):
        model, it = treeviewselection.get_selected()
        if it is None:
            return
        # mark the change.
        self.mark_change()
        path = []  # not a TreePath, just a list of node names in the config hierarchy.
        parent = it
        while parent is not None:
            path.append(parent)
            parent = model.iter_parent(parent)
        self._selectionpath = [model[i][0] for i in reversed(path)]
        self._selectioniter = it
        # get the config value for the currently selected node.
        val = self.instrument.config
        for name in self._selectionpath:
            val = val[name]
        self._updating_edit_field = True
        try:
            self.builder.get_object('path_label').set_text('::'.join(['ROOT'] + self._selectionpath[:-1]))
            self.builder.get_object('name_label').set_text(model[it][0])
            self.builder.get_object('type_label').set_text(val.__class__.__name__)
            if isinstance(val, str):
                self.builder.get_object('entry_stack').set_visible_child_name('str')
                self.builder.get_object('str_entry').set_text(val)
            elif isinstance(val, int):
                self.builder.get_object('entry_stack').set_visible_child_name('int')
                self.builder.get_object('int_entry_adjustment').set_value(val)
            elif isinstance(val, float):
                self.builder.get_object('entry_stack').set_visible_child_name('float')
                self.builder.get_object('float_entry_adjustment').set_value(val)
            elif isinstance(val, bool):
                self.builder.get_object('entry_stack').set_visible_child_name('bool')
                self.builder.get_object('bool_entry').set_active(val)
            elif isinstance(val, dict):
                self.builder.get_object('entry_stack').set_visible_child_name('dict')
            else:
                self.builder.get_object('entry_stack').set_visible_child_name('notimplemented')
                self.builder.get_object('other_display').set_text(str(val))
        finally:
            self._updating_edit_field = False

    def on_edit(self, widget):
        if self._updating_edit_field:
            # avoid erroneously flagging the config value as changed when the edit field is updated on selection.
            return False
        model, it = self.builder.get_object('configtreeview').get_selection().get_selected()
        model[it][1] = 'dialog-information'

    def on_switch_state_set(self, switch, state):
        self.on_edit(switch)
        return False

    def on_save(self, button):
        self.instrument.save_state()
        self.update_gui()
        info_message(self.widget, 'Config saved', 'Config saved to ' + self.instrument.configfile)
