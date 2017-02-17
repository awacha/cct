from ..setup.calibration import Calibration


class ExposureViewer(Calibration):
    def init_gui(self, *args, **kwargs):
        Calibration.init_gui(self, args, kwargs)
        ib = self.builder.get_object('input_box')
        ib.remove(self.builder.get_object('centering_expander'))
        ib.remove(self.builder.get_object('distance_expander'))
        stack = self.builder.get_object('plotstack')
        stack.remove(self.builder.get_object('figbox_distcalib'))
        self.builder.get_object('right_box').remove(self.builder.get_object('results_frame'))
        bb = self.builder.get_object('buttonbox')
        bb.remove(self.builder.get_object('savecenter_button'))
        bb.remove(self.builder.get_object('savedistance_button'))
