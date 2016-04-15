from gi.repository import Gtk

from ..core.toolwindow import ToolWindow, question_message, error_message
from ...core.instrument.privileges import PRIV_PROJECTMAN


class ProjectManager(ToolWindow):
    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True

    def _init_gui(self, *args):
        self._privlevel = PRIV_PROJECTMAN
        self._update_gui()

    def _update_gui(self):
        model = self._builder.get_object('projectidstore')
        model.clear()
        for pid in sorted(self._instrument.accounting.get_projectids()):
            model.append((pid,))
        self._builder.get_object('project-selection').select_iter(model.get_iter_first())
        self._builder.get_object('apply_button').set_sensitive(False)

    def on_editable_changed(self, widget):
        self._builder.get_object('apply_button').set_sensitive(True)

    def on_selection_changed(self, selection):
        if self._builder.get_object('apply_button').get_sensitive():
            if question_message(self._window, 'Save changes?'):
                self.on_apply(self._builder.get_object('apply_button'))
            self._builder.get_object('apply_button').set_sensitive(False)
        model, iterator = selection.get_selected()
        if iterator is None:
            return
        projectid = model[iterator][0]
        self._builder.get_object('projectname_entry').set_text(
            self._instrument.accounting.get_project(projectid).projectname)
        self._builder.get_object('proposer_entry').set_text(self._instrument.accounting.get_project(projectid).proposer)
        self._builder.get_object('apply_button').set_sensitive(False)

    def on_apply(self, button):
        projectname = self._builder.get_object('projectname_entry').get_text()
        proposer = self._builder.get_object('proposer_entry').get_text()
        model, iterator = self._builder.get_object('project-selection').get_selected()
        if iterator is None:
            return
        projectid = model[iterator][0]
        self._instrument.accounting.new_project(projectid, projectname, proposer)
        button.set_sensitive(False)

    def on_addproject(self, button):
        dlg = Gtk.Dialog('New project', self._window, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                         ['Ok', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL])
        b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        l = Gtk.Label('Project ID:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.FILL)
        l.set_margin_right(5)
        b.pack_start(l, False, True, 0)
        entry = Gtk.Entry()
        entry.set_text('')
        b.pack_start(entry, True, True, 0)
        entry.set_placeholder_text('The name of the new project...')
        dlg.vbox.pack_start(b, True, True, 0)
        dlg.foreach(lambda x: x.show_all())
        # dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            try:
                project=self._instrument.accounting.new_project(entry.get_text(), '', '')
            except Exception as exc:
                error_message(dlg, 'Cannot add new project', str(exc))
        dlg.destroy()
        self._update_gui()

    def on_removeproject(self, button):
        model, iterator = self._builder.get_object('project-selection').get_selected()
        if iterator is None:
            return
        projectid=model[iterator][0]
        try:
            self._instrument.accounting.delete_project(projectid)
        except AssertionError:
            error_message(self._window, 'Cannot delete current project')
        self._update_gui()