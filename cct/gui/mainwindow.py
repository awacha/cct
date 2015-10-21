from gi import require_version
require_version('Gtk','3.0')
from gi.repository import Gio
from gi.repository import Gtk
from gi.repository import GLib
import pkg_resources
import sys
import logging
import traceback
logger=logging.getLogger('__name__')
logger.setLevel(logging.DEBUG)

def my_excepthook(type_, value, traceback_):
    try:
        logger.critical(
            'Unhandled exception: ' + '\n'.join(traceback.format_exception(type_, value, traceback_)))
    except:
        logger.critical(
            'Error in excepthook: ' + traceback.format_exc())

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
        Gtk.Application.__init__(self, *args, **kwargs)
        self.connect('activate', self.on_activate)
        self.connect('startup', self.on_startup)

    def on_startup(self, app):
        return False

    def on_activate(self, app):
        self._mw=MainWindow(self)
        self.add_window(self._mw._window)
        self._mw._window.set_show_menubar(True)
        self._mw._window.show_all()
        return True



class MainWindow(object):

    def __init__(self, app):
        self._builder=Gtk.Builder.new_from_file(pkg_resources.resource_filename('cct','resource/glade/mainwindow.glade'))
        self._builder.set_application(app)
        self._window=self._builder.get_object('mainwindow')
        self._builder.connect_signals(self)
        self._window.set_show_menubar(True)
        self._window.show_all()
        self._loghandler=MyLogHandler(self._writelogline)
        self._loghandler.setLevel(logging.DEBUG)
        logging.root.addHandler(self._loghandler)
        self._loghandler.setFormatter(logging.Formatter(
            '%(asctime)s: %(levelname)s: %(message)s  (Origin: %(name)s)'))
        self._logtags=self._builder.get_object('log_texttags')
        self._logbuffer=self._builder.get_object('logbuffer')
        self._logbuffer.create_mark(
            'log_end', self._logbuffer.get_end_iter(), False)
        self._logview=self._builder.get_object('logtext')
        self._statusbar=self._builder.get_object('statusbar')
        self._dialogs={}
        def f(tt):
            print(tt.get_property('name'))
        self._logtags.foreach(f)

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
            self._statusbar.push(0,record.message.split('\n')[0])
        return False

    def on_menu_file_quit(self, menuitem):
        self._window.destroy() # this will also stop the main loop, since this is the only application window.

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
        return False

    def on_menu_devices_vacuumgauge(self, menuitem):
        return False

    def on_menu_devices_temperaturestage(self, menuitem):
        return False

    def on_menu_measurement_scan(self, menuitem):
        if 'scan' not in self._dialogs:
            self._dialogs['scan']={}
            self._dialogs['scan']['builder']=Gtk.Builder.new_from_file()
        return False

    def on_menu_measurement_singleexposure(self, menuitem):
        return False

    def on_menu_measurement_transmission(self, menuitem):
        return False

    def on_menu_measurement_automaticprogram(self, menuitem):
        return False

if __name__ == '__main__':
    app = CCTApplication(
        application_id='hu.mta.ttk.credo.cctgui', flags=Gio.ApplicationFlags.FLAGS_NONE)
    app.run()
