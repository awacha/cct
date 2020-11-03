import logging
import sys
import traceback
import multiprocessing
from typing import Optional

import click
import colorlog
from PyQt5 import QtWidgets

from cct.core2.instrument.instrument import Instrument
from cct.qtgui2.main.mainwindow import MainWindow
from cct.qtgui2.main.logindialog import LoginDialog
import cct.qtgui2.processingmain

# logging.basicConfig()
logging.root.setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logging.getLogger('matplotlib').setLevel(logging.INFO)
#logging.getLogger('matplotlib.font_manager').setLevel(logging.INFO)
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s %(levelname)s:%(name)s:%(message)s'
))

logging.root.addHandler(handler)


def excepthook(exctype, exc, tb):
    logging.root.critical(f'Uncaught exception: {repr(exc)}\nTraceback:\n{"".join(traceback.format_tb(tb))}')


@click.group()
def main():
    pass


@main.command()
@click.option('--config', default='config/cct.pickle', help='Config file')
@click.option('--online', default=False, help='Connect to devices', type=bool, is_flag=True)
@click.option('--root', default=False, help='Skip login', type=bool, is_flag=True)
def daq(config:str, online: bool, root: bool):
    multiprocessing.set_start_method('forkserver')  # the default 'fork' method is not appropriate for multi-threaded programs, e.g. with PyQt.
    sys.excepthook = excepthook
    app = QtWidgets.QApplication(sys.argv)
    logger.debug('Instantiating Instrument()')
    instrument = Instrument(configfile=config)
    if not root:
        logindialog = LoginDialog()
        logindialog.setOffline(not online)
        while True:
            logger.debug('Starting new logindialog iteration')
            result = logindialog.exec()
            if result == QtWidgets.QDialog.Accepted:
                if logindialog.authenticate():
                    logger.debug('Successful authentication')
                    break
                else:
                    logger.debug('Failed authentication')
                    continue
            else:
                logger.debug('Cancelled, exiting')
                logindialog.deleteLater()
                instrument.deleteLater()
                app.deleteLater()
                sys.exit()
        online = not logindialog.isOffline()
        logindialog.deleteLater()
    else:
        instrument.auth.setRoot()
    instrument.setOnline(online)
    mw = MainWindow(instrument=instrument)
    mw.show()
    instrument.start()
    logger.debug('Starting event loop')
    result = app.exec_()
    mw.deleteLater()
    instrument.deleteLater()
#    gc.collect()
    app.deleteLater()
#    gc.collect()
    sys.exit(result)


@main.command()
@click.option('--project', default=None, help='Project file to load')
def processing(project: Optional[str]):
    multiprocessing.set_start_method('forkserver')  # the default 'fork' method is not appropriate for multi-threaded programs, e.g. with PyQt.
    sys.excepthook = excepthook
    app = QtWidgets.QApplication(sys.argv)
    mw = cct.qtgui2.processingmain.main.Main()
    mw.show()
    logger.debug('Starting event loop')
    result = app.exec_()
    mw.deleteLater()
    app.deleteLater()
    sys.exit(result)



if __name__ == '__main__':
    main()
