from ..core.dialogs import question_message
from ..core.toolwindow import ToolWindow


class DefineGeometry(ToolWindow):
    def __init__(self, *args, **kwargs):
        self._updating = False
        super().__init__(*args, **kwargs)
        self._original_conf = None

    def init_gui(self, *args, **kwargs):
        pass

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self.update_gui()

    def update_gui(self):
        self._updating = True
        try:
            conf = self.instrument.config['geometry']
            self.builder.get_object('l0_spin').set_value(conf['dist_source_ph1'])
            self.builder.get_object('l0_spin').update()
            self.builder.get_object('l1_spin').set_value(conf['dist_ph1_ph2'])
            self.builder.get_object('l1_spin').update()
            self.builder.get_object('l2_spin').set_value(conf['dist_ph2_ph3'])
            self.builder.get_object('l2_spin').update()
            self.builder.get_object('ls_spin').set_value(conf['dist_ph3_sample'])
            self.builder.get_object('ls_spin').update()
            self.builder.get_object('ldval_spin').set_value(conf['dist_sample_det'])
            self.builder.get_object('ldval_spin').update()
            self.builder.get_object('lderr_spin').set_value(conf['dist_sample_det.err'])
            self.builder.get_object('lderr_spin').update()
            self.builder.get_object('lbs_spin').set_value(conf['dist_det_beamstop'])
            self.builder.get_object('lbs_spin').update()
            self.builder.get_object('pinhole1_spin').set_value(conf['pinhole_1'])
            self.builder.get_object('pinhole1_spin').update()
            self.builder.get_object('pinhole2_spin').set_value(conf['pinhole_2'])
            self.builder.get_object('pinhole2_spin').update()
            self.builder.get_object('pinhole3_spin').set_value(conf['pinhole_3'])
            self.builder.get_object('pinhole3_spin').update()
            self.builder.get_object('beamstop_spin').set_value(conf['beamstop'])
            self.builder.get_object('beamstop_spin').update()
            self.builder.get_object('beamx_spin').set_value(conf['beamposy'])
            self.builder.get_object('beamx_spin').update()
            self.builder.get_object('beamy_spin').set_value(conf['beamposx'])
            self.builder.get_object('beamy_spin').update()
            self.builder.get_object('pixelsize_spin').set_value(conf['pixelsize'])
            self.builder.get_object('pixelsize_spin').update()
            self.builder.get_object('wavelengthval_spin').set_value(conf['wavelength'])
            self.builder.get_object('wavelengthval_spin').update()
            self.builder.get_object('wavelengtherr_spin').set_value(conf['wavelength.err'])
            self.builder.get_object('wavelengtherr_spin').update()
            self.builder.get_object('description_entry').set_text(conf['description'])
            self.builder.get_object('mask_filechooser').set_filename(conf['mask'])
            self.builder.get_object('apply_button').set_sensitive(False)
        finally:
            self._updating = False
        self._original_conf = self.get_current_values()

    def on_edit(self, widget):
        if self._updating:
            return False
        conf = self.get_current_values()
        if not all([self._original_conf[k] == conf[k] for k in conf]):
            self.builder.get_object('apply_button').set_sensitive(True)

    def get_current_values(self):
        conf = {'dist_source_ph1': self.builder.get_object('l0_adjustment').get_value(),
                'dist_ph1_ph2': self.builder.get_object('l1_adjustment').get_value(),
                'dist_ph2_ph3': self.builder.get_object('l2_adjustment').get_value(),
                'dist_ph3_sample': self.builder.get_object('ls_adjustment').get_value(),
                'dist_sample_det': self.builder.get_object('ldval_adjustment').get_value(),
                'dist_sample_det.err': self.builder.get_object('lderr_adjustment').get_value(),
                'dist_det_beamstop': self.builder.get_object('lbs_adjustment').get_value(),
                'pinhole_1': self.builder.get_object('pinhole1_adjustment').get_value(),
                'pinhole_2': self.builder.get_object('pinhole2_adjustment').get_value(),
                'pinhole_3': self.builder.get_object('pinhole3_adjustment').get_value(),
                'beamstop': self.builder.get_object('beamstop_adjustment').get_value(),
                'beamposy': self.builder.get_object('beamx_adjustment').get_value(),
                'beamposx': self.builder.get_object('beamy_adjustment').get_value(),
                'pixelsize': self.builder.get_object('pixelsize_adjustment').get_value(),
                'wavelength': self.builder.get_object('wavelengthval_adjustment').get_value(),
                'wavelength.err': self.builder.get_object('wavelengtherr_adjustment').get_value(),
                'description': self.builder.get_object('description_entry').get_text(),
                'mask': self.builder.get_object('mask_filechooser').get_filename()}
        return conf

    def on_apply(self, button):
        self.instrument.config['geometry'].update(self.get_current_values())
        button.set_sensitive(False)
        self.instrument.save_state()
        self.info_message('Configuration saved to file ' + self.instrument.configfile)

    def on_close(self, widget, event=None):
        if self.builder.get_object('apply_button').get_sensitive():
            ret = question_message(self.widget, 'Closing window', 'Do you want to apply your changes?')
            # ret can be True (= Yes), False (= No) and None (= Cancel)
            if ret:
                self.on_apply(self.builder.get_object('apply_button'))
            elif ret is None:
                return True
            else:
                pass
        super().on_close(self, widget)
