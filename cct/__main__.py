import logging
import logging.handlers
import pickle
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
from cct.core2.config import Config
import cct.qtgui2.processingmain
from cct.core2.instrument.components.datareduction.datareductionpipeline import DataReductionPipeLine
from cct.core2.instrument.components.io import IO

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
@click.option('--config', '-c', default='config/cct.pickle', help='Config file', type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True, allow_dash=False, ))
@click.option('--online/--offline', default=False, help='Connect to devices')
@click.option('--root/--no-root', '-r', default=False, help='Skip login', type=bool, is_flag=True)
@click.option('--die-on-error/--dont-die-on-error', '-d', default=False, help='Die on an unhandled exception (for debugging)', type=bool, is_flag=True)
def daq(config:str, online: bool, root: bool, die_on_error: bool):
    """Open the data acquisition GUI mode"""
    handler = logging.handlers.TimedRotatingFileHandler('log/cct4.log', 'D', 1, encoding='utf-8', backupCount=0)
    handler.addFilter(logging.Filter('cct'))
    formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
    handler.setFormatter(formatter)
    logging.root.addHandler(handler)

    multiprocessing.set_start_method('forkserver')  # the default 'fork' method is not appropriate for multi-threaded programs, e.g. with PyQt.
    if not die_on_error:
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
@click.option('--project', '-p', default=None, help='Project file to load')
def processing(project: Optional[str]):
    """Open the data processing GUI"""
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


@main.command()
@click.option('--firstfsn', '-f', default=None, help='First file sequence number', type=click.IntRange(0), prompt='First file sequence number')
@click.option('--lastfsn', '-l', default=None, help='Last file sequence number', type=click.IntRange(0), prompt='Last file sequence number')
@click.option('--config', '-c', default='config/cct.pickle', help='Config file', type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True, allow_dash=False, ))
def datareduction(firstfsn: int, lastfsn: int, config):
    """Command-line data reduction routine"""
    config = Config(dicorfile=config)
    config.filename = None  # inhibit autosave
    io = IO(config=config, instrument=None)
    pipeline = DataReductionPipeLine(config.asdict())
    for fsn in range(firstfsn, lastfsn+1):
        try:
            ex = io.loadExposure(config['path']['prefixes']['crd'], fsn, raw=True, check_local=True)
        except FileNotFoundError:
            logger.warning(f'Cannot load exposure #{fsn}')
            continue
        pipeline.process(ex)


@main.command()
@click.option('--config', '-c', default='config/cct.pickle', help='Config file', type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True, allow_dash=False, ))
@click.option('--maxlevel', '-l', default=None, help='Maximum depth', type=int)
def dumpconfig(config, maxlevel):
    """Dump the contents of a config file"""
    with open(config, 'rb') as f:
        config = pickle.load(f)
    indentation='  '
    if not isinstance(maxlevel, int):
        maxlevel = -1
    if maxlevel < 0:
        maxlevel = None

    def dump(conf, level:int):
        if (maxlevel is not None) and (level > maxlevel):
            return
        if not isinstance(conf, dict):
            click.echo(f'{level*indentation}- {conf}')
            return
        for key in sorted(conf):
            if isinstance(conf[key], dict):
                click.echo(f'{level*indentation}{key}:')
                dump(conf[key], level+1)
            elif isinstance(conf[key], list):
                for entry in conf[key]:
                    dump(entry, level+1)
            else:
                click.echo(f'{indentation*level}{key}: {conf[key]}')
    dump(config, 0)


if __name__ == '__main__':
    main()
