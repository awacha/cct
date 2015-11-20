import logging

from gi.repository import Gtk

from ..core.toolwindow import ToolWindow, info_message
from ...core.services.accounting import PrivilegeLevel

logger=logging.getLogger()
logger.setLevel(logging.DEBUG)

class EditConfig(ToolWindow):
    def _init_gui(self, *args):
        self._changedpaths=[]
        self._privlevel = PrivilegeLevel.SUPERUSER
        tv=self._builder.get_object('configtreeview')
        tc=Gtk.TreeViewColumn('Label', Gtk.CellRendererText(), text=0)
        tv.append_column(tc)
        tc=Gtk.TreeViewColumn('Changed', Gtk.CellRendererPixbuf(), icon_name=1)
        tv.append_column(tc)

    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        self._update_gui()

    def _update_gui(self):
        model=self._builder.get_object('configtreestore')
        model.clear()
        parents=[None]
        def _add_children(config):
            for c in sorted(config.keys()):
                it=model.append(parents[-1], (c,''))
                if isinstance(config[c],dict):
                    parents.append(it)
                    _add_children(config[c])
            del parents[-1]
        _add_children(self._instrument.config)
        try:
            del self._selectioniter
        except AttributeError:
            pass
        self._builder.get_object('configtreeview').get_selection().select_iter(model.get_iter_first())

    def on_apply(self, button):
        self.note_change()
        for path, value in self._changedpaths:
            dic=self._instrument.config
            for p in path[:-1]:
                dic=dic[p]
            dic[path[-1]]=value
            logger.debug('Updated config element %s. New value: %s.'%('::'.join(['ROOT']+path),str(value)))
        self._changedpaths=[]
        model=self._builder.get_object('configtreestore')
        def reset_changed_status(model, path, it):
            model[it][1]=''
        model.foreach(reset_changed_status)
        self.on_save(button)

    def note_change(self):
        model, it=self._builder.get_object('configtreeview').get_selection().get_selected()
        if it is None:
            return
        if hasattr(self, '_selectioniter'):
            if model[self._selectioniter][1]=='dialog-information':
                # save the updated value of the previously selected config item.
                entry=self._builder.get_object('entry_stack').get_visible_child()
                if isinstance(entry, Gtk.SpinButton) and entry.get_digits()==0:
                    newvalue=entry.get_value_as_int()
                elif isinstance(entry, Gtk.SpinButton):
                    newvalue=entry.get_value()
                elif isinstance(entry, Gtk.Entry):
                    newvalue=entry.get_text()
                elif isinstance(entry, Gtk.Switch):
                    newvalue=entry.get_active()
                elif isinstance(entry, Gtk.Label):
                    newvalue=None
                else:
                    raise NotImplementedError
                if newvalue is not None:
                    self._changedpaths.append((self._selectionpath, newvalue))

    def on_select(self, treeviewselection):
        model, it=treeviewselection.get_selected()
        if it is None:
            return
        self.note_change()
        path=[]
        parent=it
        while parent is not None:
            path.append(parent)
            parent=model.iter_parent(parent)
        self._selectionpath=[model[i][0] for i in reversed(path)]
        self._selectioniter=it
        val=self._instrument.config
        for name in self._selectionpath:
            val=val[name]
        iconname_before=model[it][1]
        self._builder.get_object('path_label').set_text('::'.join(['ROOT']+self._selectionpath[:-1]))
        self._builder.get_object('name_label').set_text(model[it][0])
        self._builder.get_object('type_label').set_text(val.__class__.__name__)
        if isinstance(val, str):
            self._builder.get_object('entry_stack').set_visible_child_name('str')
            self._builder.get_object('str_entry').set_text(val)
        elif isinstance(val, int):
            self._builder.get_object('entry_stack').set_visible_child_name('int')
            self._builder.get_object('int_entry_adjustment').set_value(val)
        elif isinstance(val, float):
            self._builder.get_object('entry_stack').set_visible_child_name('float')
            self._builder.get_object('float_entry_adjustment').set_value(val)
        elif isinstance(val, bool):
            self._builder.get_object('entry_stack').set_visible_child_name('bool')
            self._builder.get_object('bool_entry').set_active(val)
        elif isinstance(val, dict):
            self._builder.get_object('entry_stack').set_visible_child_name('dict')
        else:
            self._builder.get_object('entry_stack').set_visible_child_name('notimplemented')
            self._builder.get_object('other_display').set_text(str(val))
        # updating the entries trigger the on_edit callback, even before the user did anything to the input field.
        model[it][1]=iconname_before

    def on_edit(self, widget):
        model, it=self._builder.get_object('configtreeview').get_selection().get_selected()
        model[it][1]='dialog-information'

    def on_switch_state_set(self, switch, state):
        self.on_edit(switch)
        return False

    def on_save(self, button):
        self._instrument.save_state()
        self._update_gui()
        info_message(self._window, 'Config saved to %s'%self._instrument.configfile)
