import datetime
import logging
import os

import pkg_resources
from gi.repository import GtkSource, Gdk, Gtk, GObject, GdkPixbuf, Notify, GLib

from ..core.toolwindow import ToolWindow, question_message, error_message, info_message
from ...core.commands.script import Script, Command

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ToDo: closing the script window results in GtkWarnings (not a GTK_WIDGET etc.). Something to do with buffer marks.

language_def_path = pkg_resources.resource_filename(
    'cct', 'resource/language-specs')
langman = GtkSource.LanguageManager.get_default()
langman.set_search_path(langman.get_search_path() + [language_def_path])


class ScriptMeasurement(ToolWindow):
    def _init_gui(self, *args):
        view=self._builder.get_object('sourceview')
        self._sourcebuffer=GtkSource.Buffer()
        view.set_buffer(self._sourcebuffer)
        self._sourcebuffer.set_language(langman.get_language('cct'))
        ssman = GtkSource.StyleSchemeManager.get_default()
        self._sourcebuffer.set_style_scheme(
            ssman.get_scheme(ssman.get_scheme_ids()[0]))
        self._sourcebuffer.set_highlight_syntax(True)
        self._sourcebuffer.set_highlight_matching_brackets(True)
        self._sourcebuffer.set_modified(False)
        self._sourcebuffer.connect('modified-changed', self.on_modified_changed)
        self._window.set_title('Unnamed script')
        ma = GtkSource.MarkAttributes()
        ma.set_icon_name('media-playback-start')
        ma.set_background(Gdk.RGBA(0, 1, 0, 1))
        view.set_mark_attributes('Executing', ma, 0)

    def confirm_save(self):
        if self._sourcebuffer.get_modified():
            if question_message(self._window,'Script has been modified. Do you want to save it first?'):
                self.on_toolbutton_save(self._builder.get_object('save_toolbutton'))
                self._sourcebuffer.set_modified(False)
                return True
        self._sourcebuffer.set_modified(False)
        return False


    def on_modified_changed(self, sourcebuffer):
        self._builder.get_object('save_toolbutton').set_sensitive(sourcebuffer.get_modified())
        title=self._window.get_title()
        if title.endswith('*'):
            title=title[:-1].strip()
        if sourcebuffer.get_modified():
            self._window.set_title(title+' *')
        else:
            self._window.set_title(title)

    def on_toolbutton_new(self, toolbutton):
        self.confirm_save()
        self._sourcebuffer.set_text('')
        self._sourcebuffer.set_modified(False)

    def on_toolbutton_open(self, toolbutton):
        self.confirm_save()
        if not hasattr(self, '_filechooser_open'):
            self._filechooser_open = Gtk.FileChooserDialog('Open script file', self._window, Gtk.FileChooserAction.OPEN,
                                                      ['OK', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL])
            self._filechooser_open.add_shortcut_folder(os.path.join(os.getcwd(),'scripts'))
        self._filechooser_open.set_action(Gtk.FileChooserAction.OPEN)
        self._filechooser_open.set_title('Open script file')
        self._filechooser_open.set_transient_for(self._window)
        if hasattr(self, '_filename'):
            self._filechooser_open.set_filename(self._filename)
            self._filechooser_open.set_current_folder(self._filename)
        if self._filechooser_open.run()==Gtk.ResponseType.OK:
            self._filename=self._filechooser_open.get_filename()
            self._window.set_title(self._filename)
            self._filechooser_open.set_filename(self._filename)
        self._filechooser_open.hide()
        with open(self._filename, 'rt', encoding='utf-8') as f:
            self._sourcebuffer.set_text(f.read())
        self._sourcebuffer.set_modified(False)

    def on_toolbutton_save(self, toolbutton):
        if not hasattr(self, '_filename'):
            self.on_toolbutton_saveas(toolbutton)
        with open(self._filename, 'wt', encoding='utf-8') as f:
            f.write(self._sourcebuffer.get_text(self._sourcebuffer.get_start_iter(), self._sourcebuffer.get_end_iter(), True))
        self._sourcebuffer.set_modified(False)

    def on_toolbutton_saveas(self, toolbutton):
        if not hasattr(self, '_filechooser_save'):
            self._filechooser_save = Gtk.FileChooserDialog('Save script file as...', self._window,
                                                      Gtk.FileChooserAction.SAVE, ['OK', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL])
            self._filechooser_save.add_shortcut_folder(os.path.join(os.getcwd(),'scripts'))
        self._filechooser_save.set_action(Gtk.FileChooserAction.SAVE)
        self._filechooser_save.set_do_overwrite_confirmation(True)
        self._filechooser_save.set_title('Save script file as...')
        self._filechooser_save.set_transient_for(self._window)
        if hasattr(self, '_filename'):
            self._filechooser_save.set_filename(self._filename)
            self._filechooser_save.set_current_folder(self._filename)
        if self._filechooser_save.run()==Gtk.ResponseType.OK:
            self._filename=self._filechooser_save.get_filename()
            if not self._filename.lower().endswith('.cct'):
                self._filename=self._filename+'.cct'
            self._filechooser_save.set_filename(self._filename)
            self._window.set_title(self._filename)
            self.on_toolbutton_save(toolbutton)
        self._filechooser_save.hide()

    def on_toolbutton_undo(self, toolbutton):
        self._sourcebuffer.undo()

    def on_toolbutton_redo(self, toolbutton):
        self._sourcebuffer.redo()

    def on_toolbutton_cut(self, toolbutton):
        self._sourcebuffer.copy_clipboard(Gtk.Clipboard.get_default(Gdk.Display.get_default()))

    def on_toolbutton_copy(self, toolbutton):
        self._sourcebuffer.cut_clipboard(Gtk.Clipboard.get_default(Gdk.Display.get_default()),
                                         self._inhibit_close_reason is not None)

    def on_toolbutton_paste(self, toolbutton):
        self._sourcebuffer.paste_clipboard(Gtk.Clipboard.get_default(Gdk.Display.get_default()),
                                           self._inhibit_close_reason is not None)

    def on_toolbutton_execute(self, toolbutton):
        self._scriptcommand=Script(self._sourcebuffer.get_text(self._sourcebuffer.get_start_iter(),
                                                               self._sourcebuffer.get_end_iter(),
                                                               True))
        self._make_insensitive('Script is running', ['sourceview', 'new_toolbutton', 'save_toolbutton', 'saveas_toolbutton',
                                                     'open_toolbutton', 'undo_toolbutton', 'redo_toolbutton', 'cut_toolbutton',
                                                     'copy_toolbutton', 'paste_toolbutton', 'help_toolbutton', 'execute_toolbutton'])
        self._interpreter_connections=[
            self._instrument.services['interpreter'].connect('cmd-return', self.on_script_end),
            self._instrument.services['interpreter'].connect('cmd-fail', self.on_script_fail),
            self._instrument.services['interpreter'].connect('pulse', self.on_script_pulse),
            self._instrument.services['interpreter'].connect('progress', self.on_script_progress),
            self._instrument.services['interpreter'].connect('cmd-message', self.on_script_message),
            self._instrument.services['interpreter'].connect('flag', self.on_interpreter_flag),
                                       ]
        # self._instrument.services['interpreter'].clear_flag(None)  # clear all flags
        flagsbb = self._builder.get_object('flags_buttonbox')
        for b in flagsbb:
            if b.get_active():
                self._instrument.services['interpreter'].set_flag(b.get_label())

        self._builder.get_object('sourceview').set_editable(False)
        self._scriptconnections = [self._scriptcommand.connect('cmd-start', self.on_command_start),
                                   self._scriptcommand.connect('paused', self.on_script_paused)]
        buf = self._builder.get_object('messagesbuffer')
        buf.insert(buf.get_end_iter(),
                   '----------------------- %s -----------------------\n' % str(datetime.datetime.now()))
        self._builder.get_object('messagesview').scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        buf.place_cursor(buf.get_end_iter())
        try:
            self._instrument.services['interpreter'].execute_command(self._scriptcommand)
        except Exception:
            self._cleanup()
            raise
        try:
            with open(self._filename[:-len('.cct')] + '.log', 'at', encoding='utf-8') as f:
                f.write(str(datetime.datetime.now()) + ': ----------------------- Started -----------------------\n')
        except AttributeError:
            pass

    def _cleanup(self):
        self._make_sensitive()
        for c in self._interpreter_connections:
            self._instrument.services['interpreter'].disconnect(c)
        del self._interpreter_connections
        self._builder.get_object('sourceview').set_editable(True)
        self._sourcebuffer.remove_source_marks(
            self._sourcebuffer.get_start_iter(), self._sourcebuffer.get_end_iter(), 'Executing')
        self._builder.get_object('progressbar').set_text('')
        self._builder.get_object('progressbar').set_fraction(0)
        for c in self._scriptconnections:
            self._scriptcommand.disconnect(c)
        del self._scriptconnections
        del self._scriptcommand

    def on_script_end(self, interpreter, commandname, returnvalue):
        info_message(self._window,'Script ended','Result: %s'%str(returnvalue))
        self._cleanup()
        n=Notify.Notification(summary='Script ended',body='Script execution ended with result: %s'%str(returnvalue))
        n.set_image_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(pkg_resources.resource_filename('cct','resource/icons/scalable/cctlogo.svg'),256,256))
        n.show()

    def on_script_fail(self, interpreter, commandname, exc, tb):
        error_message(self._window, 'Error while executing script', tb)

    def on_script_pulse(self, interpreter, commandname, message):
        pb=self._builder.get_object('progressbar')
        pb.set_visible(True)
        pb.set_text(message)
        pb.pulse()

    def on_script_progress(self, interpreter, commandname, message, fraction):
        pb=self._builder.get_object('progressbar')
        pb.set_visible(True)
        pb.set_text(message)
        pb.set_fraction(fraction)

    def on_script_message(self, interpreter, commandname, message):
        buf=self._builder.get_object('messagesview').get_buffer()
        buf.insert(buf.get_end_iter(), str(datetime.datetime.now())+': '+message+'\n')
        self._builder.get_object('messagesview').scroll_to_iter(buf.get_end_iter(), 0,False, 0,0)
        buf.place_cursor(buf.get_end_iter())
        try:
            with open(self._filename[:-len('.cct')]+'.log','at', encoding='utf-8') as f:
                f.write(str(datetime.datetime.now())+': '+message+'\n')
        except AttributeError:
            pass

    def on_command_start(self, scriptcmd, lineno, command ):
        it = self._sourcebuffer.get_iter_at_line(lineno)
        self._sourcebuffer.remove_source_marks(
            self._sourcebuffer.get_start_iter(), self._sourcebuffer.get_end_iter(), 'Executing')
        self._sourcebuffer.create_source_mark(
            'Line #%d' % lineno, 'Executing', it)
        self._builder.get_object('sourceview').scroll_to_iter(it, 0, False, 0, 0)
        self._sourcebuffer.place_cursor(it)
        self._builder.get_object('progressbar').hide()

    def on_toolbutton_pause(self, toolbutton):
        if toolbutton.get_active():
            self._scriptcommand.pause()
            self._pausingdlg=Gtk.Dialog('Waiting for script to pause', self._window,
                                        Gtk.DialogFlags.DESTROY_WITH_PARENT| Gtk.DialogFlags.USE_HEADER_BAR | Gtk.DialogFlags.MODAL,
                                        )
            self._pausingprogress=Gtk.ProgressBar()
            self._pausingprogress.set_text('Pausing...')
            self._pausingdlg.get_content_area().pack_start(self._pausingprogress, False, True, False)
            self._pausingdlg.show_all()
            self._pausingpulsehandler=GLib.timeout_add(300,self._pausing_pulse)
        else:
            self._scriptcommand.resume()

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
            notif=Notify.Notification.new('Script has been paused')
            notif.show()
        except AttributeError:
            pass

    def on_toolbutton_stop(self, toolbutton):
        self._instrument.services['interpreter'].kill()

    def on_toolbutton_help(self, toolbutton):
        if not hasattr(self, '_helpdialog'):
            self._helpdialog = CommandHelpDialog('help_commandhelpbrowser.glade', 'commandhelpbrowser',
                                                 self._instrument, self._application, 'Help on commands')
            self._helpdialog.connect('insert', self.on_insert)
        self._helpdialog._window.show_all()

    def on_insert(self, helpdialog, text):
        self._sourcebuffer.insert_at_cursor(text)

    def on_close(self, widget, event=None):
        self.confirm_save()
        ToolWindow.on_close(self, widget, event)

    def on_flag_toggled(self, flagtoggle):
        if flagtoggle.get_active():
            self._instrument.services['interpreter'].set_flag(flagtoggle.get_label())
        else:
            self._instrument.services['interpreter'].clear_flag(flagtoggle.get_label())

    def on_interpreter_flag(self, interpreter, flagname, newstate):
        logger.info('Flag state changed: %s, %s'%(flagname, newstate))
        tb=self._builder.get_object('flag'+flagname+'_button')
        if tb is None:
            raise('No flag button: %s'%flagname)
        tb.set_active(newstate)
        return False

class CommandHelpDialog(ToolWindow):
    __gsignals__ = {'insert': (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def _init_gui(self, *args):
        model = self._builder.get_object('commandnames')
        for command in sorted([c.name for c in Command.allcommands()]):
            model.append((command,))
        tc = Gtk.TreeViewColumn('Command', Gtk.CellRendererText(), text=0)
        self._builder.get_object('commandsview').append_column(tc)
        self._builder.get_object('commandsview').get_selection().select_iter(model.get_iter_first())

    def on_command_selected(self, treeviewselection):
        model, it = treeviewselection.get_selected()
        buf = self._builder.get_object('helptextbuffer')
        buf.set_text([c.__doc__ for c in Command.allcommands() if c.name == model[it][0]][0])

    def on_insert(self, button):
        model, it = self._builder.get_object('commandsview').get_selection().get_selected()
        self.emit('insert', model[it][0] + '()')
