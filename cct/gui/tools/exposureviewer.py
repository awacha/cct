from ..setup.calibration import Calibration


class ExposureViewer(Calibration):
    def _init_gui(self, *args):
        Calibration._init_gui(self, args)
        ib = self._builder.get_object('input_box')
        ib.remove(self._builder.get_object('centering_expander'))
        ib.remove(self._builder.get_object('distance_expander'))
        stack = self._builder.get_object('plotstack')
        stack.remove(self._builder.get_object('figbox_distcalib'))
        self._builder.get_object('right_box').remove(self._builder.get_object('results_frame'))
        bb = self._builder.get_object('buttonbox')
        bb.remove(self._builder.get_object('savecenter_button'))
        bb.remove(self._builder.get_object('savedistance_button'))
