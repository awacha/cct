import datetime
import logging
import os

import pkg_resources
from gi.repository import GtkSource, Gdk, Gtk, Notify, GLib

from ..core.dialogs import question_message, info_message
from ..core.functions import notify
from ..core.toolwindow import ToolWindow
from ...core.commands.script import Script, Command
from ...core.utils.callback import SignalFlags

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ToDo: closing the script window results in GtkWarnings (not a GTK_WIDGET etc.). Something to do with buffer marks.

language_def_path = pkg_resources.resource_filename(
    'cct', 'resource/language-specs')
langman = GtkSource.LanguageManager.get_default()
langman.set_search_path(langman.get_search_path() + [language_def_path])


class ScriptMeasurement(ToolWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sourcebuffer = None
        self.filename = None
        self.filename_folder = None
        self.filechooser_open = None
        self.filechooser_save = None
        self._cmd = None

    def init_gui(self, *args, **kwargs):
        view = self.builder.get_object('sourceview')
        self.sourcebuffer = GtkSource.Buffer()
        view.set_buffer(self.sourcebuffer)
        self.sourcebuffer.set_language(langman.get_language('cct'))
        ssman = GtkSource.StyleSchemeManager.get_default()
        self.sourcebuffer.set_style_scheme(
            ssman.get_scheme(ssman.get_scheme_ids()[0]))
        self.sourcebuffer.set_highlight_syntax(True)
        self.sourcebuffer.set_highlight_matching_brackets(True)
        self.sourcebuffer.set_modified(False)
        self.sourcebuffer.connect('modified-changed', self.on_modified_changed)
        self.widget.set_title('Unnamed script')
        ma = GtkSource.MarkAttributes()
        ma.set_icon_name('media-playback-start')
        ma.set_background(Gdk.RGBA(0, 1, 0, 1))
        view.set_mark_attributes('Executing', ma, 0)

        self.filechooser_open = Gtk.FileChooserDialog('Open script file', self.widget, Gtk.FileChooserAction.OPEN,
                                                      ['OK', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL])
        self.filechooser_open.add_shortcut_folder(os.path.join(os.getcwd(), 'scripts'))
        self.filechooser_open.set_transient_for(self.widget)
        self.filechooser_save = Gtk.FileChooserDialog('Save script file as...', self.widget,
                                                      Gtk.FileChooserAction.SAVE,
                                                      ['OK', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL])
        self.filechooser_save.add_shortcut_folder(os.path.join(os.getcwd(), 'scripts'))
        self.filechooser_save.set_do_overwrite_confirmation(True)
        self.filechooser_save.set_transient_for(self.widget)

    def confirm_save(self):
        if self.sourcebuffer.get_modified():
            res = question_message(self.widget, 'Closing window',
                                   'Script has been modified. Do you want to save it first?')
            # noinspection PySimplifyBooleanCheck
            if res:
                self.on_toolbutton_save(self.builder.get_object('save_toolbutton'))
                self.sourcebuffer.set_modified(False)
                return True
            elif res == False:
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
        self.filename = None

    def on_toolbutton_open(self, toolbutton):
        if not self.confirm_save():
            return
        if self.filename is not None:
            self.filechooser_open.set_filename(self.filename)
            self.filechooser_open.set_current_folder(self.filename)
        if self.filechooser_open.run() == Gtk.ResponseType.OK:
            self.filename = self.filechooser_open.get_filename()
            self.widget.set_title(self.filename)
            self.filechooser_open.set_filename(self.filename)
        self.filechooser_open.hide()
        with open(self.filename, 'rt', encoding='utf-8') as f:
            self.sourcebuffer.set_text(f.read())
        self.sourcebuffer.set_modified(False)

    def on_toolbutton_save(self, toolbutton):
        if self.filename is None:
            self.on_toolbutton_saveas(toolbutton)
        with open(self.filename, 'wt', encoding='utf-8') as f:
            f.write(
                self.sourcebuffer.get_text(self.sourcebuffer.get_start_iter(), self.sourcebuffer.get_end_iter(), True))
        self.sourcebuffer.set_modified(False)

    def on_toolbutton_saveas(self, toolbutton):
        if self.filename is not None:
            self.filechooser_save.set_filename(self.filename)
            self.filechooser_save.set_current_folder(self.filename)
        else:
            self.filechooser_save.set_current_folder(os.path.join(os.getcwd(), 'scripts'))
            self.filechooser_save.set_current_name('sequence.cct')
        if self.filechooser_save.run() == Gtk.ResponseType.OK:
            self.filename = self.filechooser_save.get_filename()
            if not self.filename.lower().endswith('.cct'):
                self.filename += '.cct'
            self.filechooser_save.set_filename(self.filename)
            self.widget.set_title(self.filename)
            self.on_toolbutton_save(toolbutton)
        self.filechooser_save.hide()

    def on_toolbutton_undo(self, toolbutton):
        self.sourcebuffer.undo()

    def on_toolbutton_redo(self, toolbutton):
        self.sourcebuffer.redo()

    def on_toolbutton_cut(self, toolbutton):
        self.sourcebuffer.copy_clipboard(Gtk.Clipboard.get_default(Gdk.Display.get_default()))

    def on_toolbutton_copy(self, toolbutton):
        self.sourcebuffer.cut_clipboard(Gtk.Clipboard.get_default(Gdk.Display.get_default()),
                                        self._inhibit_close_reason is not None)

    def on_toolbutton_paste(self, toolbutton):
        self.sourcebuffer.paste_clipboard(Gtk.Clipboard.get_default(Gdk.Display.get_default()),
                                          self._inhibit_close_reason is not None)

    def on_toolbutton_execute(self, toolbutton):
        script = self.sourcebuffer.get_text(self.sourcebuffer.get_start_iter(),
                                            self.sourcebuffer.get_end_iter(),
                                            True)

        class MyScriptClass(Script):
            script = script


        flagsbb = self.builder.get_object('flags_buttonbox')
        for b in flagsbb:
            if b.get_active():
                self.instrument.services['interpreter'].set_flag(b.get_label())
            else:
                self.instrument.services['interpreter'].clear_flag(b.get_label())

        self.builder.get_object('sourceview').set_editable(False)

        self.write_message('----------------------- %s -----------------------\n' % str(datetime.datetime.now()), False)

        try:
            self._cmd = self.execute_command(MyScriptClass, (), True,
                                             additional_widgets=['sourceview', 'new_toolbutton', 'save_toolbutton',
                                                                 'saveas_toolbutton',
                                                                 'open_toolbutton', 'undo_toolbutton',
                                                                 'redo_toolbutton',
                                                                 'cut_toolbutton', 'copy_toolbutton',
                                                                 'paste_toolbutton',
                                                                 'help_toolbutton', 'execute_toolbutton'])
        except Exception:
            # this has already been handled by self.execute_command()
            return
        self._scriptconnections = [self._cmd.connect('cmd-start', self.on_command_start),
                                   self._cmd.connect('paused', self.on_script_paused)]

    def write_message(self, message: str, timestamp=True):
        buf = self.builder.get_object('messagesbuffer')
        if timestamp:
            message = str(datetime.datetime.now()) + ': ' + message
        buf.insert(buf.get_end_iter(), message)
        self.builder.get_object('messagesview').scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        buf.place_cursor(buf.get_end_iter())
        try:
            with open(self.filename[:-len('.cct')] + '.log', 'at', encoding='utf-8') as f:
                f.write(message)
        except AttributeError:
            pass

    def on_command_return(self, interpreter, commandname, returnvalue):
        info_message(self.widget, 'Script ended', 'Result: %s' % str(returnvalue))
        notify('Script ended', 'Script execution ended with result: {}'.format(returnvalue))
        super().on_command_return(interpreter, commandname, returnvalue)
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
            self._pausingdlg = Gtk.Dialog('Waiting for script to pause', self.widget,
                                          Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.USE_HEADER_BAR | Gtk.DialogFlags.MODAL,
                                          )
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
            del self._pausingdlg
            del self._pausingpulsehandler
            del self._pausingprogress
            notif = Notify.Notification.new('Script has been paused')
            notif.show()
        except AttributeError:
            pass

    def on_toolbutton_stop(self, toolbutton):
        self.instrument.services['interpreter'].kill()

    def on_toolbutton_help(self, toolbutton):
        if not hasattr(self, '_helpdialog'):
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

    def init_gui(self, *args):
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
