import logging.handlers
import sys
import time
import traceback
from typing import List

import argparse
import pkg_resources
from gi import require_version

require_version('Gtk', '3.0')
require_version('GtkSource', '3.0')
require_version('Notify', '0.7')

from gi.repository import Notify, Gtk, Gio

from .accounting import AuthenticatorDialog
from ..core.instrument.instrument import Instrument
from .mainwindow import MainWindow

# initialize GObject Notification mechanism
Notify.init('cct')

# initialize the root logger
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logging.root.addHandler(handler)
handler = logging.handlers.TimedRotatingFileHandler('log/cct.log', 'D', 1, encoding='utf-8', backupCount=0)
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logging.root.addHandler(handler)
logging.root.setLevel(logging.DEBUG)
logging.root.info('------------------- Program startup -------------------')

# initialize custom icon theme for Gtk3
itheme = Gtk.IconTheme.get_default()
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/scalable'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/256x256'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/128x128'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/64x64'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/48x48'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/32x32'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/16x16'))
itheme.append_search_path(pkg_resources.resource_filename('cct', 'resource/icons/8x8'))

# install a new excepthook, which logs uncaught exceptions to the root logger.
oldexcepthook = sys.excepthook


def my_excepthook(type_, value, traceback_):
    try:
        logging.root.critical(
            'Unhandled exception: ' + '\n'.join(traceback.format_exception(type_, value, traceback_)))
    except:
        logging.root.critical(
            'Error in excepthook: ' + traceback.format_exc())
    oldexcepthook(type_, value, traceback_)


sys.excepthook = my_excepthook


class CCTApplication(Gtk.Application):
    def __init__(self, application_id: str, flags: Gio.ApplicationFlags):
        flags |= Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        super().__init__(application_id=application_id, flags=flags)
        self.instrument = None
        self._skipauthentication = False
        self._online = False
        self._mw = None
        self._starttime = time.time()

    def do_activate(self):
        ad = AuthenticatorDialog(self.instrument)
        try:
            if (not self._skipauthentication) and (not ad.run()):
                return True

            self._mw = MainWindow(self.instrument)
            self.add_window(self._mw.widget)
            self._mw.widget.set_show_menubar(True)
            self._mw.widget.show_all()
            self._instrument.start()
        finally:
            ad.widget.destroy()
        return True

    def do_command_line(self, args: List):
        parser = argparse.ArgumentParser()
        parser.add_argument('--online', action='store_true', default=False,
                            help='Enable working on-line (you should give this if you want to do serious work)')
        parser.add_argument('--root', action='store_true', default=False,
                            help='Skip the authentication dialog. Use this only as a last resort!')
        args = parser.parse_args()
        self.instrument = Instrument(args.online)
        self.instrument.load_state()
        self._online = args.online
        self._skipauthentication = args.root
        self.do_activate()
        return 0


def run():
    app = CCTApplication(
        application_id='hu.mta.ttk.credo.cctgui', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    app.run(sys.argv)


if __name__ == '__main__':
    run()
