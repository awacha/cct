from gi.repository import GLib

from ..core.functions import update_comboboxtext_choices, notify
from ..core.toolwindow import ToolWindow
from ...core.commands.transmission import Transmission


class TransmissionMeasurement(ToolWindow):
    def __init__(self, *args, **kwargs):
        self._samplestoreconnection = None
        self._pulser_timeout = None
        super().__init__(*args, **kwargs)

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self._samplestoreconnection = self.instrument.services['samplestore'].connect(
            'list-changed', self.on_samplelistchanged)
        self.on_samplelistchanged(self.instrument.services['samplestore'])

    def cleanup(self):
        self.instrument.services['samplestore'].disconnect(self._samplestoreconnection)
        self._samplestoreconnection = None

    def on_samplelistchanged(self, samplestore):
        # Note that emptyname_combo and the sample selector combobox
        # cellrenderer in the first treeview column use the same liststore.
        update_comboboxtext_choices(self.builder.get_object('emptyname_combo'),
                                    sorted(samplestore, key=lambda x: x.title),
                                    self.instrument.config['datareduction']['backgroundname'])

    def on_add(self, button):
        self.builder.get_object('transmstore').append(('', '--', '--', '--', '--', '--', '--', False, 0, -1))

    def on_remove(self, button):
        model, it = self.builder.get_object('transmselection').get_selected()
        if it is not None:
            model.remove(it)

    def on_start(self, button):
        if button.get_label() == 'Start':
            transmstore = self.builder.get_object('transmstore')
            for row in transmstore:
                row[1] = '--'
                row[2] = '--'
                row[3] = '--'
                row[4] = '--'
                row[5] = '--'
                row[6] = '--'
                row[7] = False
                row[8] = 0
            transmstore[0][7] = True

            button.set_label('Stop')
            self._pulser_timeout = GLib.timeout_add(100, self.pulser)
            samplenames = [row[0] for row in self.builder.get_object('transmstore')]
            self.execute_command(
                Transmission, (
                    samplenames,
                    self.builder.get_object('nimages_spin').get_value_as_int(),
                    self.builder.get_object('exptime_spin').get_value(),
                    self.builder.get_object('samplenamestore')[
                        self.builder.get_object('emptyname_combo').get_active()][0],
                ), True, additional_widgets=[
                    'entry_expander', 'transmview', 'add_button', 'remove_button', 'close_button']
            )
        else:
            self.instrument.services['interpreter'].kill()

    def on_command_return(self, interpreter, commandname, value):
        super().on_command_return(interpreter, commandname, value)
        GLib.source_remove(self._pulser_timeout)
        self._pulser_timeout = None
        self.builder.get_object('start_button').set_label('Start')
        notify(
            summary='Transmission measurement done',
            body='Measured transmissions for {:d} sample(s)'.format(
                len(self.builder.get_object('transmstore')))
        )

    def on_cmd_detail(self, interpreter, commandname, msg):
        transmstore = self.builder.get_object('transmstore')
        what, samplename, value = msg
        for i in range(len(transmstore)):
            if transmstore[i][0] == samplename:
                if what == 'dark':
                    transmstore[i][1] = str(value)
                elif what == 'empty':
                    transmstore[i][2] = str(value)
                elif what == 'sample':
                    transmstore[i][3] = str(value)
                elif what == 'transmission':
                    transmstore[i][4] = str(value)
                    mu = -value.log() / self.instrument.services['samplestore'].get_sample(samplename).thickness
                    transmstore[i][5] = str(mu)
                    transmstore[i][6] = str(1 / mu)
                    transmstore[i][7] = False
                    transmstore[i][8] = 0
                    if i + 1 < len(transmstore):
                        transmstore[i + 1][7] = True
                else:
                    raise ValueError(what)
        return

    def pulser(self):
        for row in self.builder.get_object('transmstore'):
            row[8] += 1
        return True

    def on_samplenamerenderercombo_changed(self, samplenamerenderercombo, path, it):
        transmstore = self.builder.get_object('transmstore')
        samplenamestore = self.builder.get_object('samplenamestore')
        samplename = samplenamestore[it][0]
        transmstore[path][0] = samplename
