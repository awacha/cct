import logging
import logging.handlers
import multiprocessing
import os
import sys

import click
from PyQt5 import QtWidgets

from .main import main
from ..core2.instrument.instrument import Instrument
from ..qtgui2.main.logindialog import LoginDialog
from ..qtgui2.main.mainwindow import MainWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@main.command()
@click.option('--config', '-c', default='config/cct.pickle', help='Config file',
              type=click.Path(file_okay=True, dir_okay=False, writable=True, readable=True,
                              allow_dash=False, ))
@click.option('--online/--offline', default=False, help='Connect to devices')
@click.option('--root/--no-root', '-r', default=False, help='Skip login', type=bool, is_flag=True)
def daq(config: str, online: bool, root: bool):
    """Open the data acquisition GUI mode"""
    os.makedirs('log', exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler('log/cct4.log', 'D', 1, encoding='utf-8', backupCount=0)
    handler.addFilter(logging.Filter('cct'))
    formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
    handler.setFormatter(formatter)
    logging.root.addHandler(handler)

    multiprocessing.set_start_method(
        'forkserver')  # the default 'fork' method is not appropriate for multi-threaded programs, e.g. with PyQt.
    app = QtWidgets.QApplication(sys.argv)
    logger.debug('Instantiating Instrument()')
    instrument = Instrument(configfile=config)
    logger.debug('Instrument() done.')
    if not root:
        while True:
            logger.debug('Starting new logindialog iteration')
            logger.debug('Opening login dialog')
            logindialog = LoginDialog()
            logindialog.setOffline(not online)
            result = logindialog.exec()
            if result == QtWidgets.QDialog.Accepted:
                if logindialog.authenticate():
                    logger.debug('Successful authentication')
                    online = not logindialog.isOffline()
                    logindialog.deleteLater()
                    break
                else:
                    logger.debug('Failed authentication')
                    logindialog.deleteLater()
                    continue
            else:
                logger.debug('Cancelled, exiting')
                logindialog.deleteLater()
                instrument.deleteLater()
                app.deleteLater()
                sys.exit()
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
