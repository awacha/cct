from gi.repository import GObject


class Command(GObject.GObject):
    """This is an abstract base class for a command, which can be issued in
    order to do something on the instrument, e.g. move a motor or take an
    exposure.

    The `name` class variable is the command name: this will be used to
    determine which command has to be run from a command line.

    The most important part is the `execute()` method, which _starts_ the
    operation, then returns. This method gets three arguments: `instrument`,
    which is the singleton object corresponding to the whole beamline, from
    which all the devices and state variables can be obtained. The second one
    is the full command line pertaining to this command, usually in the form
    'command(arg1, arg2, arg3, ...)'. The last argument is a dictionary of the
    environment (namespace) the command runs in.

    The `simulate()` should do everything as `execute()` can, without talking
    to devices.  

    When the command is finished, the 'return' signal should be emitted and 
    the results of the command, i.e. a scattering pattern, a floating point
    variable, or any kind of Python object must be sent. This signal MUST be
    emitted even if some error or failure happened.

    Failures can be signaled through the 'fail' signal: its first argument
    is the exception object, the second one is the formatted traceback.

    Long-running commands might want to emit the 'pulse' or 'progress' signals
    frequently, thus the user interface can have a clue if the command is
    still running or not.

    Other signals can also be defined by the user.
    """
    __gsignals__ = {'return': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'fail': (GObject.SignalFlags.RUN_LAST, None, (object, str)),
                    'pulse': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'progress': (GObject.SignalFlags.RUN_FIRST, None, (str, float))}

    def __init__(self):
        GObject.GObject.__init__(self)

    def execute(self, instrument, commandline, namespace):
        pass

    def simulate(self, instrument, commandline, namespace):
        pass
