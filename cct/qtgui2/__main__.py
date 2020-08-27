import logging
import sys
import traceback

import click
import colorlog
from PyQt5 import QtWidgets

from cct.core2.instrument.instrument import Instrument
from cct.qtgui2.main.mainwindow import MainWindow

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
    logging.root.critical(f'Uncaught exception: {exc}\nTraceback:\n{"".join(traceback.format_tb(tb))}')


@click.command()
@click.option('--config', default='config/cct.pickle', help='Config file')
@click.option('--online', default=False, help='Connect to devices', type=bool, is_flag=True)
def main(config:str, online: bool):
    sys.excepthook = excepthook
    app = QtWidgets.QApplication(sys.argv)
    logger.debug('Instantiating Instrument()')
    instrument = Instrument(configfile=config, online=online)
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


if __name__ == '__main__':
    main()