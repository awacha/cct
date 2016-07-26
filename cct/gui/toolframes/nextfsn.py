from ..core.toolframe import ToolFrame


class NextFSN(ToolFrame):
    def _init_gui(self, *args):
        self._fsconnections = [
            self._instrument.services['filesequence'].connect('nextfsn-changed', self.on_nextfsn),
            self._instrument.services['filesequence'].connect('lastfsn-changed', self.on_nextfsn),
        ]
        self.update_prefixselector()
        self.on_nextfsn(self._instrument.services['filesequence'],
                        sorted(list(self._instrument.services['filesequence'].get_prefixes()))[0], 0)

    def update_prefixselector(self, prefix=None):
        selector = self._builder.get_object('prefix_selector')
        if prefix is not None:
            if prefix in [x[0] for x in selector.get_model()]:
                return
        prevselected = selector.get_active_text()
        selector.remove_all()
        for i, prf in enumerate(sorted(self._instrument.services['filesequence'].get_prefixes())):
            selector.append_text(prf)
            if prf == prevselected:
                selector.set_active(i)
        if selector.get_active_text() is None:
            selector.set_active(0)

    def on_nextfsn(self, filesequence, prefix, nextfsn):
        self._builder.get_object('lastprefix_label').set_text(prefix)
        self._builder.get_object('lastlastfsn_label').set_text(
            str(self._instrument.services['filesequence'].get_lastfsn(prefix)))
        self._builder.get_object('lastnextfsn_label').set_text(
            str(self._instrument.services['filesequence'].get_nextfreefsn(prefix, acquire=False)))
        if self._builder.get_object('prefix_selector').get_active_text() == prefix:
            self.on_prefix_selector_changed(self._builder.get_object('prefix_selector'))

    def on_prefix_selector_changed(self, selector):
        self._builder.get_object('lastfsn_label').set_text(
            str(self._instrument.services['filesequence'].get_lastfsn(selector.get_active_text())))
        self._builder.get_object('nextfsn_label').set_text(
            str(self._instrument.services['filesequence'].get_nextfreefsn(selector.get_active_text(), acquire=False)))
