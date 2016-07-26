import logging

from ..core.toolwindow import ToolWindow, error_message

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class DataReduction(ToolWindow):
    def on_start(self, button):
        if button.get_label() == 'Start':
            self._stop = False
            button.set_label('Stop')
            self._make_insensitive('Data reduction running', ['inputgrid', 'exposuresview', 'button_close'])
            model, selected = self._builder.get_object('exposure_selection').get_selected_rows()
            self._nselected = len(selected)
            self._ndone = -1
            self._builder.get_object('progressbar').show()
            self._currentpath=None
            self._expanalyzerconnection = [self._instrument.services['exposureanalyzer'].connect('datareduction-done',
                                                                                                 self.on_datareduction),
                                           self._instrument.services['exposureanalyzer'].connect('error',
                                                                                                 self.on_datareduction)
                                           ]
            self.on_datareduction(self._instrument.services['exposureanalyzer'], None, None, None)
        else:
            self._stop = True

    def on_datareduction(self, expanalyzer, prefix, fsn, im, arg1=None):
        if arg1 is not None:
            logger.error('Error while data reduction. Prefix: %s. FSN: %d. Error: %s %s'%(prefix, fsn, im, arg1))
        logger.debug('On_datareduction called')
        self._ndone += 1
        self._builder.get_object('progressbar').set_fraction(self._ndone / self._nselected)
        self._builder.get_object('progressbar').set_text('Data reduction: %d/%d done' % (self._ndone, self._nselected))
        if self._currentpath is not None:
            self._builder.get_object('exposure_selection').unselect_path(self._currentpath)
            self._builder.get_object('exposuresview').scroll_to_cell(self._currentpath, None, False, 0, 0)
        model, selected = self._builder.get_object('exposure_selection').get_selected_rows()
        if (not selected) or self._stop:
            self._builder.get_object('button_execute').set_label('Start')
            self._builder.get_object('progressbar').hide()
            try:
                for c in self._expanalyzerconnection:
                    self._instrument.services['exposureanalyzer'].disconnect(c)
                del self._expanalyzerconnection
            except AttributeError:
                pass
            self._make_sensitive()
            return
        self._currentpath = selected[0]
        fsn = model[self._currentpath][0]
        prefix = self._instrument.config['path']['prefixes']['crd']
        ndigits = self._instrument.config['path']['fsndigits']
        self._instrument.services['exposureanalyzer'].submit(fsn, prefix + '_%%0%dd' % ndigits % fsn + '.cbf', prefix,
                                                             (self._instrument.services['filesequence'].load_param(
                                                                 prefix, fsn),))

    def on_reload(self, button):
        fsnfirst = self._builder.get_object('fsnfirst_adjustment').get_value()
        fsnlast = self._builder.get_object('fsnlast_adjustment').get_value()
        if fsnlast <= fsnfirst:
            error_message(self._window, 'The last fsn should be larger than the first.')
            return
        model = self._builder.get_object('exposurestore')
        model.clear()
        for i in range(int(fsnfirst), int(fsnlast) + 1):
            try:
                param = self._instrument.services['filesequence'].load_param(
                    self._instrument.config['path']['prefixes']['crd'], i)
            except FileNotFoundError:
                pass
            if 'sample' not in param:
                title = '-- no title --'
            else:
                title = param['sample']['title']
            model.append((param['exposure']['fsn'], param['sample']['title'], param['geometry']['truedistance'],
                          param['exposure']['date']))
