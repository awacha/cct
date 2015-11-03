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
import numpy as np
from ..core.instrument.instrument import Instrument
from .measurement.scan import Scan
from .devices.motors import Motors
from .devices.genix import GeniX
from .devices.tpg201 import TPG201
from .setup.editconfig import EditConfig
from .setup.sampleedit import SampleEdit
from .setup.definegeometry import DefineGeometry
from .measurement.singleexposure import SingleExposure
from .core.plotimage import PlotImageWindow
from .measurement.script import ScriptMeasurement
from .core.plotcurve import PlotCurveWindow

itheme = Gtk.IconTheme.get_default()
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/scalable'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/256x256'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/64x64'))

logger = logging.getLogger(__name__)
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
        self._mw = MainWindow(self, self._online, self._newconfig)
        self.add_window(self._mw._window)
        self._mw._window.set_show_menubar(True)
        self._mw._window.show_all()
        return True

    def do_command_line(self, args):
        parser = argparse.ArgumentParser()
        parser.add_argument('--online', action='store_true', default=False,
                            help='Enable working on-line (you should give this if you want to do serious work)')
        parser.add_argument('--newconfig', action='store_true', default=False,
                            help='Clobber the config file. You probably don\'t need this, only in case you are running a new version of cct for the first time.')
        args = parser.parse_args()
        self._online = args.online
        self._newconfig = args.newconfig
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
    def __init__(self, app, is_online, clobber_config):
        self._application = app
        self._online = is_online
        self._clobber_config = clobber_config
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
        self._instrument = Instrument(self._clobber_config)
        if self._online:
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
        self._instrument.save_state()
        self._application.quit()


    def on_menu_setup_sampleeditor(self, menuitem):
        self.construct_and_run_dialog(SampleEdit, 'samplesetup', 'setup_sampleedit.glade')
        return False

    def on_menu_setup_definegeometry(self, menuitem):
        self.construct_and_run_dialog(DefineGeometry, 'definegeometry', 'setup_definegeometry.glade')
        return False

    def on_menu_setup_editconfiguration(self, menuitem):
        self.construct_and_run_dialog(EditConfig, 'editconfig', 'setup_editconfig.glade')
        return False

    def on_menu_setup_calibration_beamcenter(self, menuitem):
        # ToDo
        return False

    def on_menu_setup_calibration_sampletodetectordistance(self, menuitem):
        #ToDo
        return False

    def on_menu_devices_xraysource(self, menuitem):
        self.construct_and_run_dialog(GeniX, 'genix', 'devices_genix.glade')
        return False

    def on_menu_devices_detector(self, menuitem):
        #ToDo
        return False

    def on_menu_devices_motors(self, menuitem):
        self.construct_and_run_dialog(Motors, 'motoroverview', 'devices_motors.glade')
        return False

    def on_menu_devices_vacuumgauge(self, menuitem):
        self.construct_and_run_dialog(TPG201, 'vacgauge', 'devices_tpg201.glade')
        return False

    def on_menu_devices_temperaturestage(self, menuitem):
        x = np.linspace(0.001, 1, 1000)
        dx = x / 100
        y = (1 / x ** 3 * (np.sin(x * 20) - x * 20 * np.cos(x * 20))) ** 2
        x = x + np.random.randn(len(x)) * dx
        dy = y / 100
        y = y + np.random.randn(len(y)) * dy
        pc = PlotCurveWindow()
        pc.addcurve(x, y, dx, dy, 'test curve', 'q', 0.172, 1000, 0.15142)
        return False

    def on_menu_measurement_scan(self, menuitem):
        self.construct_and_run_dialog(Scan, 'scan', 'measurement_scan.glade')
        return False

    def on_menu_measurement_singleexposure(self, menuitem):
        self.construct_and_run_dialog(SingleExposure,'singleexposure','measurement_singleexposure.glade')
        return False

    def on_menu_measurement_transmission(self, menuitem):
        m=np.random.randn(256*256).reshape(256,256)
        colidx, rowidx = np.meshgrid(np.arange(256), np.arange(256))
        beampos_rowidx = 30
        beampos_colidx = 120
        m = ((colidx - beampos_colidx) ** 2 + (rowidx - beampos_rowidx) ** 2) ** 0.5 + m
        mask = (rowidx > 100) & (rowidx < 150) & (colidx > 20) & (colidx < 40)
        pi = PlotImageWindow(image=m, mask=mask, pixelsize=0.172, beampos=(beampos_rowidx, beampos_colidx),
                             wavelength=0.1542,
                       distance=1500)
        return False

    def on_menu_measurement_automaticprogram(self, menuitem):
        self.construct_and_run_dialog(ScriptMeasurement,'script','measurement_script.glade')
        return False


def run():
    app = CCTApplication(
        application_id='hu.mta.ttk.credo.cctgui', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    app.run(sys.argv)


if __name__ == '__main__':
    run()
