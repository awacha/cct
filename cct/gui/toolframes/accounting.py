from ..core.toolframe import ToolFrame


class AccountingFrame(ToolFrame):
    def _init_gui(self, *args):
        self._builder.get_object('operatorname_label').set_text(self._instrument.accounting.get_user().username)
        self._builder.get_object('projectid_entry').set_text(self._instrument.accounting.get_project().projectid)
        self._builder.get_object('proposername_entry').set_text(self._instrument.accounting.get_project().proposer)
        self._builder.get_object('projectname_entry').set_text(self._instrument.accounting.get_project().projectname)
        sel = self._builder.get_object('privileges_selector')
        sel.remove_all()
        for pl in self._instrument.accounting.get_accessible_privlevels_str():
            sel.append_text(pl)
        sel.set_active(0)

    def on_entry_changed(self, entry):
        self._builder.get_object('apply_button').set_visible(True)

    def on_apply(self, button):
        self._instrument.accounting.new_project(self._builder.get_object('projectid_entry').get_text(),
                                                self._builder.get_object('projectname_entry').get_text(),
                                                self._builder.get_object('proposername_entry').get_text())
        button.set_visible(False)

    def on_privileges_changed(self, selector):
        self._instrument.accounting.set_privilegelevel(selector.get_active_text())
