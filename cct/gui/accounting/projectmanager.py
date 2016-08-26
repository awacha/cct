from gi.repository import Gtk

from ..core.dialogs import question_message
from ..core.toolwindow import ToolWindow
from ...core.instrument.privileges import PRIV_PROJECTMAN, PrivilegeError


class ProjectManager(ToolWindow):
    privlevel = PRIV_PROJECTMAN

    def init_gui(self, *args, **kwargs):
        self.builder.get_object('apply_button').set_sensitive(False)
        self.update_gui()

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self.update_gui()

    def update_gui(self, select_pid=None):
        model = self.builder.get_object('projectidstore')
        model.clear()
        if select_pid is None:
            select_pid = self.instrument.services['accounting'].get_project().projectid
        iter_to_select = None
        for pid in sorted(self.instrument.services['accounting'].get_projectids()):
            it = model.append((pid,))
            if pid == select_pid:
                iter_to_select = it
        if iter_to_select is None:
            iter_to_select = model.get_iter_first()
        self.builder.get_object('project-selection').select_iter(iter_to_select)
        self.builder.get_object('apply_button').set_sensitive(False)

    def on_editable_changed(self, widget):
        self.builder.get_object('apply_button').set_sensitive(True)

    def on_selection_changed(self, selection):
        ab = self.builder.get_object('apply_button')
        if ab.get_sensitive():
            if question_message(self.widget, 'Save changes?',
                                'Do you want to save the changes you made to this project?'):
                self.on_apply(ab)
        model, iterator = selection.get_selected()
        if iterator is None:
            return
        projectid = model[iterator][0]
        self.builder.get_object('projectname_entry').set_text(
            self.instrument.services['accounting'].get_project(projectid).projectname)
        self.builder.get_object('proposer_entry').set_text(
            self.instrument.services['accounting'].get_project(projectid).proposer)
        self.builder.get_object('apply_button').set_sensitive(False)

    def on_apply(self, button):
        projectname = self.builder.get_object('projectname_entry').get_text()
        proposer = self.builder.get_object('proposer_entry').get_text()
        model, iterator = self.builder.get_object('project-selection').get_selected()
        if iterator is None:
            return
        projectid = model[iterator][0]
        self.instrument.services['accounting'].new_project(projectid, projectname, proposer)
        button.set_sensitive(False)

    def on_addproject(self, button):
        dlg = Gtk.Dialog(title='New project', parent=self.widget, modal=True, destroy_with_parent=True)
        dlg.add_buttons('Ok', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL)
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
        if dlg.run() == Gtk.ResponseType.OK:
            try:
                project = self.instrument.services['accounting'].new_project(entry.get_text(), '', '')
            except PrivilegeError as exc:
                # should not happen, but who knows...
                self.error_message('Cannot add new project: insufficient privileges')
            else:
                self.update_gui(project.projectid)
        dlg.destroy()

    def on_removeproject(self, button):
        model, iterator = self.builder.get_object('project-selection').get_selected()
        if iterator is None:
            return
        projectid = model[iterator][0]
        try:
            self.instrument.services['accounting'].delete_project(projectid)
        except ValueError:
            self.error_message('Cannot delete the current project')
        self.update_gui()
