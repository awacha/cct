from ..core.functions import update_comboboxtext_choices
from ..core.toolframe import ToolFrame


class NextFSN(ToolFrame):
    def __init__(self, *args, **kwargs):
        self._fsconnections = []
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        self._fsconnections = [
            self.instrument.services['filesequence'].connect('nextfsn-changed', self.on_nextfsn),
            self.instrument.services['filesequence'].connect('lastfsn-changed', self.on_nextfsn),
        ]
        self.update_prefixselector()
        self.on_nextfsn(self.instrument.services['filesequence'],
                        sorted(list(self.instrument.services['filesequence'].get_prefixes()))[0], 0)

    def cleanup(self):
        for c in self._fsconnections:
            self.instrument.services['filesequence'].disconnect(c)
        self._fsconnections = []
        super().cleanup()

    def update_prefixselector(self, prefix=None):
        selector = self.builder.get_object('prefix_selector')
        if prefix is not None:
            if prefix in [x[0] for x in selector.get_model()]:
                return
        update_comboboxtext_choices(selector, sorted(self.instrument.services['filesequence'].get_prefixes()))

    def on_nextfsn(self, filesequence, prefix, nextfsn):
        self.builder.get_object('lastprefix_label').set_text(prefix)
        self.builder.get_object('lastlastfsn_label').set_text(
            str(self.instrument.services['filesequence'].get_lastfsn(prefix)))
        self.builder.get_object('lastnextfsn_label').set_text(
            str(self.instrument.services['filesequence'].get_nextfreefsn(prefix, acquire=False)))
        if self.builder.get_object('prefix_selector').get_active_text() == prefix:
            self.on_prefix_selector_changed(self.builder.get_object('prefix_selector'))

    def on_prefix_selector_changed(self, selector):
        self.builder.get_object('lastfsn_label').set_text(
            str(self.instrument.services['filesequence'].get_lastfsn(selector.get_active_text())))
        self.builder.get_object('nextfsn_label').set_text(
            str(self.instrument.services['filesequence'].get_nextfreefsn(selector.get_active_text(), acquire=False)))
