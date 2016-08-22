from ..core.dialogs import question_message, info_message
from ..core.toolwindow import ToolWindow


class DefineGeometry(ToolWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        pass

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self.update_gui()

    def update_gui(self):
        conf = self.instrument.config['geometry']
        self.builder.get_object('l0_adjustment').set_value(conf['dist_source_ph1'])
        self.builder.get_object('l1_adjustment').set_value(conf['dist_ph1_ph2'])
        self.builder.get_object('l2_adjustment').set_value(conf['dist_ph2_ph3'])
        self.builder.get_object('ls_adjustment').set_value(conf['dist_ph3_sample'])
        self.builder.get_object('ldval_adjustment').set_value(conf['dist_sample_det'])
        self.builder.get_object('lderr_adjustment').set_value(conf['dist_sample_det.err'])
        self.builder.get_object('lbs_adjustment').set_value(conf['dist_det_beamstop'])
        self.builder.get_object('pinhole1_adjustment').set_value(conf['pinhole_1'])
        self.builder.get_object('pinhole2_adjustment').set_value(conf['pinhole_2'])
        self.builder.get_object('pinhole3_adjustment').set_value(conf['pinhole_3'])
        self.builder.get_object('beamstop_adjustment').set_value(conf['beamstop'])
        self.builder.get_object('beamx_adjustment').set_value(conf['beamposy'])
        self.builder.get_object('beamy_adjustment').set_value(conf['beamposx'])
        self.builder.get_object('pixelsize_adjustment').set_value(conf['pixelsize'])
        self.builder.get_object('wavelengthval_adjustment').set_value(conf['wavelength'])
        self.builder.get_object('wavelengtherr_adjustment').set_value(conf['wavelength.err'])
        self.builder.get_object('description_entry').set_text(conf['description'])
        self.builder.get_object('mask_filechooser').set_filename(conf['mask'])
        self.builder.get_object('apply_button').set_sensitive(False)

    def on_edit(self, widget):
        self.builder.get_object('apply_button').set_sensitive(True)

    def on_apply(self, button):
        conf = self.instrument.config['geometry']
        conf['dist_source_ph1'] = self.builder.get_object('l0_adjustment').get_value()
        conf['dist_ph1_ph2'] = self.builder.get_object('l1_adjustment').get_value()
        conf['dist_ph2_ph3'] = self.builder.get_object('l2_adjustment').get_value()
        conf['dist_ph3_sample'] = self.builder.get_object('ls_adjustment').get_value()
        conf['dist_sample_det'] = self.builder.get_object('ldval_adjustment').get_value()
        conf['dist_sample_det.err'] = self.builder.get_object('lderr_adjustment').get_value()
        conf['dist_det_beamstop'] = self.builder.get_object('lbs_adjustment').get_value()
        conf['pinhole_1'] = self.builder.get_object('pinhole1_adjustment').get_value()
        conf['pinhole_2'] = self.builder.get_object('pinhole2_adjustment').get_value()
        conf['pinhole_3'] = self.builder.get_object('pinhole3_adjustment').get_value()
        conf['beamstop'] = self.builder.get_object('beamstop_adjustment').get_value()
        conf['beamposy'] = self.builder.get_object('beamx_adjustment').get_value()
        conf['beamposx'] = self.builder.get_object('beamy_adjustment').get_value()
        conf['pixelsize'] = self.builder.get_object('pixelsize_adjustment').get_value()
        conf['wavelength'] = self.builder.get_object('wavelengthval_adjustment').get_value()
        conf['wavelength.err'] = self.builder.get_object('wavelengtherr_adjustment').get_value()
        conf['description'] = self.builder.get_object('description_entry').get_text()
        conf['mask'] = self.builder.get_object('mask_filechooser').get_filename()
        button.set_sensitive(False)
        self.instrument.save_state()
        info_message(self.widget, 'Configuration saved', 'Saved configuration to file ' + self.instrument.configfile)

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
