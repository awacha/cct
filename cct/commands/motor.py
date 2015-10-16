from gi.repository import GLib
from .command import Command


class Moveto(Command):
    """Move motor

    Invocation: moveto(<motorname>, <position>)

    Arguments:
        <motorname>: name of the motor
        <position>: target position (physical units)

    Remarks:
        None
    """
    name = 'moveto'

    def execute(self, instrument, arglist, namespace):
        motorname = arglist[0]
        position = arglist[1]

        motor = instrument.motors[motorname]
        self._connections = [motor.connect('stop', self.on_stop, motorname),
                             motor.connect(
                                 'position-change', self.on_position_change, motorname),
                             motor.connect('error', self.on_error, motorname)]
        instrument.motors[motorname].moveto(position)

    def on_position_change(self, motor, newpos, motorname):
        self.emit('pulse', 'Moving motor %s: %-8.2f' % (motorname, newpos))

    def on_stop(self, motor, targetreached, motorname):
        try:
            for c in self._connections:
                motor.disconnect(c)
            del self._connections
        except AttributeError:
            pass
        self.emit('return', targetreached)

    def on_error(self, motor, propname, exc, tb, motorname):
        self.emit('fail', exc, tb)


class Moverel(Command):
    """Move motor relatively

    Invocation: moverel(<motorname>, <position>)

    Arguments:
        <motorname>: name of the motor
        <position>: target position (physical units), relative to the present

    Remarks:
        None
    """
    name = 'moverel'

    def execute(self, instrument, arglist, namespace):
        motorname = arglist[0]
        position = arglist[1]

        motor = instrument.motors[motorname]
        self._connections = [motor.connect('stop', self.on_stop, motorname),
                             motor.connect(
                                 'position-change', self.on_position_change, motorname),
                             motor.connect('error', self.on_error, motorname)]
        instrument.motors[motorname].moverel(position)

    def on_position_change(self, motor, newpos, motorname):
        self.emit('pulse', 'Moving motor %s: %-8.2f' % (motorname, newpos))

    def on_stop(self, motor, targetreached, motorname):
        try:
            for c in self._connections:
                motor.disconnect(c)
            del self._connections
        except AttributeError:
            pass
        self.emit('return', targetreached)

    def on_error(self, motor, propname, exc, tb, motorname):
        self.emit('fail', exc, tb)


class Where(Command):
    """Get current motor position(s)

    Invocation: where([<motorname>])

    Arguments:
        <motorname>: if given, return with the position of just this motor

    Remarks:
        None
    """

    name = 'where'

    def execute(self, instrument, arglist, namespace):
        if arglist:
            ret = instrument.motors[arglist[0]].where()
            txt = arglist[0] + ': %8.3f' % ret
        else:
            longestmotorname = max(
                max([len(m) for m in instrument.motors]), len('Motor name'))

            heading = '| ' + \
                ('%%-%ds' % longestmotorname) % 'Motor name' + \
                ' | Position |'
            separator = '+' + '-' * (len(heading) - 2) + '+'
            ret = dict([(m, instrument.motors[m].where())
                        for m in instrument.motors])
            txt = '\n'.join(
                [separator, heading, separator] + [('| %%-%ds | %%8.3f |' % longestmotorname) % (m, ret[m]) for m in sorted(ret)] + [separator])
        GLib.idle_add(lambda m=txt, r=ret: self._idlefunc(m, r))

    def _idlefunc(self, message, ret):
        self.emit('message', message)
        self.emit('return', ret)
        return False
