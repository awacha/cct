import pkg_resources
from gi.repository import GLib, Notify, GdkPixbuf

from ..core.toolwindow import ToolWindow, error_message


class Transmission(ToolWindow):
    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        try:
            self._instrument.services['samplestore'].disconnect(self._onlistchangedconnection)
            del self._onlistchangedconnection
        except AttributeError:
            pass
        self._onlistchangedconnection = self._instrument.services['samplestore'].connect('list-changed',
                                                                                         self.on_samplelistchanged)
        self.on_samplelistchanged(self._instrument.services['samplestore'])

    def on_unmap(self, window):
        try:
            self._instrument.services['samplestore'].disconnect(self._onlistchangedconnection)
            del self._onlistchangedconnection
        except AttributeError:
            pass

    def on_samplelistchanged(self, samplestore):
        idx=self._builder.get_object('emptyname_combo').get_active()
        try:
            prevselected=self._builder.get_object('samplenamestore')[idx][0]
        except IndexError:
            prevselected=None
        self._builder.get_object('samplenamestore').clear()
        for i,sn in enumerate(sorted(samplestore)):
            self._builder.get_object('samplenamestore').append([sn.title])
            if sn.title==prevselected:
                self._builder.get_object('emptyname_combo').set_active(i)
        if self._builder.get_object('emptyname_combo').get_active()<0:
            self._builder.get_object('emptyname_combo').set_active(0)

    def on_add(self, button):
        self._builder.get_object('transmstore').append(('','--','--','--','--','--','--',False,0,-1))

    def on_remove(self, button):
        model, it=self._builder.get_object('transmselection').get_selected()
        if it is not None:
            model.remove(it)

    def on_start(self, button):
        if button.get_label()=='Start':
            self._make_insensitive('Transmission measurement running',['entry_expander', 'transmview', 'add_button', 'remove_button', 'close_button'])
            self._builder.get_object('start_button').set_label('Stop')
            samplenames = ', '.join("'%s'" % row[0] for row in reversed(self._builder.get_object('transmstore')))
            self._interpreterconnections = [
                self._instrument.services['interpreter'].connect('cmd-return', self.on_cmd_return),
                self._instrument.services['interpreter'].connect('cmd-detail', self.on_cmd_detail),
                self._instrument.services['interpreter'].connect('cmd-fail', self.on_cmd_fail),
                ]
            self._instrument.services['interpreter'].execute_command('transmission([%s], %d, %f, "%s")' % (
                samplenames, self._builder.get_object('nimages_spin').get_value_as_int(),
                self._builder.get_object('exptime_spin').get_value(),
                self._builder.get_object('samplenamestore')[self._builder.get_object('emptyname_combo').get_active()][0]))
            transmstore=self._builder.get_object('transmstore')
            for row in transmstore:
                row[1]='--'
                row[2]='--'
                row[3]='--'
                row[4]='--'
                row[5]='--'
                row[6]='--'
                row[7]=False
                row[8]=0
            transmstore[0][7]=True
            self._pulser_timeout=GLib.timeout_add(100,self.pulser)
        else:
            self._instrument.services['interpreter'].kill()

    def on_cmd_return(self, interpreter, commandname, value):
        self._make_sensitive()
        self._builder.get_object('start_button').set_label('Start')
        try:
            for c in self._interpreterconnections:
                self._instrument.services['interpreter'].disconnect(c)
            del self._interpreterconnections
        except AttributeError:
            pass
        try:
            GLib.source_remove(self._pulser_timeout)
            del self._pulser_timeout
        except AttributeError:
            pass
        n=Notify.Notification(summary='Transmission measurement done',body='Measured transmissions for %d sample(s)'%len(self._builder.get_object('transmstore')))
        n.set_image_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(pkg_resources.resource_filename('cct','resource/icons/scalable/cctlogo.svg'),256,256))
        n.show()

    def on_cmd_fail(self, interpreter, commandname, exc, tb):
        error_message(self._window, 'Error during transmission measurement', str(exc)+tb)

    def on_cmd_detail(self, interpreter, commandname, msg):
        transmstore=self._builder.get_object('transmstore')
        what, samplename, value=msg
        for i in range(len(transmstore)):
            if transmstore[i][0]==samplename:
                if what=='dark':
                    transmstore[i][1]=str(value)
                elif what=='empty':
                    transmstore[i][2]=str(value)
                elif what=='sample':
                    transmstore[i][3]=str(value)
                elif what=='transmission':
                    transmstore[i][4]=str(value)
                    mu = -value.log() / self._instrument.services['samplestore'].get_sample(samplename).thickness
                    transmstore[i][5]=str(mu)
                    transmstore[i][6]=str(1/mu)
                    transmstore[i][7]=False
                    transmstore[i][8]=0
                    if i+1<len(transmstore):
                        transmstore[i+1][7]=True
                else:
                    raise NotImplementedError(what)
        return

    def pulser(self):
        for row in self._builder.get_object('transmstore'):
            row[8]+=1
        return True

    def on_samplenamerenderercombo_changed(self, samplenamerenderercombo, path, it):
        transmstore=self._builder.get_object('transmstore')
        samplenamestore=self._builder.get_object('samplenamestore')
        samplename=samplenamestore[it][0]
        transmstore[path][0]=samplename

