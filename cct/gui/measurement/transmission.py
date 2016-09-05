import logging

from gi.repository import GLib, Gtk, Gdk

from ..core.functions import notify
from ..core.toolwindow import ToolWindow
from ...core.commands.transmission import Transmission

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class TransmissionMeasurement(ToolWindow):
    required_devices = ['detector', 'xray_source', 'Motor_BeamStop_X', 'Motor_BeamStop_Y', 'Motor_Sample_X',
                        'Motor_Sample_Y']

    def __init__(self, *args, **kwargs):
        self._samplestoreconnection = None
        self._pulser_timeout = None
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        self.builder.get_object('nimages_spin').set_value(self.instrument.config['transmission']['nimages'])
        self.builder.get_object('exptime_spin').set_value(self.instrument.config['transmission']['exptime'])
        maskpath = self.instrument.services['filesequence'].get_mask_filepath(
            self.instrument.config['transmission']['mask'])
        self.builder.get_object('maskchooser').set_filename(maskpath)
        self.tidy_transmmodel(self.builder.get_object('transmview'))

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
        logger.debug('on_samplelistchanged')
        emptynamecombo = self.builder.get_object('emptyname_combo')
        samplenamestore = self.builder.get_object('samplenamestore')
        assert isinstance(samplenamestore, Gtk.ListStore)
        assert isinstance(emptynamecombo, Gtk.ComboBox)
        if (emptynamecombo.get_active() is None) or (not len(samplenamestore)):
            emptyname = self.instrument.config['datareduction']['backgroundname']
        else:
            emptyname = samplenamestore[emptynamecombo.get_active()][0]
        logger.debug('Emptyname is {}'.format(emptyname))
        samplenamestore.clear()
        to_be_selected_iter = None
        for st in sorted([x.title for x in samplestore]):
            it = samplenamestore.append([st])
            if st == emptyname:
                logger.debug('Found iter to be selected')
                to_be_selected_iter = it
        if to_be_selected_iter is not None:
            logger.debug('Selecting iter.')
            emptynamecombo.set_active_iter(to_be_selected_iter)
            logger.debug('ComboBox now points at {}'.format(samplenamestore[emptynamecombo.get_active()][0]))

    # noinspection PyMethodMayBeStatic
    def tidy_transmmodel(self, treeview: Gtk.TreeView):
        model, selected_iter = treeview.get_selection().get_selected()
        assert isinstance(model, Gtk.ListStore)
        if selected_iter:
            selected_name = model[selected_iter][0]
        else:
            selected_name = None
        selected_iter = None
        rows = [list(r) for r in model]
        model.clear()
        for r in rows:
            if not r[0]:
                continue
            it = model.append(r)
            if r[0] == selected_name:
                selected_iter = it
        it = model.append(['', '--', '--', '--', '--', '--', '--', False, 0, -1])
        if selected_iter is None:
            selected_iter = it
        treeview.get_selection().select_iter(selected_iter)

    def on_transmview_keypress(self, treeview: Gtk.TreeView, event: Gdk.EventKey):
        if event.get_keyval()[1] in [Gdk.KEY_Delete, Gdk.KEY_KP_Delete, Gdk.KEY_BackSpace]:
            model, selectediter = treeview.get_selection().get_selected()
            if (selectediter is not None) and (model[selectediter] != ''):
                model.remove(selectediter)
                self.tidy_transmmodel(treeview)
        return False

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
            self.instrument.config['transmission']['mask'] = self.builder.get_object('maskchooser').get_filename()
            self.instrument.save_state()
            button.set_label('Stop')
            button.get_image().set_from_icon_name('gtk-stop', Gtk.IconSize.BUTTON)
            self._pulser_timeout = GLib.timeout_add(100, self.pulser)
            samplenames = [row[0] for row in self.builder.get_object('transmstore') if row[0]]
            self.execute_command(
                Transmission, (
                    samplenames,
                    self.builder.get_object('nimages_spin').get_value_as_int(),
                    self.builder.get_object('exptime_spin').get_value(),
                    self.builder.get_object('samplenamestore')[
                        self.builder.get_object('emptyname_combo').get_active()][0],
                ), True, additional_widgets=[
                    'entry_expander', 'transmview', 'close_button']
            )
        else:
            self.instrument.services['interpreter'].kill()

    def on_command_return(self, interpreter, commandname, value):
        super().on_command_return(interpreter, commandname, value)
        GLib.source_remove(self._pulser_timeout)
        self._pulser_timeout = None
        self.builder.get_object('start_button').set_label('Start')
        self.builder.get_object('start_button').get_image().set_from_icon_name('system-run', Gtk.IconSize.BUTTON)
        for r in self.builder.get_object('transmstore'):
            r[7] = False
            r[8] = 0
        notify(
            summary='Transmission measurement done',
            body='Measured transmissions for {:d} sample(s)'.format(
                len(self.builder.get_object('transmstore')) - 1)
        )
        self.instrument.save_state()

    def on_command_detail(self, interpreter, commandname, msg):
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
        self.tidy_transmmodel(self.builder.get_object('transmview'))
