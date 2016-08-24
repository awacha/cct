import logging

from gi.repository import Gtk

from ..core.dialogs import question_message, error_message
from ..core.toolwindow import ToolWindow
from ...core.instrument.privileges import PrivilegeLevel, PRIV_USERMAN, PRIV_LAYMAN

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class UserManager(ToolWindow):
    privlevel = PRIV_USERMAN

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self.update_gui()

    def init_gui(self, *args, **kwargs):
        ps = self.builder.get_object('privilege_selector')
        for pl in PrivilegeLevel.all_privileges():
            ps.append_text(pl.name)
        self.update_gui()

    def update_gui(self, username_to_select=None):
        model = self.builder.get_object('usernamestore')
        model.clear()
        iter_to_select = None
        for u in self.instrument.services['accounting'].get_usernames():
            it = model.append((u,))
            if u.username == username_to_select:
                iter_to_select = it
        if iter_to_select is None:
            iter_to_select = model.get_iter_first()
        self.builder.get_object('user-selection').select_iter(iter_to_select)
        self.builder.get_object('apply_button').set_sensitive(False)

    def on_editable_changed(self, widget):
        self.builder.get_object('apply_button').set_sensitive(True)

    def on_selection_changed(self, selection):
        if self.builder.get_object('apply_button').get_sensitive():
            if question_message(self.widget, 'Confirm saving changes', 'Save changes?'):
                self.on_apply(self.builder.get_object('apply_button'))
            self.builder.get_object('apply_button').set_sensitive(False)
        model, iterator = selection.get_selected()
        if iterator is None:
            return
        username = model[iterator][0]
        ps = self.builder.get_object('privilege_selector')
        ps.set_sensitive(username != self.instrument.services['accounting'].get_user().username)
        self.builder.get_object('deluser_button').set_sensitive(
            username != self.instrument.services['accounting'].get_user().username)
        ps.set_active(-1)
        for i, priv in enumerate(ps.get_model()):
            logger.debug('Comparing privilege level with %s.' % priv[0])
            if PrivilegeLevel.get_priv(priv[0]) == self.instrument.services['accounting'].get_user(username).privlevel:
                ps.set_active(i)
        assert (ps.get_active_text() is not None)
        self.builder.get_object('firstname_entry').set_text(
            self.instrument.services['accounting'].get_user(username).firstname)
        self.builder.get_object('lastname_entry').set_text(
            self.instrument.services['accounting'].get_user(username).lastname)
        self.builder.get_object('apply_button').set_sensitive(False)

    def on_apply(self, button):
        firstname = self.builder.get_object('firstname_entry').get_text()
        lastname = self.builder.get_object('lastname_entry').get_text()
        if self.builder.get_object('privilege_selector').get_sensitive():
            privlevel = self.builder.get_object('privilege_selector').get_active_text()
        else:
            privlevel = None
        model, iterator = self.builder.get_object('user-selection').get_selected()
        if iterator is None:
            return
        username = model[iterator][0]
        self.instrument.services['accounting'].update_user(username, firstname, lastname, privlevel)
        logger.info('Updated user %s: %s, %s, %s' % (username, firstname, lastname, privlevel))
        user = [u for u in self.instrument.services['accounting'].users if u.username == username][0]
        logger.info('Control: %s, %s, %s' % (user.firstname, user.lastname, user.privlevel))
        button.set_sensitive(False)

    def on_adduser(self, button):
        dlg = Gtk.Dialog('Add user', self.widget, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                         ['Ok', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL])
        b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        l = Gtk.Label('User name:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.FILL)
        l.set_margin_right(5)
        b.pack_start(l, False, True, 0)
        entry = Gtk.Entry()
        b.pack_start(entry, True, True, 0)
        entry.set_placeholder_text('The name of the new user...')
        dlg.vbox.pack_start(b, True, True, 0)
        dlg.foreach(lambda x: x.show_all())
        # dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            try:
                user = self.instrument.services['accounting'].add_user(entry.get_text(), '', '', PRIV_LAYMAN)
                self.update_gui(user.username)
            except Exception as exc:
                error_message(dlg, 'Cannot add new user', str(exc))
        dlg.destroy()

    def on_deluser(self, button):
        model, iterator = self.builder.get_object('user-selection').get_selected()
        if iterator is None:
            return
        username = model[iterator][0]
        self.instrument.services['accounting'].delete_user(username)
        self.update_gui()
