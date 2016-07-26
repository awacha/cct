from ..core.toolframe import ToolFrame
from ...core.instrument.privileges import PrivilegeLevel

class AccountingFrame(ToolFrame):
    def _init_gui(self, *args):
        sel = self._builder.get_object('privileges_selector')
        sel.remove_all()
        for i, pl in enumerate(self._instrument.services['accounting'].get_accessible_privlevels_str()):
            sel.append_text(pl)
            if PrivilegeLevel.get_priv(pl) == self._instrument.services['accounting'].get_privilegelevel():
                sel.set_active(i)
        if sel.get_active() is None:
            sel.set_active(0)
        self._instrument.services['accounting'].connect('project-changed', self.on_project_changed)
        self.on_project_changed(self._instrument.services['accounting'])

    def on_projectid_changed(self, comboboxtext):
        if hasattr(self, '_projectid_changed_disable'):
            return
        pid = comboboxtext.get_active_text()
        if self._instrument.services['accounting'].get_project().projectid != pid:
            self._instrument.services['accounting'].select_project(pid)

    def on_project_changed(self, accounting):
        self._builder.get_object('operatorname_label').set_text(
            self._instrument.services['accounting'].get_user().username)
        pidsel = self._builder.get_object('projectid_selector')
        self._projectid_changed_disable = True
        pidsel.remove_all()
        for i, project in enumerate(self._instrument.services['accounting'].get_projectids()):
            pidsel.append_text(project)
            if project == self._instrument.services['accounting'].get_project().projectid:
                pidsel.set_active(i)
        self._builder.get_object('proposer_label').set_text(
            self._instrument.services['accounting'].get_project().proposer)
        self._builder.get_object('projectname_label').set_text(
            self._instrument.services['accounting'].get_project().projectname)
        del self._projectid_changed_disable

    def on_entry_changed(self, entry):
        self._builder.get_object('apply_button').set_visible(True)

    def on_apply(self, button):
        self._instrument.services['accounting'].new_project(self._builder.get_object('projectid_entry').get_text(),
                                                            self._builder.get_object('projectname_entry').get_text(),
                                                            self._builder.get_object('proposername_entry').get_text())
        button.set_visible(False)

    def on_privileges_changed(self, selector):
        self._instrument.services['accounting'].set_privilegelevel(selector.get_active_text())
