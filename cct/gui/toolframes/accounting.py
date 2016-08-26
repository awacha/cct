import logging

from ..core.functions import update_comboboxtext_choices
from ..core.toolframe import ToolFrame
from ...core.services.accounting import Accounting, PrivilegeLevel

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AccountingFrame(ToolFrame):
    def __init__(self, *args, **kwargs):
        self._acctconn = []
        self._projectid_changed_disable = None
        self._updating_privilegeselector = False
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        self.on_user_changed(self.instrument.services['accounting'],
                             self.instrument.services['accounting'].get_user())
        self.on_accounting_privlevel_changed(self.instrument.services['accounting'],
                                             self.instrument.services['accounting'].get_privilegelevel())
        self._acctconn = [self.instrument.services['accounting'].connect('project-changed', self.on_project_changed),
                          self.instrument.services['accounting'].connect('privlevel-changed',
                                                                         self.on_accounting_privlevel_changed),
                          self.instrument.services['accounting'].connect('user-changed', self.on_user_changed)]
        self.on_project_changed(self.instrument.services['accounting'])

    def cleanup(self):
        for c in self._acctconn:
            self.instrument.services['accounting'].disconnect(c)
        self._acctconn = []
        return super().cleanup()

    def on_projectid_changed(self, comboboxtext):
        if self._projectid_changed_disable:
            return
        pid = comboboxtext.get_active_text()
        if self.instrument.services['accounting'].get_project().projectid != pid:
            self.instrument.services['accounting'].select_project(pid)

    def on_project_changed(self, accountingservice: Accounting):
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
            self._projectid_changed_disable = False

    def on_privileges_changed(self, selector):
        if not self._updating_privilegeselector:
            self.instrument.services['accounting'].set_privilegelevel(selector.get_active_text())
        return False

    def on_user_changed(self, accountingservice: Accounting, user):
        self.builder.get_object('operatorname_label').set_text(
            user.username)

    def on_accounting_privlevel_changed(self, accountingservice: Accounting, privlevel: PrivilegeLevel):
        logger.debug('Updating privileges selector. Current privilege level: {}'.format(privlevel))
        self._updating_privilegeselector = True
        try:
            update_comboboxtext_choices(
                self.builder.get_object('privileges_selector'),
                accountingservice.get_accessible_privlevels_str(),
                set_to=privlevel.name)
        finally:
            self._updating_privilegeselector = False
