import datetime
import logging
import os

import pkg_resources
from gi.repository import GtkSource, Gdk, Gtk, GLib

from ..core.dialogs import question_message, info_message
from ..core.filechooser import DoubleFileChooserDialog
from ..core.functions import notify
from ..core.toolwindow import ToolWindow
from ...core.commands.script import Script, Command
from ...core.utils.callback import SignalFlags

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

language_def_path = pkg_resources.resource_filename(
    'cct', 'resource/language-specs')
langman = GtkSource.LanguageManager.get_default()
langman.set_search_path(langman.get_search_path() + [language_def_path])


class ScriptMeasurement(ToolWindow, DoubleFileChooserDialog):
    def __init__(self, *args, **kwargs):
        self.sourcebuffer = None
        self._cmd = None
        self._scriptconnections = []
        self._pausingdlg = None
        self._pausingprogress = None
        self._pausingpulsehandler = None
        self._helpdialog = None
        super().__init__(*args, **kwargs)
        DoubleFileChooserDialog.__init__(self,
                                         self.widget, 'Open script...', 'Save script...',
                                         [('CCT script files', '*.cct'), ('All files', '*')],
                                         self.instrument.config['path']['directories']['scripts'],
                                         os.path.abspath(self.instrument.config['path']['directories']['scripts']),
                                         )

    def init_gui(self, *args, **kwargs):
        view = self.builder.get_object('sourceview')
        self.sourcebuffer = GtkSource.Buffer()
        view.set_buffer(self.sourcebuffer)
        self.sourcebuffer.set_language(langman.get_language('cct'))
        self.on_style_scheme_changed(self.builder.get_object('styleschemechooserbutton'),
                                     self.builder.get_object('styleschemechooserbutton').get_style_scheme())
        self.sourcebuffer.set_highlight_syntax(True)
        self.sourcebuffer.set_highlight_matching_brackets(True)
        self.sourcebuffer.set_modified(False)
        self.sourcebuffer.connect('modified-changed', self.on_modified_changed)
        self.sourcebuffer.connect('changed', self.on_sourcebuffer_changed)
        self.widget.set_title('Unnamed script')
        ma = GtkSource.MarkAttributes()
        ma.set_icon_name('media-playback-start')
        ma.set_background(Gdk.RGBA(0, 1, 0, 1))
        view.set_mark_attributes('Executing', ma, 0)

    def on_style_scheme_changed(self, sschooser: GtkSource.StyleSchemeChooserButton, newscheme):
        self.sourcebuffer.set_style_scheme(sschooser.get_style_scheme())

    def on_sourcebuffer_changed(self, sourcebuffer):
        self.builder.get_object('undo_toolbutton').set_sensitive(self.sourcebuffer.can_undo())

    def suggest_filename(self):
        return 'untitled.cct'

    def confirm_save(self):
        if self.sourcebuffer.get_modified():
            res = question_message(self.widget, 'Closing window',
                                   'Script has been modified. Do you want to save it first?')
            # noinspection PySimplifyBooleanCheck
            if res:
                self.on_toolbutton_save(self.builder.get_object('save_toolbutton'))
                self.sourcebuffer.set_modified(False)
                return True
            elif res is False:
                self.sourcebuffer.set_modified(False)
                return True
            else:
                return False
        return True

    def on_modified_changed(self, sourcebuffer):
        self.builder.get_object('save_toolbutton').set_sensitive(sourcebuffer.get_modified())
        title = self.widget.get_title()
        if title.endswith('*'):
            title = title[:-1].strip()
        if sourcebuffer.get_modified():
            self.widget.set_title(title + ' *')
        else:
            self.widget.set_title(title)

    def on_toolbutton_new(self, toolbutton):
        if not self.confirm_save():
            return
        self.sourcebuffer.set_text('')
        self.sourcebuffer.set_modified(False)
        self.set_last_filename(None)

    def on_toolbutton_open(self, toolbutton):
        if not self.confirm_save():
            return
        fn = self.get_open_filename()
        if fn is None:
            return
        try:
            with open(fn, 'rt', encoding='utf-8') as f:
                self.sourcebuffer.set_text(f.read())
            self.widget.set_title(fn)
            self.sourcebuffer.set_modified(False)
        except FileNotFoundError:
            self.error_message('Cannot open file: {}'.format(fn))

    def on_toolbutton_save(self, toolbutton):
        if self.get_last_filename() is None:
            self.on_toolbutton_saveas(toolbutton)
            return
        with open(self.get_last_filename(), 'wt', encoding='utf-8') as f:
            f.write(
                self.sourcebuffer.get_text(self.sourcebuffer.get_start_iter(), self.sourcebuffer.get_end_iter(), True))
        self.sourcebuffer.set_modified(False)

    def on_toolbutton_saveas(self, toolbutton):
        fn = self.get_save_filename()
        if fn is None:
            return
        if not fn.lower().endswith('.cct'):
            fn += '.cct'
            self.set_last_filename(fn)
        self.on_toolbutton_save(toolbutton)
        self.widget.set_title(fn)

    def on_toolbutton_undo(self, toolbutton):
        self.sourcebuffer.undo()
        assert isinstance(self.sourcebuffer, GtkSource.Buffer)
        toolbutton.set_sensitive(self.sourcebuffer.can_undo())
        self.builder.get_object('redo_toolbutton').set_sensitive(self.sourcebuffer.can_redo())

    def on_toolbutton_redo(self, toolbutton):
        self.sourcebuffer.redo()
        toolbutton.set_sensitive(self.sourcebuffer.can_redo())
        self.builder.get_object('undo_toolbutton').set_sensitive(self.sourcebuffer.can_undo())

    def on_toolbutton_cut(self, toolbutton):
        self.sourcebuffer.copy_clipboard(Gtk.Clipboard.get_default(Gdk.Display.get_default()))

    def on_toolbutton_copy(self, toolbutton):
        self.sourcebuffer.cut_clipboard(Gtk.Clipboard.get_default(Gdk.Display.get_default()),
                                        self._inhibit_close_reason is not None)

    def on_toolbutton_paste(self, toolbutton):
        self.sourcebuffer.paste_clipboard(Gtk.Clipboard.get_default(Gdk.Display.get_default()),
                                          self._inhibit_close_reason is not None)

    def on_toolbutton_execute(self, toolbutton):
        if toolbutton.get_label() == 'Execute':
            script = self.sourcebuffer.get_text(self.sourcebuffer.get_start_iter(),
                                                self.sourcebuffer.get_end_iter(),
                                                True)

            class MyScriptClass(Script):
                pass

            MyScriptClass.script = script

            flagsbb = self.builder.get_object('flags_buttonbox')
            for b in flagsbb:
                if b.get_active():
                    self.instrument.services['interpreter'].set_flag(b.get_label())
                else:
                    self.instrument.services['interpreter'].clear_flag(b.get_label())

            self.builder.get_object('sourceview').set_editable(False)

            self.write_message('----------------------- %s -----------------------\n' % str(datetime.datetime.now()),
                               False)

            try:
                self._cmd = self.execute_command(MyScriptClass, (), True,
                                                 additional_widgets=['sourceview', 'new_toolbutton', 'save_toolbutton',
                                                                     'saveas_toolbutton',
                                                                     'open_toolbutton', 'undo_toolbutton',
                                                                     'redo_toolbutton',
                                                                     'cut_toolbutton', 'copy_toolbutton',
                                                                     'paste_toolbutton',
                                                                     'help_toolbutton'])
            except Exception as exc:
                # this has already been handled by self.execute_command()
                return
            if self._cmd is None:
                return
            self._scriptconnections = [self._cmd.connect('cmd-start', self.on_command_start),
                                       self._cmd.connect('paused', self.on_script_paused)]
            toolbutton.set_label('Stop')
            toolbutton.set_icon_name('media-playback-stop')
        else:
            assert toolbutton.get_label() == 'Stop'
            self.instrument.services['interpreter'].kill()

    def write_message(self, message: str, timestamp=True):
        if self.get_last_filename() is None:
            return
        buf = self.builder.get_object('messagesbuffer')
        if timestamp:
            message = str(datetime.datetime.now()) + ': ' + message
        buf.insert(buf.get_end_iter(), message)
        self.builder.get_object('messagesview').scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        buf.place_cursor(buf.get_end_iter())
        try:
            with open(self.get_last_filename()[:-len('.cct')] + '.log', 'at', encoding='utf-8') as f:
                f.write(message)
        except AttributeError:
            pass

    def on_command_return(self, interpreter, commandname, returnvalue):
        info_message(self.widget, 'Script ended', 'Result: %s' % str(returnvalue))
        notify('Script ended', 'Script execution ended with result: {}'.format(returnvalue))
        super().on_command_return(interpreter, commandname, returnvalue)
        self.builder.get_object('execute_toolbutton').set_label('Execute')
        self.builder.get_object('execute_toolbutton').set_icon_name('media-playback-start')
        self.builder.get_object('sourceview').set_editable(True)
        self.sourcebuffer.remove_source_marks(
            self.sourcebuffer.get_start_iter(), self.sourcebuffer.get_end_iter(), 'Executing')
        self.builder.get_object('progressbar').set_text('')
        self.builder.get_object('progressbar').set_fraction(0)
        try:
            for c in self._scriptconnections:
                self._cmd.disconnect(c)
        finally:
            self._scriptconnections = None
            self._cmd = None

    def on_command_pulse(self, interpreter, commandname, message):
        pb = self.builder.get_object('progressbar')
        pb.set_visible(True)
        pb.set_text(message)
        pb.pulse()

    def on_command_progress(self, interpreter, commandname, message, fraction):
        pb = self.builder.get_object('progressbar')
        pb.set_visible(True)
        pb.set_text(message)
        pb.set_fraction(fraction)

    def on_command_message(self, interpreter, commandname, message):
        self.write_message(message + '\n')

    def on_command_start(self, script, lineno, command):
        it = self.sourcebuffer.get_iter_at_line(lineno)
        self.sourcebuffer.remove_source_marks(
            self.sourcebuffer.get_start_iter(), self.sourcebuffer.get_end_iter(), 'Executing')
        self.sourcebuffer.create_source_mark(
            'Line #%d' % lineno, 'Executing', it)
        self.builder.get_object('sourceview').scroll_to_iter(it, 0, False, 0, 0)
        self.sourcebuffer.place_cursor(it)
        self.builder.get_object('progressbar').hide()

    def on_toolbutton_pause(self, toolbutton):
        if toolbutton.get_active():
            self._cmd.pause()
            self._pausingdlg = Gtk.Dialog(
                'Waiting for script to pause', transient_for=self.widget,
                destroy_with_parent=True, use_header_bar=True, modal=True)
            self._pausingprogress = Gtk.ProgressBar()
            self._pausingprogress.set_text('Waiting for current command to complete...')
            self._pausingdlg.get_content_area().pack_start(self._pausingprogress, False, True, False)
            self._pausingdlg.show_all()
            self._pausingpulsehandler = GLib.timeout_add(300, self._pausing_pulse)
        else:
            self._cmd.resume()

    def _pausing_pulse(self):
        self._pausingprogress.pulse()
        return True

    def on_script_paused(self, script):
        try:
            GLib.source_remove(self._pausingpulsehandler)
            self._pausingdlg.destroy()
            self._pausingdlg = None
            self._pausingpulsehandler = None
            self._pausingprogress = None
            notify('Script has been paused', '')
        except AttributeError:
            pass


    def on_toolbutton_help(self, toolbutton):
        if self._helpdialog is None:
            self._helpdialog = CommandHelpDialog('help_commandhelpbrowser.glade', 'commandhelpbrowser',
                                                 self.instrument, 'Help on commands')
            self._helpdialog.connect('insert', self.on_insert)
        self._helpdialog.widget.show_all()

    def on_insert(self, helpdialog, text):
        self.sourcebuffer.insert_at_cursor(text)

    def on_close(self, widget, event=None):
        if not self.confirm_save():
            return
        ToolWindow.on_close(self, widget, event)

    def on_flag_toggled(self, flagtoggle):
        if flagtoggle.get_active():
            self.instrument.services['interpreter'].set_flag(flagtoggle.get_label())
        else:
            self.instrument.services['interpreter'].clear_flag(flagtoggle.get_label())

    def on_interpreter_flag(self, interpreter, flagname, newstate):
        logger.info('Flag state changed: %s, %s' % (flagname, newstate))
        tb = self.builder.get_object('flag' + flagname + '_button')
        if tb is None:
            raise ('No flag button: %s' % flagname)
        tb.set_active(newstate)
        return False


class CommandHelpDialog(ToolWindow):
    __signals__ = {'insert': (SignalFlags.RUN_FIRST, None, (str,))}

    def init_gui(self, *args, **kwargs):
        model = self.builder.get_object('commandnames')
        for command in sorted([c.name for c in Command.allcommands()]):
            model.append((command,))
        tc = Gtk.TreeViewColumn('Command', Gtk.CellRendererText(), text=0)
        self.builder.get_object('commandsview').append_column(tc)
        self.builder.get_object('commandsview').get_selection().select_iter(model.get_iter_first())

    def on_command_selected(self, treeviewselection):
        model, it = treeviewselection.get_selected()
        buf = self.builder.get_object('helptextbuffer')
        buf.set_text([c.__doc__ for c in Command.allcommands() if c.name == model[it][0]][0])

    def on_insert(self, button):
        model, it = self.builder.get_object('commandsview').get_selection().get_selected()
        self.emit('insert', model[it][0] + '()')
