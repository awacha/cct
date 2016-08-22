from ..core.functions import update_comboboxtext_choices
from ..core.toolframe import ToolFrame
from ...core.services.accounting import Accounting


class AccountingFrame(ToolFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._acctconn = None
        self._projectid_changed_disable = None

    def init_gui(self, *args):
        update_comboboxtext_choices(
            self.builder.get_object('privileges_selector'),
            self.instrument.services['accounting'].get_accessible_privlevels_str(),
            set_to=str(self.instrument.services['accounting'].get_privilegelevel()))
        self._acctconn = self.instrument.services['accounting'].connect('project-changed', self.on_project_changed)
        self.on_project_changed(self.instrument.services['accounting'])

    def cleanup(self):
        if self._acctconn is not None:
            self.instrument.services['accounting'].disconnect(self._acctconn)
            self._acctconn = None
        return super().cleanup()

    def on_projectid_changed(self, comboboxtext):
        if self._projectid_changed_disable:
            return
        pid = comboboxtext.get_active_text()
        if self.instrument.services['accounting'].get_project().projectid != pid:
            self.instrument.services['accounting'].select_project(pid)

    def on_project_changed(self, accountingservice: Accounting):
        self.builder.get_object('operatorname_label').set_text(
            accountingservice.get_user().username)
        pidsel = self.builder.get_object('projectid_selector')
        self._projectid_changed_disable = True
        try:
            proj = accountingservice.get_project()
            update_comboboxtext_choices(pidsel, sorted(self.instrument.services['accounting'].get_projectids()),
                                        set_to=proj.projectid)
            self.builder.get_object('proposer_label').set_text(
                proj.proposer)
            self.builder.get_object('projectname_label').set_text(
                proj.projectname)
        finally:
            del self._projectid_changed_disable

    def on_privileges_changed(self, selector):
        self.instrument.services['accounting'].set_privilegelevel(selector.get_active_text())
