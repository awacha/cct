import cct.instrument.instrument
from cct.services import InterpreterError
import readline
import traceback
from gi.repository import GLib, Gtk

ins = cct.instrument.instrument.Instrument()
ins.connect_devices()


class CCTTerm(object):
    prompt = 'cct %d> '
    Npulse = 5

    def __init__(self, instrument):
        self.index = 0
        self.pulser = 0
        self.instrument = instrument
        self.instrument.interpreter.connect('cmd-message', self.on_message)
        self.instrument.interpreter.connect('pulse', self.on_pulse)
        self.instrument.interpreter.connect('progress', self.on_progress)
        self.instrument.interpreter.connect('cmd-return', self.on_return)
        self.instrument.interpreter.connect('cmd-fail', self.on_fail)
        print('Known commands:', ', '.join(
            self.instrument.interpreter.commands.keys()))

    def on_message(self, interpreter, command, message):
        print(message + '\n')

    def on_pulse(self, interpreter, command, message):
        print('\r' + message + ' ' + ' ' * self.pulser +
              '.' + ' ' * (self.Npulse - self.pulser), end='')
        self.pulser = (self.pulser + 1) % self.Npulse

    def on_progress(self, interpreter, command, message, fraction):
        print('\r' + message + ' ' + 'Complete: %6.1f %%' %
              (fraction * 100), end='')

    def give_prompt(self):
        self.index += 1
        try:
            cmdline = input(self.prompt % self.index)
        except EOFError:
            Gtk.main_quit()
            return
        self.pulser = 0
        try:
            self.instrument.interpreter.execute_command(cmdline)
        except InterpreterError:
            print('\n\x1b[31mUnknown command in line: %s\x1b[m' % cmdline)
            print('\n\x1b[31m' + traceback.format_exc() + '\x1b[m')
            GLib.idle_add(term.give_prompt)
        except Exception:
            print('\n\x1b[31mError while running command: %s\x1b[m' % cmdline)
            print('\n\x1b[31m' + traceback.format_exc() + '\x1b[m')
            GLib.idle_add(term.give_prompt)
        return False

    def on_return(self, interpreter, command, result):
        print('\nResult: %s' % str(result))
        self.give_prompt()

    def on_fail(self, interpreter, command, exc, tb):
        print('\n\x1b[31m' + str(exc) + '\n' + tb + '\x1b[m')

term = CCTTerm(ins)

GLib.idle_add(term.give_prompt)
Gtk.main()
