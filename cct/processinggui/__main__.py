import logging
import sys

logging.basicConfig()
logging.root.setLevel(logging.DEBUG)
logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from PyQt5 import QtWidgets
from .mainwindow import Main

def run():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    main=Main()
    logger.debug('Instantiated main')
    main.show()
    if len(sys.argv) >1:
        main.project.open(sys.argv[1])
    logger.debug('Shown main')
    result=app.exec_()
    logger.debug('Main loop exited with result: {}'.format(result))
    del main
    del app
    sys.exit(result)

if __name__ == '__main__':
    run()