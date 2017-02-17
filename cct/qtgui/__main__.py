import logging.handlers
import sys

import pkg_resources
from PyQt5.QtWidgets import QApplication

from .accounting.logindialog import LogInDialog
from .mainwindow import MainWindow
from .mainwindow.collectinghandler import CollectingHandler
from ..core.instrument.instrument import Instrument

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
ch = CollectingHandler()
logging.root.addHandler(ch)

logging.root.info('------------------- Program startup v{} -------------------'.format(
    pkg_resources.get_distribution('cct').version))


app = QApplication(sys.argv)

credo = Instrument(online='--online' in app.arguments()[1:])

if '--root' not in app.arguments()[1:]:
    ld = LogInDialog(credo)
    if ld.exec() == ld.Rejected:
        sys.exit(1)

mw = MainWindow(credo=credo)
mw.show()
sys.exit(app.exec_())