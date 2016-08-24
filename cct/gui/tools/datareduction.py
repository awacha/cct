import logging

from ..core.toolwindow import ToolWindow, error_message

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DataReduction(ToolWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop = False
        self._expanalyzerconnection = []
        self._currentpath = None
        self._nselected = None
        self._ndone = None
        self._prefix = self.instrument.config['path']['prefixes']['crd']

    def on_start(self, button):
        if button.get_label() == 'Start':
            self._stop = False
            model, selected = self.builder.get_object('exposure_selection').get_selected_rows()
            self._nselected = len(selected)
            self._ndone = -1
            self.builder.get_object('progressbar').show()
            self._currentpath = None
            self._expanalyzerconnection = [
                self.instrument.services['exposureanalyzer'].connect(
                    'datareduction-done', self.on_datareduction),
                self.instrument.services['exposureanalyzer'].connect(
                    'error', self.on_expanalyzer_error)
            ]
            button.set_label('Stop')
            self.set_sensitive(False, 'Data reduction running', ['inputgrid', 'exposuresview', 'button_close'])
            self.on_datareduction(self.instrument.services['exposureanalyzer'], self._prefix, None, None)
        else:
            self._stop = True

    # noinspection PyMethodMayBeStatic
    def on_expanalyzer_error(self, prefix, fsn, exception, fmt_traceback):
        logger.error('Error while data reduction. Prefix: {}. FSN: {:d}. Error: {} {}'.format(prefix, fsn, exception,
                                                                                              fmt_traceback))

    def on_datareduction(self, expanalyzer, prefix, fsn, im):
        self._ndone += 1
        self.builder.get_object('progressbar').set_fraction(self._ndone / self._nselected)
        self.builder.get_object('progressbar').set_text('Data reduction: %d/%d done' % (self._ndone, self._nselected))
        if self._currentpath is not None:
            self.builder.get_object('exposure_selection').unselect_path(self._currentpath)
            self.builder.get_object('exposuresview').scroll_to_cell(self._currentpath, None, False, 0, 0)
        model, selected = self.builder.get_object('exposure_selection').get_selected_rows()
        if (not selected) or self._stop:
            self.builder.get_object('button_execute').set_label('Start')
            self.builder.get_object('progressbar').hide()
            self.set_sensitive(True)
            for c in self._expanalyzerconnection:
                self.instrument.services['exposureanalyzer'].disconnect(c)
            self._expanalyzerconnection = []
            return
        self._currentpath = selected[0]
        fsn = model[self._currentpath][0]
        self.instrument.services['exposureanalyzer'].submit(
            fsn, self.instrument.services['filesequence'].exposurefileformat(
                prefix, fsn) + '.cbf', prefix,
            params=(self.instrument.services['filesequence'].load_param(prefix, fsn),)
        )

    def on_reload(self, button):
        fsnfirst = self.builder.get_object('fsnfirst_adjustment').get_value()
        fsnlast = self.builder.get_object('fsnlast_adjustment').get_value()
        if fsnlast <= fsnfirst:
            error_message(self.widget, 'Error', 'The last fsn should be larger than the first.')
            return
        model = self.builder.get_object('exposurestore')
        model.clear()
        for i in range(int(fsnfirst), int(fsnlast) + 1):
            try:
                param = self.instrument.services['filesequence'].load_param(
                    self.instrument.config['path']['prefixes']['crd'], i)
            except FileNotFoundError:
                pass
            if 'sample' not in param:
                title = '-- no title --'
            else:
                title = param['sample']['title']
            model.append((param['exposure']['fsn'], title, param['geometry']['truedistance'],
                          param['exposure']['date']))
