import logging
import sys

import colorlog
from PyQt5 import QtCore

from .instrument.instrument import Instrument

# logging.basicConfig()
logging.root.setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(levelname)s:%(name)s:%(message)s'
))

logging.root.addHandler(handler)


def main():
    app = QtCore.QCoreApplication(sys.argv)
    logger.debug('Instantiating Instrument()')
    instrument = Instrument()
    logger.debug('Starting event loop')
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
