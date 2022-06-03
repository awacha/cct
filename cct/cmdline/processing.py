import logging
import multiprocessing
import sys
from typing import Optional

import click
from PyQt5 import QtWidgets

from .main import main
from ..qtgui2.processingmain.main import Main

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@main.command()
@click.option('--project', '-p', default=None, help='Project file to load')
def processing(project: Optional[str]):
    """Open the data processing GUI"""
    multiprocessing.set_start_method(
        'forkserver')  # the default 'fork' method is not appropriate for multi-threaded programs, e.g. with PyQt.
    app = QtWidgets.QApplication(sys.argv)
    mw = Main()
    if project is not None:
        mw.openProject(project)
    mw.show()
    logger.debug('Starting event loop')
    result = app.exec_()
    mw.deleteLater()
    app.deleteLater()
    sys.exit(result)
