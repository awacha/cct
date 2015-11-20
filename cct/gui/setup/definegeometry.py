from ..core.toolwindow import ToolWindow, question_message, info_message

class DefineGeometry(ToolWindow):
    def _init_gui(self, *args):
        pass

    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        self._update_gui()

    def _update_gui(self):
        conf=self._instrument.config['geometry']
        self._builder.get_object('l0_adjustment').set_value(conf['dist_source_ph1'])
        self._builder.get_object('l1_adjustment').set_value(conf['dist_ph1_ph2'])
        self._builder.get_object('l2_adjustment').set_value(conf['dist_ph2_ph3'])
        self._builder.get_object('ls_adjustment').set_value(conf['dist_ph3_sample'])
        self._builder.get_object('ldval_adjustment').set_value(conf['dist_sample_det'])
        self._builder.get_object('lderr_adjustment').set_value(conf['dist_sample_det.err'])
        self._builder.get_object('lbs_adjustment').set_value(conf['dist_det_beamstop'])
        self._builder.get_object('pinhole1_adjustment').set_value(conf['pinhole_1'])
        self._builder.get_object('pinhole2_adjustment').set_value(conf['pinhole_2'])
        self._builder.get_object('pinhole3_adjustment').set_value(conf['pinhole_3'])
        self._builder.get_object('beamstop_adjustment').set_value(conf['beamstop'])
        self._builder.get_object('beamx_adjustment').set_value(conf['beamposy'])
        self._builder.get_object('beamy_adjustment').set_value(conf['beamposx'])
        self._builder.get_object('pixelsize_adjustment').set_value(conf['pixelsize'])
        self._builder.get_object('wavelengthval_adjustment').set_value(conf['wavelength'])
        self._builder.get_object('wavelengtherr_adjustment').set_value(conf['wavelength.err'])
        self._builder.get_object('description_entry').set_text(conf['description'])
        self._builder.get_object('mask_filechooser').set_filename(conf['mask'])
        self._builder.get_object('apply_button').set_sensitive(False)

    def on_edit(self, widget):
        self._builder.get_object('apply_button').set_sensitive(True)

    def on_apply(self, button):
        conf=self._instrument.config['geometry']
        conf['dist_source_ph1']=self._builder.get_object('l0_adjustment').get_value()
        conf['dist_ph1_ph2']=self._builder.get_object('l1_adjustment').get_value()
        conf['dist_ph2_ph3']=self._builder.get_object('l2_adjustment').get_value()
        conf['dist_ph3_sample']=self._builder.get_object('ls_adjustment').get_value()
        conf['dist_sample_det']=self._builder.get_object('ldval_adjustment').get_value()
        conf['dist_sample_det.err']=self._builder.get_object('lderr_adjustment').get_value()
        conf['dist_det_beamstop']=self._builder.get_object('lbs_adjustment').get_value()
        conf['pinhole_1']=self._builder.get_object('pinhole1_adjustment').get_value()
        conf['pinhole_2']=self._builder.get_object('pinhole2_adjustment').get_value()
        conf['pinhole_3']=self._builder.get_object('pinhole3_adjustment').get_value()
        conf['beamstop']=self._builder.get_object('beamstop_adjustment').get_value()
        conf['beamposy']=self._builder.get_object('beamx_adjustment').get_value()
        conf['beamposx']=self._builder.get_object('beamy_adjustment').get_value()
        conf['pixelsize']=self._builder.get_object('pixelsize_adjustment').get_value()
        conf['wavelength']=self._builder.get_object('wavelengthval_adjustment').get_value()
        conf['wavelength.err']=self._builder.get_object('wavelengtherr_adjustment').get_value()
        conf['description']=self._builder.get_object('description_entry').get_text()
        conf['mask']=self._builder.get_object('mask_filechooser').get_filename()
        self._builder.get_object('apply_button').set_sensitive(False)
        self._instrument.save_state()
        info_message(self._window, 'Configuration saved', 'Saved configuration to file %s'%self._instrument.configfile)

    def on_close(self, widget, event=None):
        if self._builder.get_object('apply_button').get_sensitive():
            if question_message(self._window,'Do you want to save your changes?'):
                self.on_apply(self._builder.get_object('apply_button'))
        ToolWindow.on_close(self,widget, event)
