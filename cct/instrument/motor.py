from gi.repository import GObject
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Motor(GObject.GObject):
    """High-level interface for a motor. Nothing more than a wrapper for the
    actual functionality of the lower level motor controllers. This way
    the motors can be decoupled."""

    __gsignals__ = {'variable-change': (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
                    'error': (GObject.SignalFlags.RUN_LAST, None, (str, object)),
                    'position-change': (GObject.SignalFlags.RUN_FIRST, None, (float,)),
                    'stop': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    }

    def __init__(self, controller, index):
        GObject.GObject.__init__(self)
        self._controller = controller
        self._index = index
        self._connection = [self._controller.connect(
            'variable-change', self.on_variable_change),
            self._controller.connect('error', self.on_error)]

    def on_variable_change(self, controller, variable, newvalue):
        try:
            variable, index = variable.rsplit('$', 1)
            index = int(index)
        except ValueError:
            return  # message cannot be split: not for us
        if index != self._index:
            return  # message not for us
        if variable == '_status' and newvalue == 'idle':
            self.emit('stop', self.get_variable('targetpositionreached'))
        if variable == 'actualposition':
            self.emit('position-change', newvalue)
        self.emit('variable-change', variable, newvalue)

    def on_error(self, controller, variable, errmsg):
        try:
            if variable.split('$')[-1] != str(self._index):
                return False
        except AttributeError:
            return False
        self.emit('error', variable.rsplit('$')[0], errmsg)

    def get_variable(self, varname):
        return self._controller.get_variable(varname + '$%d' % self._index)

    def refresh_variable(self, varname):
        return self._controller.refresh_variable(varname + '$%d' % self._index)

    def set_variable(self, varname, value):
        return self._controller.set_variable(varname + '$%d' % self._index, value)

    def where(self):
        return self._controller.where(self._index)

    def moveto(self, position):
        return self._controller.moveto(self._index, position)

    def moverel(self, position):
        return self._controller.moverel(self._index, position)

    def calibrate(self, position):
        return self._controller.calibrate(self._index, position)

    def stop(self):
        return self._controller.stop(self._index)

    def ismoving(self):
        return self.get_variable('actualspeed') != 0

    def __del__(self):
        try:
            self._controller.disconnect(self._connection)
            del self._connection
        except AttributeError:
            pass
