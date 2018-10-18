import gc
import logging.handlers
import sys
import traceback

import pkg_resources
from PyQt5.QtWidgets import QApplication

from .accounting.logindialog import LogInDialog
from .mainwindow import MainWindow
from .mainwindow.collectinghandler import CollectingHandler
from ..core.instrument.instrument import Instrument
from ..core.instrument.privileges import PRIV_SUPERUSER


class AnsiColorFormatter(logging.Formatter):
    def __init__(self, oldformatter: logging.Formatter):
        super().__init__()
        self._oldformatter = oldformatter

    def format(self, record: logging.LogRecord):
        s = self._oldformatter.format(record)
        if record.levelno >= logging.CRITICAL:
            s = '\x1b\x5b30m\x1b\x5b1m\x1b\x5b41m' + s + '\x1b\x5b0m'
        elif record.levelno >= logging.ERROR:
            s = '\x1b\x5b31m\x1b\x5b1m' + s + '\x1b\x5b0m'
        elif record.levelno >= logging.WARNING:
            s = '\x1b\x5b33m\x1b\x5b1m' + s + '\x1b\x5b0m'
        elif record.levelno >= logging.INFO:
            s = '\x1b\x5b32m' + s + '\x1b\x5b0m'
        elif record.levelno >= logging.DEBUG:
            s = '\x1b\x5b37m' + s + '\x1b\x5b0m'
        return s


# initialize the root logger
handler = logging.StreamHandler()
handler.addFilter(logging.Filter('cct'))
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
ansiformatter = AnsiColorFormatter(formatter)
handler.setFormatter(ansiformatter)
logging.root.addHandler(handler)
handler = logging.handlers.TimedRotatingFileHandler('log/cct.log', 'D', 1, encoding='utf-8', backupCount=0)
handler.addFilter(logging.Filter('cct'))
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logging.root.addHandler(handler)
logging.root.setLevel(logging.DEBUG)
ch = CollectingHandler()
ch.addFilter(logging.Filter('cct'))
logging.root.addHandler(ch)

logging.root.info('------------------- Program startup v{} -------------------'.format(
    pkg_resources.get_distribution('cct').version))

app = QApplication(sys.argv)

credo = Instrument(online='--online' in app.arguments()[1:])

oldexcepthook = sys.excepthook


def my_excepthook(type_, value, traceback_):
    # noinspection PyBroadException
    try:
        logging.root.critical(
            'Unhandled exception: ' + '\n'.join(traceback.format_exception(type_, value, traceback_)))
    except Exception:
        logging.root.critical(
            'Error in excepthook: ' + traceback.format_exc())
    oldexcepthook(type_, value, traceback_)


sys.excepthook = my_excepthook

if '--root' not in app.arguments()[1:]:
    ld = LogInDialog(credo)
    if ld.exec() == ld.Rejected:
        sys.exit(1)
else:
    try:
        credo.services['accounting'].select_user('root')
    except IndexError:
        credo.services['accounting'].add_user('root', 'Rootus', 'Systemus', PRIV_SUPERUSER)
        credo.services['accounting'].select_user('root')
mw = MainWindow(credo=credo)
mw.setWindowTitle(mw.windowTitle() + ' v{}'.format(pkg_resources.get_distribution('cct').version))
app.setWindowIcon(mw.windowIcon())
credo.start()
mw.show()
result = app.exec_()
logging.root.debug('QApplication exited.')
mw.deleteLater()
del mw
logging.root.debug('MW deleted.')
gc.collect()
logging.root.debug('Garbage collected.')
app.deleteLater()
del app
logging.root.debug('App deleted.')
gc.collect()
logging.root.debug('Garbage collected.')
del credo
logging.root.debug('Credo deleted.')
gc.collect()
logging.root.debug('Garbage collected.')

logging.root.debug('Exiting.')
sys.exit(result)
