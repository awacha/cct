from  PyQt5.QtCore import QTimer

class TimeOut(object):
    def __init__(self, interval:int, function, start:bool=True, singleShot=False):
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
        self.timer.timeout.disconnect()

class IdleFunction(object):
    def __init__(self, function, interval=100, *args, **kwargs):
        self.function = function
        self.interval = interval
        self.args = args
        self.kwargs = kwargs
        self.timer = QTimer(None)
        self.timer.setSingleShot(False)
        self.timer.setInterval(0) # schedule the first timeout to as soon as possible
        self.timer.timeout.connect(self.onTimeout)
        self.timer.start()

    def onTimeout(self):
        if self.function(*self.args, **self.kwargs):
            self.timer.setInterval(self.interval) # avoid too frequent subsequent calls
        else:
            self.stop()

    def stop(self):
        self.timer.stop()
        self.timer.timeout.disconnect()

class SingleIdleFunction(IdleFunction):
    def onTimeout(self):
        super().onTimeout()
        self.stop()