import logging

from PyQt5.QtCore import QTimer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class TimeOut(object):
    def __init__(self, interval: int, function, start: bool = True, singleShot=False):
        self.function = function
        self.timer = QTimer(None)
        self.timer.setInterval(interval)
        self.timer.setSingleShot(singleShot)
        if start:
            self.start()

    def onTimeout(self):
        if not self.function():
            self.stop()

    def start(self):
        self.timer.timeout.connect(self.onTimeout)
        self.timer.start()

    def stop(self):
        self.timer.stop()
        if self.timer.receivers(self.timer.timeout):
            self.timer.timeout.disconnect()


class IdleFunction(object):
    def __init__(self, function, interval=0, *args, **kwargs):
        self.function = function
        self.interval = interval
        self.args = args
        self.kwargs = kwargs
        self.timer = QTimer(None)
        self.timer.setSingleShot(False)
        self.timer.setInterval(0)  # schedule the first timeout to as soon as possible
        self.timer.timeout.connect(self.onTimeout)
        self.timer.start()
        logger.debug('Timer started in an IdleFunction')

    def onTimeout(self):
        try:
            logger.debug('onTimeout in an IdleFunction. Name: {}'.format(self.kwargs['name']))
        except KeyError:
            pass
        if self.function(*self.args, **self.kwargs):
            self.timer.setInterval(self.interval)  # avoid too frequent subsequent calls
        else:
            self.stop()

    def stop(self):
        self.timer.stop()
        if self.timer.receivers(self.timer.timeout):
            self.timer.timeout.disconnect()


class SingleIdleFunction(object):
    instances = []

    def __init__(self, function, *args, **kwargs):
        self.function = function
        self.args = args
        self.kwargs = kwargs
        QTimer.singleShot(0, self.onTimeout)
        logger.debug('Initialized a SingleIdleFunction')
        type(self).instances.append(self)

    def onTimeout(self):
        logger.debug('Timeout in a SingleIdleFunction')
        self.function(*self.args, **self.kwargs)
        del self.function
        del self.kwargs
        del self.args
        type(self).instances.remove(self)

    def __del__(self):
        logger.debug('Deleting a SingleIdleFunction')
