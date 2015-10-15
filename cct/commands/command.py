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
    is the argument list of this command. The last argument is a dictionary of the
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

    The member function kill() signifies the running command that it should
    stop and emit the 'return' signal immediately, or as soon as possible.
    Short-running commands (runtime is at most 5 seconds) might ignore this
    function.

    As a general rule, signals must not be emitted from the execute, simulate
    and kill member functions. Use idle functions or callbacks for this.
    """
    __gsignals__ = {
        # emitted when the command completes. Must be emitted exactly once
        'return': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        # emitted on a failure. Can be emitted multiple times
        'fail': (GObject.SignalFlags.RUN_LAST, None, (object, str)),
        # long running commands where the duration cannot be
        # estimated in advance, should emit this periodically (say
        # in every second)
        'pulse': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # long running commands where the duration can be estimated
        # in advance, this should be emitted periodically (e.g. in
        # every second)
        'progress': (GObject.SignalFlags.RUN_FIRST, None, (str, float)),
        # send occasional messages to the command interpreter (to
        # be written to a terminal or logged at the INFO level.
        'message': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }

    name = '__abstract__'

    def __init__(self):
        GObject.GObject.__init__(self)

    def execute(self, instrument, arglist, namespace):
        pass

    def simulate(self, instrument, arglist, namespace):
        pass

    def kill(self):
        pass
