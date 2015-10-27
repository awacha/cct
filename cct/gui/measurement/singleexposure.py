from ..core.toolwindow import ToolWindow, error_message

class SingleExposure(ToolWindow):
    def _init_gui(self, *args):
        pass

    def _break_connections(self):
        try:
            self._instrument.samplestore.disconnect(self._sampleconnections)
        except AttributeError:
            pass

    def on_map(self, window):
        self._break_connections()
        self._sampleconnections=self._instrument.samplestore.connect('list-changed', self.on_samplelist_changed)
        self.on_samplelist_changed(self._instrument.samplestore)
        prefixselector=self._builder.get_object('prefixselector')
        prefixselector.remove_all()
        for i,p in enumerate(sorted(self._instrument.filesequence.get_prefixes())):
            prefixselector.append_text(p)
            if p==self._instrument.config['path']['prefixes']['tst']:
                prefixselector.set_active(i)
        self.on_maskoverride_toggled(self._builder.get_object('mask_checkbutton'))
        self.on_samplecheck_toggled(self._builder.get_object('samplename_check'))

    def on_unmap(self, window):
        self._break_connections()

    def on_samplecheck_toggled(self, togglebutton):
        self._builder.get_object('sampleselector').set_sensitive(togglebutton.get_active())

    def on_maskoverride_toggled(self, togglebutton):
        self._builder.get_object('maskchooserbutton').set_sensitive(togglebutton.get_active())

    def on_start(self, button):
        if button.get_label()=='Start':
            if self._builder.get_object('samplename_check').get_active():
                samplename=self._builder.get_object('sampleselector').get_active_text()
                self._instrument.samplestore.set_active(samplename)
                sample=self._instrument.get_active()
            else:
                sample=None
            prefix=self._builder.get_object('prefixselector').get_active_text()
            exptime=self._builder.get_object('exptime_spin').get_value()
            nimages=self._builder.get_object('nimages_spin').get_value_as_int()
            expdelay=self._builder.get_object('expdelay_spin').get_value()

            self._builder.get_object('progressframe').show_all()
            self._builder.get_object('progressframe').set_visible(True)
            self._builder.get_object('nimages_progress').set_visible(nimages>1)

            button.set_label('Stop')
            self._make_insensitive('Exposure is running', ['entrygrid', 'close_button'])
        else:
            button.set_label('Start')
            self._builder.get_object('progressframe').set_visible(False)
            self._make_sensitive()
            self._window.resize(1,1)

    def on_samplelist_changed(self, samplestore):
        sampleselector=self._builder.get_object('sampleselector')
        previously_selected=sampleselector.get_active_text()
        if previously_selected is None:
            previously_selected = samplestore.get_active_name()
        sampleselector.remove_all()
        for i,sample in enumerate(sorted(samplestore, key=lambda x:x.title)):
            sampleselector.append_text(sample.title)
            if sample.title==previously_selected:
                sampleselector.set_active(i)

    def on_nimages_changed(self, spinbutton):
        self._builder.get_object('expdelay_spin').set_sensitive(spinbutton.get_value_as_int()>1)