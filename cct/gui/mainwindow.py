import datetime
import logging
import sys
import time
import traceback
from logging import StreamHandler
from logging.handlers import TimedRotatingFileHandler

import argparse
import pkg_resources
from gi import require_version

require_version('Gtk', '3.0')
require_version('GtkSource', '3.0')
require_version('Notify', '0.7')

from gi.repository import Gio
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import GdkPixbuf
from gi.repository import Notify
from ..core.instrument.instrument import Instrument
from ..core.commands.command import CommandError
from .measurement.scan import Scan
from .devices.motors import Motors
from .devices.genix import GeniX
from .devices.tpg201 import TPG201
from .setup.editconfig import EditConfig
from .setup.sampleedit import SampleEdit
from .setup.definegeometry import DefineGeometry
from .measurement.singleexposure import SingleExposure
from .measurement.script import ScriptMeasurement, CommandHelpDialog
from .measurement.transmission import Transmission
from .setup.calibration import Calibration
from .tools.exposureviewer import ExposureViewer
from .tools.capillarymeasurement import CapillaryMeasurement
from .tools.scanviewer import ScanViewer
from .tools.maskeditor import MaskEditor
from .tools.datareduction import DataReduction
from .diagnostics.telemetry import ResourceUsage
from .devices.haakephoenix import HaakePhoenix
from .devices.pilatus import Pilatus
from .toolframes.resourceusage import ResourceUsageFrame
from .toolframes.nextfsn import NextFSN
from .toolframes.shutter import ShutterBeamstop
from .toolframes.accounting import AccountingFrame
from .accounting.usermanager import UserManager
from .accounting.projectmanager import ProjectManager
from .core.toolwindow import error_message
from .devices.connections import DeviceConnections

Notify.init('cct')

handler = StreamHandler()
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logging.root.addHandler(handler)
handler = TimedRotatingFileHandler('log/cct.log', 'D', 1, encoding='utf-8', backupCount=0)
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logging.root.addHandler(handler)
logging.root.setLevel(logging.DEBUG)
logging.root.info('------------------- Program startup -------------------')

cssprovider = Gtk.CssProvider()
cssprovider.load_from_path(pkg_resources.resource_filename('cct', 'resource/css/widgetbackgrounds.css'))

itheme = Gtk.IconTheme.get_default()
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/scalable'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/256x256'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/128x128'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/64x64'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/48x48'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/32x32'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/16x16'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/8x8'))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

oldexcepthook = sys.excepthook


def my_excepthook(type_, value, traceback_):
    try:
        logger.critical(
            'Unhandled exception: ' + '\n'.join(traceback.format_exception(type_, value, traceback_)))
    except:
        logger.critical(
            'Error in excepthook: ' + traceback.format_exc())
    oldexcepthook(type_, value, traceback_)


sys.excepthook = my_excepthook


class MyLogHandler(logging.Handler):
    def __init__(self, logfunction):
        logging.Handler.__init__(self)
        self._logfunction = logfunction

    def emit(self, record):
        message = self.format(record)
        GLib.idle_add(self._logfunction, message, record)


class CCTApplication(Gtk.Application):
    def __init__(self, *args, **kwargs):
        kwargs['flags'] = Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        Gtk.Application.__init__(self, *args, **kwargs)
        self._starttime = time.time()

    def do_activate(self):
        ad = AuthenticatorDialog(self, self._instrument)
        try:
            if (not self._skipauthentication) and (not ad.run()):
                return True

            self._mw = MainWindow(self, self._instrument)
            self.add_window(self._mw._window)
            self._mw._window.set_show_menubar(True)
            self._mw._window.show_all()
            self._instrument.start()
        finally:
            ad._window.destroy()
        return True

    def do_command_line(self, args):
        parser = argparse.ArgumentParser()
        parser.add_argument('--online', action='store_true', default=False,
                            help='Enable working on-line (you should give this if you want to do serious work)')
        parser.add_argument('--root', action='store_true', default=False,
                            help='Skip the authentication dialog. Use this only as a last resort!')
        args = parser.parse_args()
        self._instrument = Instrument(args.online)
        self._instrument.load_state()
        self._online = args.online
        self._skipauthentication = args.root
        self.do_activate()
        return 0


class AuthenticatorDialog(object):
    def __init__(self, application, instrument):
        self._application = application
        self._instrument = instrument
        self._builder = Gtk.Builder.new_from_file(
            pkg_resources.resource_filename('cct', 'resource/glade/accounting_login.glade'))
        self._window = self._builder.get_object('accountingdialog')
        self._builder.get_object('password_entry').get_style_context().add_provider(cssprovider,
                                                                                    Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._builder.connect_signals(self)

    def on_password_changed(self, password_entry):
        password_entry.set_name('GtkEntry')

    def run(self):
        while True:
            response = self._window.run()
            if response == Gtk.ResponseType.DELETE_EVENT or response == 0:
                self._application.quit()
                return False
            elif response == 1:
                username = self._builder.get_object('operator_entry').get_text()
                if self._application._instrument.services['accounting'].authenticate(
                        username, self._builder.get_object('password_entry').get_text()):
                    return True
                self._builder.get_object('password_entry').set_name('redbackground')


class DeviceStatusBar(Gtk.Box):
    def __init__(self, instrument):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL)
        self._instrument = instrument
        self._statuslabels = {}
        self._connections = {}
        self._status = {}
        self._auxstatus = {}
        for device in sorted(self._instrument.devices):
            dev = self._instrument.devices[device]
            frame = Gtk.Frame(label=device)
            self._status[dev] = dev.get_variable('_status')
            try:
                self._auxstatus[dev] = dev.get_variable('_auxstatus')
            except KeyError:
                self._auxstatus[dev] = None
            self._statuslabels[device] = Gtk.Label(label=self.get_labeltext(dev))
            frame.add(self._statuslabels[device])
            self.pack_start(frame, True, True, 0)
            self._connections[dev] = dev.connect('variable-change', self.on_variable_change, device)

    def get_labeltext(self, device):
        if (device not in self._auxstatus):
            return str(self._status[device])
        elif (self._auxstatus[device] is None):
            return str(self._status[device])
        else:
            return '{} ({})'.format(self._status[device], self._auxstatus[device])

    def do_destroy(self):
        try:
            for d in self._connections:
                d.disconnect(self._connections[d])
            del self._connections
        except (AttributeError, KeyError):
            pass

    def on_variable_change(self, device, variablename, newvalue, devicename):
        if variablename == '_status':
            self._status[device] = newvalue
            self._statuslabels[devicename].set_text(self.get_labeltext(device))
        elif variablename == '_auxstatus':
            self._auxstatus[device] = newvalue
            self._statuslabels[devicename].set_text(self.get_labeltext(device))
        return False


class MainWindow(object):
    def __init__(self, app, instrument):
        self._application = app
        self._builder = Gtk.Builder.new_from_file(
            pkg_resources.resource_filename('cct', 'resource/glade/mainwindow.glade'))
        self._builder.set_application(app)
        self._window = self._builder.get_object('mainwindow')
        self._builder.connect_signals(self)
        self._window.set_show_menubar(True)
        self._window.connect('delete-event', self.on_delete_event)
        self._window.set_default_icon_list([GdkPixbuf.Pixbuf.new_from_file_at_size(
            pkg_resources.resource_filename('cct', 'resource/icons/scalable/cctlogo.svg'),
            sz, sz) for sz in [16, 32, 48, 64, 128, 256]])
        self._window.show_all()
        self._loghandler = MyLogHandler(self._writelogline)
        self._loghandler.setLevel(logging.DEBUG)
        logging.root.addHandler(self._loghandler)
        self._loghandler.setFormatter(logging.Formatter(
            '%(asctime)s: %(levelname)s: %(message)s  (Origin: %(name)s)'))
        self._logtags = self._builder.get_object('log_texttags')
        self._logbuffer = self._builder.get_object('logbuffer')
        self._logbuffer.create_mark(
            'log_end', self._logbuffer.get_end_iter(), False)
        self._logview = self._builder.get_object('logtext')
        self._statusbar = self._builder.get_object('statusbar')
        self._dialogs = {}
        self._instrument = instrument
        if self._instrument._online:
            self._instrument.connect_devices()
        self._devicestatus = DeviceStatusBar(self._instrument)
        self._builder.get_object('devicestatus_box').pack_start(self._devicestatus, True, True, 0)

        self._toolframes = {'resourceusage': ResourceUsageFrame('toolframe_telemetry.glade',
                                                                'telemetryframe',
                                                                self._instrument,
                                                                self._application),
                            'nextfsn': NextFSN('toolframe_nextfsn.glade',
                                               'nextfsnframe',
                                               self._instrument,
                                               self._application),
                            'shutterbeamstop': ShutterBeamstop('toolframe_shutter.glade',
                                                               'shutterframe',
                                                               self._instrument,
                                                               self._application),
                            'accounting': AccountingFrame('toolframe_accounting.glade',
                                                          'accountingframe',
                                                          self._instrument,
                                                          self._application)
                            }

        self._builder.get_object('toolbox').pack_end(self._toolframes['resourceusage']._widget, False, True, 0)
        self._builder.get_object('toolbox').pack_end(self._toolframes['nextfsn']._widget, False, True, 0)
        self._builder.get_object('toolbox').pack_end(self._toolframes['shutterbeamstop']._widget, False, True, 0)
        self._builder.get_object('toolbox').pack_end(self._toolframes['accounting']._widget, False, True, 0)
        self._window.show_all()
        self._window.set_title('Credo Control Tool')

        self._interpreterconnections = [
            self._instrument.services['interpreter'].connect('cmd-return', self.on_interpreter_cmd_return),
            self._instrument.services['interpreter'].connect('cmd-fail', self.on_interpreter_cmd_fail),
            self._instrument.services['interpreter'].connect('pulse', self.on_interpreter_cmd_pulse),
            self._instrument.services['interpreter'].connect('progress', self.on_interpreter_cmd_progress),
            self._instrument.services['interpreter'].connect('cmd-message', self.on_interpreter_cmd_message),
            self._instrument.services['interpreter'].connect('idle-changed', self.on_interpreter_idle_changed), ]
        self._commandhistory = []
        self._historyindex = None

    def on_command_entry_keyevent(self, entry, event):
        if event.hardware_keycode == 111:
            # cursor up key
            if self._commandhistory:
                if self._historyindex is None:
                    self._historyindex = len(self._commandhistory)
                self._historyindex = max(0, self._historyindex - 1)
                self._builder.get_object('command_entry').set_text(self._commandhistory[self._historyindex])
            return True  # inhibit further processing of this key event
        elif event.hardware_keycode == 116:
            # cursor down key
            if self._commandhistory:
                if self._historyindex is None:
                    self._historyindex = -1
                self._historyindex = min(self._historyindex + 1, len(self._commandhistory) - 1)
                self._builder.get_object('command_entry').set_text(self._commandhistory[self._historyindex])
            return True  # inhibit further processing of this key event
        return False

    def on_interpreter_idle_changed(self, interpreter, idle):
        if not idle:
            self._builder.get_object('command_entry').set_sensitive(idle)
            if self._builder.get_object('execute_button').get_label() == 'Execute':
                self._builder.get_object('execute_button').set_sensitive(idle)
        if idle:
            self._builder.get_object('command_entry').set_sensitive(idle)
            self._builder.get_object('execute_button').set_sensitive(idle)

    def on_command_execute(self, button):
        if button.get_label() == 'Execute':
            cmd = self._builder.get_object('command_entry').get_text()
            try:
                self._instrument.services['interpreter'].execute_command(cmd)
            except CommandError as ce:
                error_message(self._window, 'Cannot execute command', str(ce))
            else:
                button.set_label('Stop')
                if (not self._commandhistory) or (self._commandhistory and self._commandhistory[-1] != cmd):
                    self._commandhistory.append(self._builder.get_object('command_entry').get_text())
        elif button.get_label() == 'Stop':
            self._instrument.services['interpreter'].kill()
        else:
            raise NotImplementedError(button.get_label())

    def on_interpreter_cmd_return(self, interpreter, commandname, returnvalue):
        self._builder.get_object('command_entry').set_sensitive(True)
        # self._builder.get_object('execute_button').set_sensitive(True)
        self._builder.get_object('command_entry').set_progress_fraction(0)
        self._builder.get_object('command_entry').set_text('')
        self._builder.get_object('command_entry').grab_focus()
        self._builder.get_object('execute_button').set_label('Execute')
        self._historyindex = None
        self._statusbar.pop(1)

    def on_interpreter_cmd_fail(self, interpreter, commandname, exc, tb):
        logger.error('Command {} failed: {} {}'.format(commandname, str(exc), tb))

    def on_interpreter_cmd_message(self, interpreter, commandname, message):
        self._statusbar.pop(1)
        self._statusbar.push(1, message)
        enditer = self._logbuffer.get_end_iter()
        self._logbuffer.insert_with_tags(enditer, str(datetime.datetime.now()) + ': MESSAGE: ' + message + '\n',
                                         self._logtags.lookup('normal'))
        self._logview.scroll_to_mark(
            self._logbuffer.get_mark('log_end'), 0.1, False, 0, 0)

    def on_interpreter_cmd_pulse(self, interpreter, commandname, message):
        self._builder.get_object('command_entry').progress_pulse()
        self._statusbar.pop(1)
        self._statusbar.push(1, message)

    def on_interpreter_cmd_progress(self, interpreter, commandname, message, fraction):
        self._builder.get_object('command_entry').set_progress_fraction(fraction)
        self._statusbar.pop(1)
        self._statusbar.push(1, message)

    def on_delete_event(self, window, event):
        return self.on_menu_file_quit(window)

    def _writelogline(self, message, record):
        if record.levelno >= logging.CRITICAL:
            tag = self._logtags.lookup('critical')
        elif record.levelno >= logging.ERROR:
            tag = self._logtags.lookup('error')
        elif record.levelno >= logging.WARNING:
            tag = self._logtags.lookup('warning')
        else:
            tag = self._logtags.lookup('normal')
        enditer = self._logbuffer.get_end_iter()
        self._logbuffer.insert_with_tags(enditer, message + '\n', tag)
        self._logview.scroll_to_mark(
            self._logbuffer.get_mark('log_end'), 0.1, False, 0, 0)
        if record.levelno >= logging.INFO:
            self._statusbar.pop(0)
            self._statusbar.push(0, record.message.split('\n')[0])
        return False

    def construct_and_run_dialog(self, windowclass, toplevelname, gladefile, windowtitle):
        key = str(windowclass) + str(toplevelname)
        if key not in self._dialogs:
            try:
                self._dialogs[key] = windowclass(gladefile, toplevelname, self._instrument, self._application,
                                                 windowtitle)
            except Exception as exc:
                # this has already been handled with an error dialog
                logger.warning('Could not open window {}: {} {}'.format(windowtitle, str(exc), traceback.format_exc()))
                return
        self._dialogs[key]._window.present()
        return self._dialogs[key]

    def on_menu_file_quit(self, menuitem):
        self._window.destroy()
        self._instrument.save_state()
        self._application.quit()

    def on_menu_setup_sampleeditor(self, menuitem):
        self.construct_and_run_dialog(SampleEdit, 'samplesetup', 'setup_sampleedit.glade', 'Set-up samples')
        return False

    def on_menu_setup_definegeometry(self, menuitem):
        self.construct_and_run_dialog(DefineGeometry, 'definegeometry', 'setup_definegeometry.glade', 'Define geometry')
        return False

    def on_menu_setup_editconfiguration(self, menuitem):
        self.construct_and_run_dialog(EditConfig, 'editconfig', 'setup_editconfig.glade', 'Edit configuration')
        return False

    def on_menu_setup_calibration(self, menuitem):
        self.construct_and_run_dialog(Calibration, 'calibration', 'setup_calibration.glade', 'Calibration')
        return False

    def on_menu_devices_xraysource(self, menuitem):
        self.construct_and_run_dialog(GeniX, 'genix', 'devices_genix.glade', 'X-ray source')
        return False

    def on_menu_devices_detector(self, menuitem):
        self.construct_and_run_dialog(Pilatus, 'pilatus', 'devices_pilatus.glade', 'Detector')
        return False

    def on_menu_devices_motors(self, menuitem):
        self.construct_and_run_dialog(Motors, 'motoroverview', 'devices_motors.glade', 'Overview of motors')
        return False

    def on_menu_devices_vacuumgauge(self, menuitem):
        self.construct_and_run_dialog(TPG201, 'vacgauge', 'devices_tpg201.glade', 'Vacuum gauge')
        return False

    def on_menu_devices_temperaturestage(self, menuitem):
        self.construct_and_run_dialog(HaakePhoenix, 'haakephoenix', 'devices_haakephoenix.glade',
                                      'Temperature controller')
        return False

    def on_menu_devices_connections(self, menuitem):
        print('on_menu_devices_connections')
        self.construct_and_run_dialog(DeviceConnections, 'deviceconnections', 'devices_connection.glade',
                                      'Connected devices')
        return False


    def on_menu_measurement_scan(self, menuitem):
        self.construct_and_run_dialog(Scan, 'scan', 'measurement_scan.glade', 'Scan measurements')
        return False

    def on_menu_measurement_singleexposure(self, menuitem):
        self.construct_and_run_dialog(SingleExposure, 'singleexposure', 'measurement_singleexposure.glade',
                                      'Single exposure')
        return False

    def on_menu_measurement_transmission(self, menuitem):
        self.construct_and_run_dialog(Transmission, 'measuretransmission', 'measurement_transmission.glade',
                                      'Transmission measurement')
        return False

    def on_menu_measurement_automaticprogram(self, menuitem):
        self.construct_and_run_dialog(ScriptMeasurement, 'script', 'measurement_script.glade', 'Scripting')
        return False

    def on_menu_tools_maskeditor(self, menuitem):
        self.construct_and_run_dialog(MaskEditor, 'maskeditor', 'tools_maskeditor.glade', 'Mask editor')
        return False

    def on_menu_tools_view(self, menuitem):
        self.construct_and_run_dialog(ExposureViewer, 'calibration', 'setup_calibration.glade', 'Data viewer')
        return False

    def on_menu_tools_scanview(self, menuitem):
        self.construct_and_run_dialog(ScanViewer, 'scanviewer', 'tools_scanviewer.glade', 'Scan viewer')
        return False

    def on_menu_tools_capillary(self, menuitem):
        self.construct_and_run_dialog(CapillaryMeasurement, 'capillarymeasurement', 'tools_capillarymeasurement.glade',
                                      'Capillary measurement')
        return False

    def on_menu_tools_datareduction(self, menuitem):
        self.construct_and_run_dialog(DataReduction, 'datareduction', 'tools_datareduction.glade', 'Data reduction')
        return False

    def on_menu_tools_diagnostics_resourceusage(self, menuitem):
        self.construct_and_run_dialog(ResourceUsage, 'resourceusagewindow', 'diagnostics_resourceusage.glade',
                                      'Resource usage')

    def on_menu_help_about(self, menuitem):
        builder = Gtk.Builder.new_from_file(pkg_resources.resource_filename('cct', 'resource/glade/help_about.glade'))
        ad = builder.get_object('aboutdialog')
        ad.set_version(pkg_resources.get_distribution('cct').version)
        ad.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(
            pkg_resources.resource_filename('cct', 'resource/icons/scalable/cctlogo.svg'), 256, 256))
        ad.run()
        ad.destroy()
        return False

    def on_menu_help_commandhelp(self, menuitem):
        chd = self.construct_and_run_dialog(CommandHelpDialog, 'commandhelpbrowser', 'help_commandhelpbrowser.glade',
                                            'Help on commands')
        chd.connect('insert', self._on_insert_command)
        return False

    def _on_insert_command(self, commandhelpdialog, command):
        self._builder.get_object('command_entry').set_text(command)

    def on_menu_setup_management_users(self, menuitem):
        self.construct_and_run_dialog(UserManager, 'usermanager', 'accounting_usermanager.glade', 'Manage users')
        return False

    def on_menu_setup_management_projects(self, menuitem):
        self.construct_and_run_dialog(ProjectManager, 'projectmanager', 'accounting_projectmanager.glade',
                                      'Manage projects')
        return False


def run():
    app = CCTApplication(
        application_id='hu.mta.ttk.credo.cctgui', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    app.run(sys.argv)


if __name__ == '__main__':
    run()
