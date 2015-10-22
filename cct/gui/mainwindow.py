from gi import require_version

require_version('Gtk', '3.0')
from gi.repository import Gio
from gi.repository import Gtk
from gi.repository import GLib
import pkg_resources
import sys
import logging
import traceback
import argparse
from ..core.instrument.instrument import Instrument
from .measurement.scan import Scan
from .devices.motors import Motors

logger = logging.getLogger('__name__')
logger.setLevel(logging.DEBUG)

oldexcepthook=sys.excepthook
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
        print(message, flush=True)
        GLib.idle_add(self._logfunction, message, record)


class CCTApplication(Gtk.Application):
    def __init__(self, *args, **kwargs):
        kwargs['flags'] = Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        Gtk.Application.__init__(self, *args, **kwargs)
        # self.connect('activate', self.on_activate)
        # self.connect('startup', self.on_startup)

    def do_activate(self):
        self._mw = MainWindow(self, self._online)
        self.add_window(self._mw._window)
        self._mw._window.set_show_menubar(True)
        self._mw._window.show_all()
        return True

    def do_command_line(self, args):
        parser = argparse.ArgumentParser()
        parser.add_argument('--online',
                            help='Enable working on-line (you should give this if you want to do serious work)')
        args = parser.parse_args()
        if args.online:
            self._online = True
        else:
            self._online = False
        self.do_activate()
        return 0

class DeviceStatusBar(Gtk.Box):
    def __init__(self, instrument):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL)
        self._instrument=instrument
        self._statuslabels={}
        self._connections={}
        for device in sorted(self._instrument.devices):
            dev=self._instrument.devices[device]
            frame=Gtk.Frame(label=device)
            self._statuslabels[device]=Gtk.Label(label=dev.get_variable('_status'))
            frame.add(self._statuslabels[device])
            self.pack_start(frame, True, True, 0)
            self._connections[dev]=dev.connect('variable-change', self.on_variable_change, device)

    def do_destroy(self):
        logger.debug('Destroying devicestatusbar')
        try:
            for d in self._connections:
                d.disconnect(self._connections[d])
            del self._connections
        except (AttributeError, KeyError):
            pass

    def on_variable_change(self, device, variablename, newvalue, devicename):
        if variablename=='_status':
            self._statuslabels[devicename].set_text(newvalue)
        return False

class MainWindow(object):
    def __init__(self, app, is_online):
        self._application = app
        self._online = is_online
        self._builder = Gtk.Builder.new_from_file(
            pkg_resources.resource_filename('cct', 'resource/glade/mainwindow.glade'))
        self._builder.set_application(app)
        self._window = self._builder.get_object('mainwindow')
        self._builder.connect_signals(self)
        self._window.set_show_menubar(True)
        self._window.connect('delete-event', self.on_delete_event)
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
        self._instrument = Instrument()
        self._instrument.connect_devices()
        self._devicestatus=DeviceStatusBar(self._instrument)
        self._builder.get_object('devicestatus_box').pack_start(self._devicestatus, True, True, 0)

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

    def construct_and_run_dialog(self, windowclass, toplevelname, gladefile):
        if toplevelname not in self._dialogs:
            self._dialogs[toplevelname] = windowclass(gladefile, toplevelname, self._instrument, self._application)
        self._dialogs[toplevelname]._window.show_all()

    def on_menu_file_quit(self, menuitem):
        self._window.destroy()
        self._application.quit()


    def on_menu_setup_sampleeditor(self, menuitem):
        logger.debug('This is not yet implemented')
        return False

    def on_menu_setup_definegeometry(self, menuitem):
        raise NotImplementedError
        return False

    def on_menu_setup_editconfiguration(self, menuitem):
        return False

    def on_menu_setup_calibration_beamcenter(self, menuitem):
        return False

    def on_menu_setup_calibration_sampletodetectordistance(self, menuitem):
        return False

    def on_menu_devices_xraysource(self, menuitem):
        return False

    def on_menu_devices_detector(self, menuitem):
        return False

    def on_menu_devices_motors(self, menuitem):
        self.construct_and_run_dialog(Motors, 'motoroverview', 'devices_motors.glade')
        return False

    def on_menu_devices_vacuumgauge(self, menuitem):
        return False

    def on_menu_devices_temperaturestage(self, menuitem):
        return False

    def on_menu_measurement_scan(self, menuitem):
        self.construct_and_run_dialog(Scan, 'scan', 'measurement_scan.glade')
        return False

    def on_menu_measurement_singleexposure(self, menuitem):
        return False

    def on_menu_measurement_transmission(self, menuitem):
        return False

    def on_menu_measurement_automaticprogram(self, menuitem):
        return False


def run():
    app = CCTApplication(
        application_id='hu.mta.ttk.credo.cctgui', flags=Gio.ApplicationFlags.FLAGS_NONE)
    app.run(sys.argv)


if __name__ == '__main__':
    run()
